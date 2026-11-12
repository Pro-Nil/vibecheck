"""VibeCheck REST API. Run:  uvicorn vibe.main:app --app-dir backend --port 8000
Docs: http://localhost:8000/docs   Spec: http://localhost:8000/openapi.json
"""
from __future__ import annotations

import io
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from sqlalchemy import delete, func, select

from . import config, features, importers, model, pipeline, plugins
from .db import Check, Feature, Job, ModelVersion, Outcome, Plugin, Post, SessionLocal, Team, init_db
from .schemas import ImportIn, OutcomeIn, Panel, PluginIn, PluginPatch, PostPatch, TeamIn, TeamPatch

MAX_UPLOAD_MB = 15
_scheduler = None


def _daily_refresh():
    with SessionLocal() as s:
        teams = [t.id for t in s.scalars(select(Team).where(Team.instagram_handle.is_not(None)))]
    for tid in teams:
        # only the team page's posts from the last week: never re-pulls old posts or other pages
        pipeline.request_refresh(tid, "daily-refresh", background=False, fetch=True, max_posts=50,
                                 max_posts_other=0, since=datetime.now() - timedelta(days=7))


@asynccontextmanager
async def lifespan(_app):
    global _scheduler
    init_db()
    with SessionLocal() as s:  # jobs cut off by a restart will never finish: say so
        for j in s.scalars(select(Job).where(Job.status.in_(("queued", "running")))):
            j.status, j.message = "failed", (j.message + "; stopped: server restarted").lstrip("; ")
        s.commit()
    if config.SCHEDULER_ON:
        from apscheduler.schedulers.background import BackgroundScheduler
        _scheduler = BackgroundScheduler(daemon=True)
        _scheduler.add_job(_daily_refresh, "cron", hour=config.REFRESH_HOUR, minute=0, id="daily-refresh")
        _scheduler.start()
    yield
    if _scheduler:
        _scheduler.shutdown(wait=False)


TAGS = [
    {"name": "teams", "description": "Design teams and their Instagram pages."},
    {"name": "data", "description": "Import posts, list posts, run feature extraction."},
    {"name": "model", "description": "Train the vibe model and read its accuracy."},
    {"name": "checks", "description": "Score a designer's plan (the main call)."},
    {"name": "plugins", "description": "Register another team's service to add panels inside the app."},
]
app = FastAPI(title="VibeCheck API", version="1.0.0", lifespan=lifespan, openapi_tags=TAGS,
              description="Learns a design team's visual style from its Instagram feed and scores a "
                          "designer's plan (inspiration images + description) before they design.\n\n"
                          "**Plugins:** register with `POST /plugins`. We POST an event to your URL and "
                          "draw the `Panel` you return. See the `Panel` schema below.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/media", StaticFiles(directory=config.DATA_DIR), name="media")


# ----------------------------------------------------------------------- helpers
def _team(s, team_id: int) -> Team:
    t = s.get(Team, team_id)
    if t is None:
        raise HTTPException(404, f"Team {team_id} not found")
    return t


async def _read_image(f: UploadFile) -> tuple[bytes, Image.Image]:
    data = await f.read()
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"{f.filename} is larger than {MAX_UPLOAD_MB} MB")
    try:
        img = features.load_image(io.BytesIO(data))
    except Exception:
        raise HTTPException(400, f"{f.filename} is not an image we can read")
    return data, img


def _base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


# ------------------------------------------------------------------------- teams
@app.get("/health", tags=["teams"])
def health():
    return {"ok": True, "fake_clip": config.FAKE_CLIP}


@app.post("/teams", tags=["teams"], status_code=201)
def create_team(body: TeamIn):
    with SessionLocal() as s:
        t = Team(name=body.name, instagram_handle=(body.instagram_handle or "").lstrip("@") or None,
                 other_pages_json=json.dumps([p.lstrip("@") for p in body.other_pages if p.strip()]))
        s.add(t)
        s.commit()
        return t.to_dict()


