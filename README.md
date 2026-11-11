# VibeCheck

Learns a design team's visual style from its Instagram feed and tells a new designer, **before they design**,
how well their plan (inspiration images + a short description) fits that style: a 0–100 score, the reasons,
and the team's closest past posts.

FDE1 course project (IIT Kanpur, 2026-27).

> **Status:** the pipeline, API, plugin system and dashboards work end to end. The model does **not** yet
> separate posters the team accepts from ones it rejects; with the data available so far both score about the
> same. See [KNOWN_ISSUES.md](KNOWN_ISSUES.md) for everything that fails, the evidence, and what to improve.

## Run it

```bash
python -m venv .venv
.venv/Scripts/python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
.venv/Scripts/python -m pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
.venv/Scripts/python -m uvicorn vibe.main:app --app-dir backend --port 8000
```

Open http://localhost:8000 (app) and http://localhost:8000/docs (API docs). The first run downloads the
CLIP model (~350 MB) once.

Frontend development with hot reload: `cd frontend && npm run dev` → http://localhost:5173 (calls the API on :8000).

## Getting data in

1. **Team setup → Import from Instagram.** Enter the team page and the "other pages" (posts that are *not* our vibe).
   Instagram often blocks anonymous downloads. If the job says so, log in once yourself:
   ```bash
   .venv/Scripts/instaloader --login YOUR_USERNAME
   ```
   then start the server with `VIBE_IG_SESSION_USER=YOUR_USERNAME` set, and import again.
2. **Team setup → Upload images**: pick many files, say whether they are team posts, other pages' posts, or rejected drafts.
3. **API with a folder**: `POST /teams/{id}/import` with `{"fetch_instagram": false, "folders": [{"path": "C:/posts", "label": "team"}]}`.
   A `meta.csv` (`filename,caption,posted_at,likes,comments`) or Instaloader's `.json.xz` files next to the images are read for likes and dates.

Every import computes features, makes near-miss images and retrains. A scheduler re-fetches new posts and retrains daily at 03:00
(`VIBE_SCHEDULER=0` turns it off, `VIBE_REFRESH_HOUR` changes the hour).

## How it works

| Component | Where | What |
|---|---|---|
| Data (ETL) | `backend/vibe/importers.py`, `pipeline.py` | Instaloader / folders / uploads → images + likes + dates → SQLite (`data/vibecheck.db`) |
| Features | `features.py` | CLIP ViT-B/32 embedding (512 numbers) + 8 readable style features (brightness, saturation, warmth, text amount, busyness, empty space, contrast, illustration) + 5-colour palette |
| Adaptive | `model.py`, `augment.py` | Logistic regression (team vs other pages + near-misses) + nearest-neighbour similarity percentile; text scored against team vs other posts; thresholds set from a 20% hold-out; ridge regression for engagement; UMAP style map. Retrains on every import and daily. |
| Visualization | `frontend/src/pages` | Result (gauge, reasons, feature strips, palettes, nearest posts), Team style (model health, style map, palette, ranges, trend, what gets likes) |
| App | `frontend/` (React + Vite + Recharts) | Check my idea, Result, History (record seniors' decisions), Team setup, Plugins |
| Developer API | `main.py`, `/docs`, `/openapi.json` | REST + OpenAPI 3; plugins register a webhook and return a `Panel` that we draw inside our pages |

Real rejected drafts are never trained on; they only test the model (shown as "real rejected drafts caught").

## Plugins (for cross-dev teams)

1. Build a small HTTP service with one POST endpoint.
2. Register it: `POST /plugins {"name": "...", "url": "http://host:port/hook", "slot": "result" | "profile"}` (or on the Plugins page).
3. We POST `{"event": "check.completed", "check": {...score, reasons, plan_style, plan_palette, nearest...}, "team": {...}, "api_base": "..."}`
   (or `profile.viewed`) and draw the `Panel` you return within 5 s: `title`, optional `summary`, `metrics`, `items`, `chart`.
   See `GET /plugins/panel-example` and the `Panel` schema in `/docs`. Your service may call any of our endpoints using `api_base`.

Example: `plugins/contrast_checker/app.py` (run on port 8100).

## Tests

```bash
.venv/Scripts/python -m pytest backend/tests -q
```
Tests use a stand-in for CLIP (`VIBE_FAKE_CLIP=1`) and synthetic posters, so they run offline in seconds.

## Third-party

CLIP weights (OpenAI, via open_clip), PyTorch, FastAPI, SQLAlchemy, scikit-learn, OpenCV, Pillow, UMAP, Instaloader
(downloading Instagram is against Instagram's terms; used at small scale for a course project), APScheduler, React, Vite, Recharts.
