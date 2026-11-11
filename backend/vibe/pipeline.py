"""Transform + Load: compute features for new posts, make near-misses, run whole refresh jobs."""
from __future__ import annotations

import json
import traceback
from typing import Callable

import numpy as np
from sqlalchemy import select

from . import augment, config, features
from .db import Feature, Job, Post, SessionLocal, Team, now

Progress = Callable[[float, str], None]


def compute_missing_features(team_id: int, progress: Progress | None = None, batch: int = 32) -> int:
    """Run feature extraction on every post of the team that has none yet."""
    with SessionLocal() as s:
        todo = list(s.scalars(select(Post).where(Post.team_id == team_id, ~Post.features.has())))
    done = 0
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        imgs, ok = [], []
        for p in chunk:
            try:
                imgs.append(features.load_image(config.DATA_DIR / p.image_path))
                ok.append(p)
            except Exception:
                continue  # unreadable file: skip, keep going
        feats = features.extract(imgs)
        with SessionLocal() as s:
            for p, f in zip(ok, feats):
                s.add(Feature(post_id=p.id, clip=f["clip"].astype(np.float32).tobytes(),
                              palette_json=json.dumps(f["palette"]),
                              **{k: float(f[k]) for k in features.STYLE_KEYS}))
            s.commit()
        done += len(ok)
        if progress:
            progress(done / max(1, len(todo)), f"Computed features for {done}/{len(todo)} images")
    return done


def make_near_misses(team_id: int, per_post: int = 1, progress: Progress | None = None) -> int:
    """One broken copy of each team post that does not have one yet."""
    with SessionLocal() as s:
        team_posts = list(s.scalars(select(Post).where(Post.team_id == team_id, Post.label == "team")))
        have = set(s.scalars(select(Post.external_id).where(Post.team_id == team_id,
                                                           Post.label == "augmented")))
    dest_dir = config.IMAGES_DIR / f"team_{team_id}" / "augmented"
    dest_dir.mkdir(parents=True, exist_ok=True)
    added = 0
    with SessionLocal() as s:
        for p in team_posts:
            for k in range(per_post):
                ext = f"aug{k}_{p.id}"
                if ext in have:
                    continue
                try:
                    img = features.load_image(config.DATA_DIR / p.image_path)
                except Exception:
                    continue
                out, how = augment.near_miss(img, seed=p.id * 31 + k)
                dest = dest_dir / f"{ext}.jpg"
                out.save(dest, quality=88)
                s.add(Post(team_id=team_id, label="augmented", source_page=f"near-miss:{how}",
                           external_id=ext, image_path=dest.relative_to(config.DATA_DIR).as_posix(),
                           caption=f"near-miss ({how}) of post {p.id}"))
                added += 1
        s.commit()
    if progress:
        progress(1.0, f"Made {added} near-miss images")
    return added


# ------------------------------------------------------------------------- jobs
def new_job(kind: str, team_id: int | None) -> int:
    with SessionLocal() as s:
        j = Job(kind=kind, team_id=team_id, status="queued", message="Waiting to start")
        s.add(j)
        s.commit()
        return j.id


def _update_job(job_id: int, **kw):
    with SessionLocal() as s:
        j = s.get(Job, job_id)
        for k, v in kw.items():
            setattr(j, k, v)
        s.commit()


def run_refresh(job_id: int, team_id: int, fetch: bool = True, max_posts: int = 300,
                max_posts_other: int = 60, folders: list[dict] | None = None,
                since=None) -> None:
    """The whole ETL + train run, reported step by step on the Job row.

    Steps (weights add to 1): fetch/import 0.35, features 0.4, near-misses 0.05, train 0.2.
    """
    from . import model

    def stage(start: float, width: float) -> Progress:
        return lambda f, msg: _update_job(job_id, progress=start + width * min(1.0, f), message=msg)

    _update_job(job_id, status="running", message="Starting")
    notes: list[str] = []
    try:
        with SessionLocal() as s:
            team = s.get(Team, team_id)
            handle, others = team.instagram_handle, team.other_pages
        from . import importers
        for spec in folders or []:
            n = importers.import_folder(team_id, spec["path"], spec.get("label", "team"),
                                        spec.get("source_page", ""), progress=stage(0, 0.1))
            notes.append(f"{n} images from folder {spec['path']}")
        if fetch:
            pages = (([(handle, "team")] if handle and max_posts > 0 else [])
                     + ([(o, "other") for o in others] if max_posts_other > 0 else []))
            for i, (h, lab) in enumerate(pages):
                try:
                    n = importers.fetch_instagram(team_id, h, lab,
                                                  max_posts=max_posts if lab == "team" else max_posts_other,
                                                  since=since,
                                                  progress=stage(0.35 * i / len(pages), 0.35 / len(pages)))
                    notes.append(f"{n} new posts from @{h}")
                except Exception as e:  # keep going: one blocked page should not kill the run
                    notes.append(f"@{h}: download failed ({type(e).__name__}: {str(e)[:120]})")
        compute_missing_features(team_id, stage(0.35, 0.35))
        make_near_misses(team_id, progress=stage(0.70, 0.03))
        compute_missing_features(team_id, stage(0.73, 0.07))
        _update_job(job_id, progress=0.8, message="Training the vibe model")
        mv = model.train(team_id)
        notes.append(f"model v{mv['id']} trained, hold-out AUC {mv['metrics'].get('auc')}")
        _update_job(job_id, status="done", progress=1.0, message="; ".join(notes), finished_at=now())
    except Exception as e:
        traceback.print_exc()
        _update_job(job_id, status="failed", message="; ".join(notes + [f"{type(e).__name__}: {e}"]),
                    finished_at=now())