@app.get("/teams", tags=["teams"])
def list_teams():
    with SessionLocal() as s:
        teams = s.scalars(select(Team).order_by(Team.id)).all()
        counts = dict(s.execute(select(Post.team_id, func.count()).where(Post.label == "team")
                                .group_by(Post.team_id)).all())
        trained = {tid for (tid,) in s.execute(select(ModelVersion.team_id).distinct())}
        return [{**t.to_dict(), "n_posts": counts.get(t.id, 0), "trained": t.id in trained} for t in teams]


@app.get("/teams/{team_id}", tags=["teams"])
def get_team(team_id: int):
    with SessionLocal() as s:
        t = _team(s, team_id)
        counts = dict(s.execute(select(Post.label, func.count()).where(Post.team_id == team_id)
                                .group_by(Post.label)).all())
        return {**t.to_dict(), "counts": counts}


@app.patch("/teams/{team_id}", tags=["teams"])
def patch_team(team_id: int, body: TeamPatch):
    with SessionLocal() as s:
        t = _team(s, team_id)
        if body.name is not None:
            t.name = body.name
        if body.instagram_handle is not None:
            t.instagram_handle = body.instagram_handle.lstrip("@") or None
        if body.other_pages is not None:
            t.other_pages_json = json.dumps([p.lstrip("@") for p in body.other_pages if p.strip()])
        s.commit()
        return t.to_dict()


@app.delete("/teams/{team_id}", tags=["teams"], summary="Delete a team and everything it owns",
            responses={409: {"description": "An import or training job for this team is still running"}})
def delete_team(team_id: int):
    """Removes the team's posts, features, checks and outcomes, model versions, jobs and team-only plugins, and its
    files: images/team_<id>/, models/team_<id>_v*.joblib and the upload folders of its checks. Cannot be undone.
    The Instagram download cache (raw/) is shared by page handle and is kept."""
    import shutil
    with SessionLocal() as s:
        t = _team(s, team_id)
        busy = s.scalar(select(Job.id).where(Job.team_id == team_id, Job.status.in_(("queued", "running"))))
        if busy:
            raise HTTPException(409, "An import or training job for this team is still running. Wait for it to finish, then delete.")
        name = t.name
        checks = list(s.scalars(select(Check).where(Check.team_id == team_id)))
        upload_dirs = {Path(p).parent for c in checks for p in json.loads(c.inspo_json or "[]")}
        post_ids = list(s.scalars(select(Post.id).where(Post.team_id == team_id)))
        counts = {"posts": len(post_ids), "checks": len(checks)}
        if post_ids:
            s.execute(delete(Feature).where(Feature.post_id.in_(post_ids)))
        if checks:
            s.execute(delete(Outcome).where(Outcome.check_id.in_([c.id for c in checks])))
        for table in (Check, Post, ModelVersion, Plugin, Job):
            s.execute(delete(table).where(table.team_id == team_id))
        s.delete(t)
        s.commit()
    model.forget(team_id)
    data = config.DATA_DIR.resolve()

    def rm(path: Path):  # only ever inside the data folder
        p = path.resolve()
        if p != data and data in p.parents and p.exists():
            shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
    rm(config.IMAGES_DIR / f"team_{team_id}")
    for f in config.MODELS_DIR.glob(f"team_{team_id}_v*.joblib"):
        rm(f)
    for d in upload_dirs:
        if d.name.startswith("check_"):
            rm(config.DATA_DIR / d)
    return {"deleted": team_id, "name": name, **counts}


# -------------------------------------------------------------------------- data
@app.post("/teams/{team_id}/import", tags=["data"], status_code=202,
          summary="Fetch / import posts, compute features and train (runs in the background)")
