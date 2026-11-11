"""Build docs/api.html: a single self-contained page (no external scripts or fonts) documenting the
VibeCheck API, generated from the app's own OpenAPI spec, plus a plugin guide and real examples.

    .venv/Scripts/python scripts/build_api_docs.py [examples_dir]

examples_dir (optional) holds JSON responses captured from a running server:
check.json, profile.json, model.json, posts.json, teams.json. Missing files are skipped.
"""
from __future__ import annotations

import html
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("VIBE_FAKE_CLIP", "1")
os.environ.setdefault("VIBE_SCHEDULER", "0")
os.environ.setdefault("VIBE_DATA_DIR", tempfile.mkdtemp(prefix="vibe_docs_"))
sys.path.insert(0, str(ROOT / "backend"))

from vibe.main import app, panel_example  # noqa: E402

SPEC = app.openapi()
SCHEMAS = SPEC["components"]["schemas"]
E = html.escape


# ------------------------------------------------------------------ examples
def load_examples(d: Path | None) -> dict:
    ex = {}
    if not d:
        return ex
    for name in ("check", "profile", "model", "posts", "teams"):
        f = d / f"{name}.json"
        if f.exists():
            ex[name] = json.loads(f.read_text(encoding="utf-8"))
    return ex


def cut(s, n=48):
    return s if not isinstance(s, str) or len(s) <= n else s[:n] + "…"


def trim_check(c: dict) -> dict:
    keep = ["id", "team_id", "score", "verdict", "verdict_level", "thresholds", "weights", "components",
            "reasons", "plan_style", "plan_palette", "nearest", "engagement", "map_point", "description",
            "inspo_urls", "plugins", "model_version", "created_at", "outcome"]
    out = {k: c[k] for k in keep if k in c}
    out["reasons"] = [{k: v for k, v in r.items()} for r in c.get("reasons", [])[:2]] + ["…"]
    out["plan_palette"] = c.get("plan_palette", [])[:3] + ["…"]
    out["nearest"] = [{**{k: cut(v) for k, v in c["nearest"][0].items()}}, "…"] if c.get("nearest") else []
    out["signature_palette"] = c.get("signature_palette", [])[:2] + ["…"]
    rk = list(c.get("ranges", {}))[:1]
    out["ranges"] = {**{k: c["ranges"][k] for k in rk}, "…": "one entry per style feature"}
    return out


def trim_profile(p: dict) -> dict:
    m = p.get("metrics", {})
    out = {k: p[k] for k in ("model_version", "trained_at", "thresholds", "date_range") if k in p}
    out["metrics"] = {k: m[k] for k in ("n_team", "n_other", "n_rejected", "auc", "accuracy", "weights") if k in m}
    out["metrics"]["…"] = "roc, test_scores, real_rejects, engagement"
    rk = list(p.get("ranges", {}))[:1]
    out["ranges"] = {**{k: p["ranges"][k] for k in rk}, "…": "one entry per style feature"}
    out["signature_palette"] = p.get("signature_palette", [])[:2] + ["…"]
    out["trend"] = p.get("trend", [])[:1] + ["… one row per month"]
    out["what_works"] = (p.get("what_works") or [])[:2] + ["…"]
    out["map"] = p.get("map", [])[:2] + ["… one point per post"]
    out["plugins"] = []
    return out


def trim_posts(p: dict) -> dict:
    items = [{k: cut(v) for k, v in it.items()} for it in p.get("items", [])[:1]]
    return {"total": p.get("total"), "items": items + ["…"]}


def trim_model(m: dict) -> dict:
    cur = m.get("current", {})
    met = cur.get("metrics", {})
    return {"current": {"id": cur.get("id"), "team_id": cur.get("team_id"), "trained_at": cur.get("trained_at"),
                        "metrics": {**{k: met[k] for k in ("auc", "accuracy", "thresholds", "weights") if k in met},
                                    "…": "more fields"}},
            "history": m.get("history", [])[:2]}


# ------------------------------------------------------------------ schema rendering
def deref(s: dict) -> dict:
    while "$ref" in s:
        s = SCHEMAS[s["$ref"].split("/")[-1]]
    return s