def start_import(team_id: int, body: ImportIn = Body(default_factory=ImportIn)):
    with SessionLocal() as s:
        _team(s, team_id)
    return pipeline.request_refresh(
        team_id, "import", fetch=body.fetch_instagram, max_posts=body.max_posts, max_posts_other=body.max_posts_other,
        since=datetime.combine(body.since, datetime.min.time()) if body.since else None,
        folders=[f.model_dump() for f in body.folders])


@app.post("/teams/{team_id}/import/upload", tags=["data"], status_code=201,
          summary="Upload many images at once: team posts, other-page posts, accepted designs or rejected drafts")
async def upload_many(team_id: int, files: list[UploadFile] = File(...),
                      label: str = Form("team", description="team | other | accepted | rejected. "
                                        "'accepted' and 'rejected' are designs the seniors decided on; they train the approval model."),
                      project: str = Form("", description="Which brief/project these designs were for, e.g. 'finlit-talk'. "
                                          "Versions of one brief let the model learn which version wins."),
                      meta: UploadFile | None = File(None, description="Optional meta.csv with columns filename and any of "
                                                     "posted_at (YYYY-MM-DD), likes, caption, project. A project in the "
                                                     "file overrides the form's project for that image."),
                      train: bool = Form(True)):
    if label not in ("team", "other", "rejected", "accepted"):
        raise HTTPException(400, "label must be team, other, accepted or rejected")
    with SessionLocal() as s:
        _team(s, team_id)
    rows = {}
    if meta is not None and meta.filename:
        try:
            rows = importers.parse_meta_csv((await meta.read()).decode("utf-8-sig"))
        except Exception as e:
            raise HTTPException(400, f"Could not read {meta.filename}: {e}")
    n = with_meta = 0
    for f in files:
        data, _ = await _read_image(f)
        name = Path(f.filename or "upload.png").name
        row = rows.get(name, {})
        with_meta += bool(row)
        importers.add_upload(team_id, data, name, "team" if label == "accepted" else label,
                             caption=row.get("caption") or "", likes=importers.as_int(row.get("likes")),
                             posted_at=importers.date_from(row.get("posted_at"), name),
                             decision="accepted" if label == "accepted" else None,
                             project=(row.get("project") or project).strip() or None)
        n += 1
    run = pipeline.request_refresh(team_id, "retrain", fetch=False) if train else {}
    # joined: a run was already going; queued_follow_up: it runs once more afterwards so these images are included
    return {"added": n, "with_meta": with_meta, "job_id": run.get("job_id"), "joined": run.get("joined", False),
            "queued_follow_up": run.get("queued_follow_up", False)}


@app.get("/jobs/{job_id}", tags=["data"])
def get_job(job_id: int):
    with SessionLocal() as s:
        j = s.get(Job, job_id)
        if j is None:
            raise HTTPException(404, "Job not found")
        return j.to_dict()


@app.get("/teams/{team_id}/jobs", tags=["data"])
def list_jobs(team_id: int, limit: int = 10):
    with SessionLocal() as s:
        return [j.to_dict() for j in s.scalars(select(Job).where(Job.team_id == team_id)
                                                .order_by(Job.id.desc()).limit(limit))]


@app.get("/teams/{team_id}/posts", tags=["data"])
def list_posts(team_id: int, label: str | None = None, with_features: bool = False,
               limit: int = Query(60, le=500), offset: int = 0):
    with SessionLocal() as s:
        _team(s, team_id)
        q = select(Post).where(Post.team_id == team_id)
        if label:
            q = q.where(Post.label == label)
        total = s.scalar(select(func.count()).select_from(q.subquery()))
        rows = s.scalars(q.order_by(Post.posted_at.desc().nullslast(), Post.id.desc())
                         .limit(limit).offset(offset)).all()
        return {"total": total, "items": [p.to_dict(with_features) for p in rows]}


@app.get("/posts/{post_id}", tags=["data"])
def get_post(post_id: int):
    with SessionLocal() as s:
        p = s.get(Post, post_id)
        if p is None:
            raise HTTPException(404, "Post not found")
        return p.to_dict(with_features=True)


@app.patch("/posts/{post_id}", tags=["data"], summary="Set what the seniors decided about a post, and its project")
def patch_post(post_id: int, body: PostPatch):
    with SessionLocal() as s:
        p = s.get(Post, post_id)
        if p is None:
            raise HTTPException(404, "Post not found")
        for k, v in body.model_dump(exclude_unset=True).items():
            setattr(p, k, v or None)
        s.commit()
    return get_post(post_id)


@app.post("/teams/{team_id}/posts", tags=["data"], status_code=201,
          summary="Add one post or draft by hand (features are computed right away)")
async def add_post(team_id: int, file: UploadFile = File(...), label: str = Form("team"),
                   caption: str = Form(""), likes: int | None = Form(None),
                   posted_at: str | None = Form(None, description="YYYY-MM-DD")):
    if label not in ("team", "other", "rejected"):
        raise HTTPException(400, "label must be team, other or rejected")
    with SessionLocal() as s:
        _team(s, team_id)
    data, _ = await _read_image(file)
    when = datetime.strptime(posted_at, "%Y-%m-%d") if posted_at else None
    p = importers.add_upload(team_id, data, file.filename or "upload.png", label, caption, likes, when)
    pipeline.compute_missing_features(team_id)
    return get_post(p.id)


@app.post("/features", tags=["data"], summary="Utility: CLIP vector + style features of any image")
async def image_features(file: UploadFile = File(...), include_vector: bool = False):
    _, img = await _read_image(file)
    f = features.extract([img])[0]
    out = {k: round(float(f[k]), 4) for k in features.STYLE_KEYS}
    out["palette"] = f["palette"]
    if include_vector:
        out["clip"] = [round(float(x), 5) for x in f["clip"]]
    return out


# ------------------------------------------------------------------------- model
@app.post("/teams/{team_id}/retrain", tags=["model"], status_code=202)
def retrain(team_id: int):
    with SessionLocal() as s:
        _team(s, team_id)
    # pressing Retrain while a run is going joins that run instead of starting a second one
    return pipeline.request_refresh(team_id, "retrain", follow_up=False, fetch=False)


@app.get("/teams/{team_id}/model", tags=["model"], summary="Current model, its accuracy, and history")
def get_model(team_id: int):
    with SessionLocal() as s:
        _team(s, team_id)
        rows = s.scalars(select(ModelVersion).where(ModelVersion.team_id == team_id)
                         .order_by(ModelVersion.id.desc())).all()
        if not rows:
            raise HTTPException(404, "No model trained yet for this team")
        return {"current": rows[0].to_dict(),
                "history": [{"id": r.id, "trained_at": r.trained_at.isoformat(),
                             "auc": json.loads(r.metrics_json).get("auc")} for r in rows]}


@app.get("/teams/{team_id}/style-profile", tags=["model"])
def get_style_profile(team_id: int, request: Request, include_plugins: bool = True):
    with SessionLocal() as s:
        team = _team(s, team_id).to_dict()
    try:
        prof = model.style_profile(team_id)
    except model.NotTrained as e:
        raise HTTPException(409, str(e))
    prof["team"] = team
    prof["plugins"] = plugins.run_plugins(team_id, "profile", {
        "event": "profile.viewed", "api_base": _base_url(request), "team": team,
        "profile": {k: prof[k] for k in ("ranges", "signature_palette", "thresholds", "trend")},
    }) if include_plugins else []
    return prof


# ------------------------------------------------------------------------ checks
@app.post("/teams/{team_id}/checks", tags=["checks"], status_code=201,
          summary="Score a plan (1-5 inspiration images and/or a description) or a finished design (kind=final, 1 image)")