def type_of(s: dict) -> str:
    if "$ref" in s:
        name = s["$ref"].split("/")[-1]
        return f'<a href="#schema-{E(name)}">{E(name)}</a>'
    if "anyOf" in s:
        return " | ".join(type_of(x) for x in s["anyOf"])
    if "enum" in s:
        return " | ".join(f"<code>{E(json.dumps(v))}</code>" for v in s["enum"])
    if s.get("const") is not None:
        return f"<code>{E(json.dumps(s['const']))}</code>"
    t = s.get("type", "any")
    if t == "array":
        return f"array of {type_of(s.get('items', {}))}"
    if t == "string" and s.get("format") in ("binary",):
        return "file"
    if t == "string" and s.get("contentMediaType"):
        return "file"
    if t == "string" and s.get("format"):
        return f"string ({E(s['format'])})"
    return E(t)


def fields_table(schema: dict) -> str:
    s = deref(schema)
    props = s.get("properties", {})
    if not props:
        return f"<p>{type_of(schema)}</p>"
    req = set(s.get("required", []))
    rows = []
    for name, p in props.items():
        desc = p.get("description", "")
        if "default" in p and p["default"] not in (None, [], ""):
            desc += f" Default: <code>{E(json.dumps(p['default']))}</code>."
        ex = p.get("examples")
        if ex:
            desc += f" Example: <code>{E(json.dumps(ex[0]))}</code>."
        rows.append(f"<tr><td><code>{E(name)}</code>{' <span class=req>required</span>' if name in req else ''}</td>"
                    f"<td>{type_of(p)}</td><td>{desc}</td></tr>")
    return ("<table><thead><tr><th>Field</th><th>Type</th><th>Description</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>")


def params_table(params: list) -> str:
    rows = []
    for p in params:
        sch = p.get("schema", {})
        desc = p.get("description", "")
        if "default" in sch and sch["default"] is not None:
            desc += f" Default: <code>{E(json.dumps(sch['default']))}</code>."
        if "maximum" in sch:
            desc += f" Max {sch['maximum']}."
        rows.append(f"<tr><td><code>{E(p['name'])}</code>{' <span class=req>required</span>' if p.get('required') else ''}</td>"
                    f"<td>{E(p['in'])}</td><td>{type_of(sch)}</td><td>{desc}</td></tr>")
    return ("<table><thead><tr><th>Name</th><th>In</th><th>Type</th><th>Description</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>")


def code(obj, lang="json") -> str:
    text = obj if isinstance(obj, str) else json.dumps(obj, indent=2, ensure_ascii=False, default=str)
    return f'<pre><code class="{lang}">{E(text)}</code></pre>'


# Example requests (curl) and which captured response goes with which operation
CURL = {
    ("post", "/teams"): """curl -X POST $API/teams -H "Content-Type: application/json" \\
  -d '{"name": "Techkriti Design", "instagram_handle": "techkriti.iitk", "other_pages": []}'""",
    ("post", "/teams/{team_id}/import"): """curl -X POST $API/teams/1/import -H "Content-Type: application/json" \\
  -d '{"fetch_instagram": true, "max_posts": 200, "max_posts_other": 30, "since": "2026-01-01"}'""",
    ("post", "/teams/{team_id}/import/upload"): """curl -X POST $API/teams/1/import/upload \\
  -F "files=@post1.jpg" -F "files=@post2.jpg" -F "label=team" """,
    ("post", "/teams/{team_id}/checks"): """curl -X POST $API/teams/1/checks \\
  -F "images=@inspo1.jpg" -F "images=@inspo2.png" \\
  -F "description=dark background, neon green code text, big bold title" -F "user=asha" """,
    ("post", "/checks/{check_id}/outcome"): """curl -X POST $API/checks/12/outcome -F "result=approved" -F "final_image=@final.jpg" """,
    ("post", "/features"): """curl -X POST "$API/features?include_vector=false" -F "file=@poster.jpg" """,
    ("post", "/plugins"): """curl -X POST $API/plugins -H "Content-Type: application/json" \\
  -d '{"name": "Font matcher", "url": "http://your-host:8100/hook", "slot": "result", "author_team": "Team 7"}'""",
    ("get", "/teams/{team_id}/style-profile"): "curl $API/teams/1/style-profile",
}
RESP = {
    ("post", "/teams/{team_id}/checks"): "check", ("get", "/checks/{check_id}"): "check",
    ("get", "/teams/{team_id}/style-profile"): "profile", ("get", "/teams/{team_id}/model"): "model",
    ("get", "/teams/{team_id}/posts"): "posts", ("get", "/teams"): "teams",
}
STATIC_RESP = {
    ("post", "/teams/{team_id}/import"): {"job_id": 7},
    ("post", "/teams/{team_id}/retrain"): {"job_id": 8},
    ("get", "/jobs/{job_id}"): {"id": 7, "team_id": 1, "kind": "import", "status": "running", "progress": 0.42,
                                "message": "Computed features for 120/280 images", "created_at": "2026-11-11T16:57:19",
                                "finished_at": None},
    ("get", "/health"): {"ok": True, "fake_clip": False},
}