async def create_check(team_id: int, request: Request,
                       images: list[UploadFile] = File(
                           default=[], description="1-5 inspiration images (JPG, PNG or WebP, up to 15 MB each). "
                                                   "Repeat the field once per image."),
                       description: str = Form("", description="What you plan to make: colours, layout, fonts, "
                                                               "photo or illustration. Send images, a description, or both."),
                       user: str = Form("", description="Who is checking (optional, shown in History)."),
                       kind: str = Form("plan", description="plan = inspiration before designing; "
                                        "final = your finished design (exactly 1 image): adds finish checks "
                                        "(legibility, text size, edges, resolution) and the learned approval model."),
                       plan_check_id: int | None = Form(None, description="For kind=final: the plan check this design came from, "
                                                        "to compare the final with its plan."),
                       project: str = Form("", description="Which brief/project this is for (optional). "
                                           "Lets decisions on versions of one brief train the approval model.")):
    with SessionLocal() as s:
        team = _team(s, team_id).to_dict()
        plan = s.get(Check, plan_check_id) if plan_check_id else None
        if plan_check_id and (plan is None or plan.team_id != team_id):
            raise HTTPException(404, "Plan check not found for this team")
        plan_paths = json.loads(plan.inspo_json) if plan else []
        plan_dict = plan.to_dict() if plan else None
        if plan is not None and not project:
            project = plan.project or ""
    if kind not in ("plan", "final"):
        raise HTTPException(400, "kind must be plan or final")
    images = [f for f in images if f.filename]
    if len(images) > 5:
        raise HTTPException(400, "Send at most 5 inspiration images")
    folder = config.UPLOADS_DIR / f"check_{uuid.uuid4().hex[:12]}"
    folder.mkdir(parents=True, exist_ok=True)
    pil, paths = [], []
    for i, f in enumerate(images):
        data, img = await _read_image(f)
        dest = folder / f"{i}_{importers._safe(f.filename or 'inspo.png')}"
        dest.write_bytes(data)
        pil.append(img)
        paths.append(dest.relative_to(config.DATA_DIR).as_posix())
    try:
        plan_imgs = [features.load_image(config.DATA_DIR / p) for p in plan_paths] if kind == "final" else None
        result = model.score(team_id, pil, description, kind=kind, plan_images=plan_imgs, plan_result=plan_dict)
    except model.NotTrained as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    with SessionLocal() as s:
        c = Check(team_id=team_id, user=user, description=description, inspo_json=json.dumps(paths),
                  score=result["score"], verdict=result["verdict"], result_json=json.dumps(result),
                  model_version=result["model_version"], kind=kind,
                  parent_id=plan_check_id if kind == "final" else None, project=project.strip() or None)
        s.add(c)
        s.commit()
        check = c.to_dict()
    base = _base_url(request)
    check["plugins"] = plugins.run_plugins(team_id, "result", {
        "event": "check.completed", "api_base": base, "team": team,
        "check": {**{k: check.get(k) for k in ("id", "kind", "score", "verdict", "verdict_level", "reasons", "plan_style",
                                               "plan_palette", "description", "nearest", "engagement", "finish")},
                  "inspo_urls": [base + u for u in check["inspo_urls"]]},
    })
    with SessionLocal() as s:  # keep plugin panels with the check so History shows them too
        c = s.get(Check, check["id"])
        stored = json.loads(c.result_json)
        stored["plugins"] = check["plugins"]
        c.result_json = json.dumps(stored)
        s.commit()
    return check


@app.get("/teams/{team_id}/checks", tags=["checks"])
def list_checks(team_id: int, limit: int = Query(50, le=500)):
    with SessionLocal() as s:
        rows = s.scalars(select(Check).where(Check.team_id == team_id)
                         .order_by(Check.id.desc()).limit(limit)).all()
        return [c.to_dict() for c in rows]


@app.get("/checks/{check_id}", tags=["checks"])
def get_check(check_id: int):
    with SessionLocal() as s:
        c = s.get(Check, check_id)
        if c is None:
            raise HTTPException(404, "Check not found")
        out = c.to_dict()
        out["finals"] = [{"id": f.id, "score": f.score, "verdict": f.verdict}
                         for f in s.scalars(select(Check).where(Check.parent_id == check_id).order_by(Check.id))]
        return out


@app.post("/checks/{check_id}/outcome", tags=["checks"],
          summary="Record what the seniors decided; with a final image it becomes training data")
async def set_outcome(check_id: int, result: str = Form(...), final_image: UploadFile | None = File(None)):
    OutcomeIn(result=result)  # validates the value
    with SessionLocal() as s:
        c = s.get(Check, check_id)
        if c is None:
            raise HTTPException(404, "Check not found")
        team_id, kind, project = c.team_id, c.kind or "plan", c.project
        own = json.loads(c.inspo_json)
    data = name = None
    if final_image is not None and final_image.filename:
        data, _ = await _read_image(final_image)
        name = final_image.filename
    elif kind == "final" and own:   # a final check's own image IS the design that was decided on
        data, name = (config.DATA_DIR / own[0]).read_bytes(), Path(own[0]).name
    final_path = None
    if data is not None:
        decided = result in ("approved", "posted")
        p = importers.add_upload(team_id, data, name, "team" if decided else "rejected",
                                 caption=f"final design of check {check_id}",
                                 decision="accepted" if decided else "rejected",
                                 project=project or f"check-{check_id}")
        final_path = p.image_path
        pipeline.compute_missing_features(team_id)
    with SessionLocal() as s:
        o = s.get(Outcome, check_id) or Outcome(check_id=check_id)
        o.result, o.final_image_path = result, final_path or o.final_image_path
        s.merge(o)
        s.commit()
    return get_check(check_id)


# ----------------------------------------------------------------------- plugins
@app.post("/plugins", tags=["plugins"], status_code=201)
def register_plugin(body: PluginIn):
    with SessionLocal() as s:
        p = Plugin(**body.model_dump())
        s.add(p)
        s.commit()
        return p.to_dict()


@app.get("/plugins", tags=["plugins"])
def list_plugins(team_id: int | None = None):
    with SessionLocal() as s:
        q = select(Plugin).order_by(Plugin.id)
        if team_id is not None:
            q = q.where((Plugin.team_id == team_id) | Plugin.team_id.is_(None))
        return [p.to_dict() for p in s.scalars(q)]


@app.get("/plugins/panel-example", tags=["plugins"], response_model=Panel,
         summary="An example of the Panel JSON your plugin must return")
def panel_example():
    return Panel(title="Readability", summary="Contrast of your main colours.",
                 metrics=[{"label": "Best contrast", "value": 5.2, "unit": ":1"}],
                 items=[{"ok": True, "text": "Passes the 4.5:1 rule for small text."}],
                 chart={"type": "bar", "title": "Contrast with background",
                        "points": [{"label": "#ffffff", "value": 5.2}, {"label": "#ffcc00", "value": 2.1}]})


@app.patch("/plugins/{plugin_id}", tags=["plugins"])
def patch_plugin(plugin_id: int, body: PluginPatch):
    with SessionLocal() as s:
        p = s.get(Plugin, plugin_id)
        if p is None:
            raise HTTPException(404, "Plugin not found")
        for k, v in body.model_dump(exclude_none=True).items():
            setattr(p, k, int(v) if k == "enabled" else v)
        s.commit()
        return p.to_dict()


@app.delete("/plugins/{plugin_id}", tags=["plugins"], status_code=204)
def delete_plugin(plugin_id: int):
    with SessionLocal() as s:
        p = s.get(Plugin, plugin_id)
        if p is None:
            raise HTTPException(404, "Plugin not found")
        s.delete(p)
        s.commit()


# ------------------------------------------------------------- built frontend (SPA)
_DIST = config.ROOT / "frontend" / "dist"
if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = _DIST / path
        return FileResponse(f if path and f.is_file() else _DIST / "index.html")