TAG_TEXT = {t["name"]: t["description"] for t in SPEC.get("tags", [])}
TAG_ORDER = ["checks", "plugins", "model", "data", "teams"]


def op_id(method, path):
    return f"op-{method}-{path.strip('/').replace('/', '-').replace('{', '').replace('}', '')}"


def render_ops(ex: dict) -> tuple[str, str]:
    by_tag: dict[str, list] = {}
    for path, ops in SPEC["paths"].items():
        for method, op in ops.items():
            by_tag.setdefault((op.get("tags") or ["other"])[0], []).append((method, path, op))
    nav, body = [], []
    for tag in TAG_ORDER + [t for t in by_tag if t not in TAG_ORDER]:
        if tag not in by_tag:
            continue
        nav.append(f'<li class="navtag">{E(tag.title())}</li>')
        body.append(f'<h2 id="tag-{E(tag)}">{E(tag.title())}</h2><p class="muted">{E(TAG_TEXT.get(tag, ""))}</p>')
        for method, path, op in by_tag[tag]:
            oid = op_id(method, path)
            nav.append(f'<li><a href="#{oid}"><span class="m {method}">{method.upper()}</span> {E(path)}</a></li>')
            parts = [f'<section class="op" id="{oid}"><h3><span class="m {method}">{method.upper()}</span> '
                     f'<code>{E(path)}</code></h3><p class="summary">{E(op.get("summary", ""))}</p>']
            if op.get("description"):
                parts.append(f"<p>{E(op['description'])}</p>")
            if op.get("parameters"):
                parts.append("<h4>Parameters</h4>" + params_table(op["parameters"]))
            rb = op.get("requestBody")
            if rb:
                for ctype, c in rb["content"].items():
                    label = "JSON body" if "json" in ctype else "Form fields (multipart/form-data)"
                    parts.append(f"<h4>{label}</h4>" + fields_table(c.get("schema", {})))
            if (method, path) in CURL:
                parts.append("<h4>Example request</h4>" + code(CURL[(method, path)], "sh"))
            codes = ", ".join(f"<code>{E(k)}</code> {E(v.get('description', ''))}" for k, v in op.get("responses", {}).items())
            parts.append(f"<h4>Responses</h4><p>{codes}</p>")
            key = RESP.get((method, path))
            sample = None
            if key and key in ex:
                sample = {"check": trim_check, "profile": trim_profile, "posts": trim_posts,
                          "model": trim_model, "teams": lambda x: x[:1]}[key](ex[key])
            elif (method, path) in STATIC_RESP:
                sample = STATIC_RESP[(method, path)]
            elif (method, path) == ("get", "/plugins/panel-example"):
                sample = panel_example().model_dump(exclude_none=True)
            if sample is not None:
                parts.append("<h4>Example response</h4>" + code(sample))
            parts.append("</section>")
            body.append("".join(parts))
    return "".join(nav), "".join(body)


def render_schemas() -> tuple[str, str]:
    names = ["Panel", "PanelMetric", "PanelItem", "PanelChart", "PanelPoint", "PluginIn", "PluginPatch",
             "TeamIn", "TeamPatch", "ImportIn", "FolderSpec"]
    nav = ['<li class="navtag">Schemas</li>'] + [f'<li><a href="#schema-{n}">{n}</a></li>' for n in names if n in SCHEMAS]
    body = ['<h2 id="schemas">Schemas</h2>']
    for n in names:
        if n not in SCHEMAS:
            continue
        s = SCHEMAS[n]
        body.append(f'<section class="op" id="schema-{n}"><h3><code>{n}</code></h3>'
                    f'<p>{E(s.get("description", ""))}</p>{fields_table(s)}</section>')
    return "".join(nav), "".join(body)


def plugin_guide(ex: dict) -> str:
    chk = trim_check(ex["check"]) if "check" in ex else {"id": 12, "score": 71.0, "verdict": "Borderline"}
    event = {
        "event": "check.completed",
        "api_base": "http://<vibecheck-host>:8000",
        "team": {"id": 1, "name": "Techkriti Design", "instagram_handle": "techkriti.iitk", "other_pages": []},
        "check": {k: chk[k] for k in ("id", "score", "verdict", "verdict_level", "reasons", "plan_style",
                                      "plan_palette", "description", "nearest", "engagement") if k in chk}
                 | {"inspo_urls": ["http://<vibecheck-host>:8000/media/uploads/check_ab12/0_inspo.jpg"]},
    }
    plugin_code = '''# my_plugin.py  ->  run:  uvicorn my_plugin:app --port 8100
from fastapi import FastAPI

app = FastAPI()

@app.post("/hook")
def hook(event: dict):
    check = event.get("check", {})          # for event == "check.completed"
    palette = check.get("plan_palette", [])
    # ... your own data + model here ...
    return {
        "title": "My plugin",
        "summary": "One line about what this panel shows.",
        "metrics": [{"label": "Colours used", "value": len(palette)}],
        "items": [{"ok": True, "text": "Something that fits."},
                  {"ok": False, "text": "Something to fix."}],
        "chart": {"type": "bar", "title": "Share of each colour", "y_label": "%",
                  "points": [{"label": c["hex"], "value": round(100 * c["share"])}
                             for c in palette if isinstance(c, dict)]},
    }'''
    return f"""
<h2 id="plugins-guide">Build a plugin (cross-dev)</h2>
<p>A plugin is your own small web service with <b>one POST endpoint</b>. It runs <i>inside</i> our app:
we send it the data, it returns a <a href="#schema-Panel">Panel</a>, and we draw that panel with our own
components on the Result page (or the Team style page). You do not build a separate app.</p>
<ol class="steps">
<li><b>Write the service.</b> Any language; it must answer within <b>5 seconds</b> with Panel JSON.</li>
<li><b>Register it once:</b> <code>POST /plugins</code> with its URL and where it shows
(<code>"slot": "result"</code> or <code>"profile"</code>). Or use the Plugins page in the app.</li>
<li><b>Done.</b> Every new check calls your URL. Errors and timeouts show as a small note, never break the page.</li>
</ol>
<h3>What we send you</h3>
<p><code>check.completed</code> (slot <code>result</code>), after every check:</p>
{code(event)}
<p><code>profile.viewed</code> (slot <code>profile</code>) sends <code>team</code> and
<code>profile</code> {{ranges, signature_palette, thresholds, trend}} instead of <code>check</code>.
Use <code>api_base</code> to call any endpoint below for more data (posts, features, style profile).</p>
<h3>What you send back</h3>
<p>A <a href="#schema-Panel">Panel</a>. Only <code>title</code> is required.</p>
{code(panel_example().model_dump(exclude_none=True))}
<h3>Minimal plugin (Python)</h3>
{code(plugin_code, "py")}
<p>Full working example: <code>plugins/contrast_checker/app.py</code> in the repo
(<a href="https://github.com/Pro-Nil/vibecheck">github.com/Pro-Nil/vibecheck</a>).</p>
<p class="note"><b>Course rule:</b> a cross-dev plugin needs its own data, adaptive and visualization parts.
Data: what we send plus anything you fetch. Adaptive: your model or rules. Visualization: the Panel's chart,
metrics and items.</p>
"""


CSS = """
:root{--bg:#f7f6f2;--surface:#fff;--s2:#efeee9;--text:#1b1d21;--t2:#565b64;--border:#dcdad3;--accent:#0b63a5;
--get:#0b63a5;--post:#1d7a4f;--patch:#8a5a00;--delete:#b03a1a;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#15171b;--surface:#1d2025;--s2:#262a30;--text:#eceae4;--t2:#a9adb5;
--border:#353a42;--accent:#6cb6ec;--get:#6cb6ec;--post:#5fd39a;--patch:#e5b552;--delete:#ff8a66;color-scheme:dark}}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--accent)}code,pre{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:.88em}
.wrap{display:grid;grid-template-columns:290px minmax(0,1fr);max-width:1240px;margin:0 auto}
nav{position:sticky;top:0;height:100vh;overflow:auto;padding:20px 12px 40px;border-right:1px solid var(--border)}
nav ul{list-style:none;margin:0;padding:0}nav li a{display:block;padding:3px 8px;border-radius:6px;text-decoration:none;
color:var(--text);font-size:.83rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}nav li a:hover{background:var(--s2)}
.navtag{margin:14px 8px 4px;font-weight:700;font-size:.75rem;letter-spacing:.06em;text-transform:uppercase;color:var(--t2)}
main{padding:28px 32px 80px;min-width:0}h1{font-size:2rem;margin:0 0 4px}h2{margin:44px 0 6px;font-size:1.45rem;
padding-top:8px;border-top:1px solid var(--border)}h3{margin:0 0 4px;font-size:1.05rem}h4{margin:16px 0 6px;font-size:.85rem;
text-transform:uppercase;letter-spacing:.05em;color:var(--t2)}
.op{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px 18px;margin:14px 0}
.summary{margin:2px 0 8px;color:var(--t2)}.muted{color:var(--t2)}
.m{display:inline-block;min-width:58px;text-align:center;font:700 .72rem/1.9 ui-monospace,monospace;border-radius:6px;
padding:0 6px;color:#fff;margin-right:6px;vertical-align:1px}
.m.get{background:var(--get)}.m.post{background:var(--post)}.m.patch{background:var(--patch)}.m.delete{background:var(--delete)}
@media (prefers-color-scheme:dark){.m{color:#0d0f12}}
nav .m{min-width:46px;font-size:.62rem;line-height:1.7;margin-right:4px}
table{width:100%;border-collapse:collapse;margin:4px 0 8px;font-size:.9rem}th,td{text-align:left;padding:6px 8px;
border-bottom:1px solid var(--border);vertical-align:top}th{color:var(--t2);font-size:.78rem;text-transform:uppercase}
.req{font-size:.68rem;font-weight:700;color:var(--delete);margin-left:4px}
pre{background:var(--s2);border:1px solid var(--border);border-radius:8px;padding:12px 14px;overflow:auto;max-height:520px;margin:6px 0 10px}
.note{background:var(--s2);border-left:4px solid var(--accent);padding:10px 14px;border-radius:6px}
.steps li{margin:4px 0}.hero p{max-width:75ch}
.quick{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin:16px 0}
.quick div{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:12px 14px}
.quick b{display:block;margin-bottom:2px}
@media (max-width:860px){.wrap{display:block}nav{position:static;height:auto;border-right:0;border-bottom:1px solid var(--border)}
main{padding:20px 16px 60px}}
"""


def build(examples_dir: Path | None, out: Path) -> None:
    ex = load_examples(examples_dir)
    ops_nav, ops_body = render_ops(ex)
    sch_nav, sch_body = render_schemas()
    info = SPEC["info"]
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VibeCheck API</title><style>{CSS}</style></head>
<body><div class="wrap">
<nav aria-label="Contents"><ul>
<li class="navtag">Start</li><li><a href="#top">Overview</a></li><li><a href="#plugins-guide">Build a plugin</a></li>
{ops_nav}{sch_nav}</ul></nav>
<main id="top">
<div class="hero">
<h1>VibeCheck API <span class="muted" style="font-size:1rem">v{E(info['version'])} · OpenAPI {E(SPEC['openapi'])}</span></h1>
<p>VibeCheck learns a design team's visual style from its Instagram feed and scores a designer's plan
(inspiration images + a short description) <b>before</b> they design: a 0–100 vibe-match score, the reasons, and
the team's closest past posts.</p>
<p>Plain JSON over HTTP. No authentication yet. Images are uploaded as <code>multipart/form-data</code>.
In the examples, <code>$API</code> is the server address, e.g. <code>http://localhost:8000</code>
(run it from <a href="https://github.com/Pro-Nil/vibecheck">github.com/Pro-Nil/vibecheck</a>).
A live, clickable version of these docs is at <code>$API/docs</code>; the raw spec is at <code>$API/openapi.json</code>.</p>
</div>
<div class="quick">
<div><b>Score a plan</b><code>POST /teams/{{id}}/checks</code></div>
<div><b>Team's learned style</b><code>GET /teams/{{id}}/style-profile</code></div>
<div><b>Add a plugin</b><code>POST /plugins</code></div>
<div><b>Features of any image</b><code>POST /features</code></div>
</div>
<p class="note">Long jobs (import, retrain) return a <code>job_id</code> at once; poll <code>GET /jobs/{{id}}</code>
until <code>status</code> is <code>done</code> or <code>failed</code>. Scores are 0–100; style features are 0–1.
Errors return <code>{{"detail": "…"}}</code> with a 4xx code (409 = team has no trained model yet).</p>
{plugin_guide(ex)}
{ops_body}
{sch_body}
<p class="muted" style="margin-top:40px">Generated from the API's OpenAPI spec by <code>scripts/build_api_docs.py</code>.</p>
</main></div></body></html>"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"wrote {out} ({len(page) // 1024} KB)")


if __name__ == "__main__":
    build(Path(sys.argv[1]) if len(sys.argv) > 1 else None, ROOT / "docs" / "api.html")
