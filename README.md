# VibeCheck

Learns a design team's visual style from its Instagram feed and tells a new designer, **before they design**,
how well their plan (inspiration images + a short description) fits that style: a 0–100 score, the reasons,
and the team's closest past posts.

FDE1 course project (IIT Kanpur, 2026-27).

> **Status:** the pipeline, API, plugin system and dashboards work end to end. It scores plans *and* finished
> designs. Model v6 ranks the team's real new posts above its rejected drafts (AUC 0.90 on posts it had not seen,
> `scripts/evaluate.py`) and both accepted designs above all 9 rejected drafts (only 2 accepted, 9 rejected, 2 briefs:
> encouraging, not proven). The approval model switches itself on once enough decided designs are recorded.
> See [KNOWN_ISSUES.md](KNOWN_ISSUES.md) for everything that fails, the evidence, and what to improve.

## Two checks

- **Check my idea** (before designing): 1-5 inspiration images and/or a description → on-brand score, reasons,
  closest past posts.
- **Check my design** (after designing): the finished poster → on-brand score of the design itself, a finish
  checklist (headline legibility, low-contrast text, amount of text, headline size, resolution, shape; each
  calibrated on the team's own posts), "plan vs final" when linked to the plan check, and the learned approval
  model once it has enough data. Mark what the seniors decided and that design becomes training data.

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
2. **Team setup → Upload images**: pick many files, say whether they are team posts, other pages' posts, designs the
   seniors accepted, or rejected drafts (with a project name, so versions of one brief can be compared).
   This is the most valuable data: the approval model learns only from decided designs.
3. **API with a folder**: `POST /teams/{id}/import` with `{"fetch_instagram": false, "folders": [{"path": "C:/posts", "label": "team"}]}`.
   A `meta.csv` (`filename,caption,posted_at,likes,comments`) or Instaloader's `.json.xz` files next to the images are read for likes and dates.

Every import computes features, makes near-miss images and retrains. A scheduler re-fetches new posts and retrains daily at 03:00
(`VIBE_SCHEDULER=0` turns it off, `VIBE_REFRESH_HOUR` changes the hour).

## How it works

| Component | Where | What |
|---|---|---|
| Data (ETL) | `backend/vibe/importers.py`, `pipeline.py` | Instaloader / folders / uploads → images + likes + dates → SQLite (`data/vibecheck.db`) |
| Features | `features.py` | CLIP ViT-B/32 embedding of the whole poster (padded to a square, not centre-cropped; 512 numbers) + 8 readable style features (brightness, saturation, warmth, text amount, busyness, empty space, contrast, illustration) + 5-colour palette |
| Adaptive | `model.py`, `augment.py`, `finish.py` | Approval model trained on designs the seniors decided on (leave-one-project-out validated, switches on at 8 accepted + 8 rejected from 3 projects); finish checks from text detection (EasyOCR), calibrated on team posts; on-brand score: percentile among the team's own posts from CLIP look (near-twins ignored) + colour match against same-topic past posts; a logistic regression (team vs other pages + near-misses) is blended in once ≥ 20 other-page posts exist; text scored against 40 reference descriptions; LAION aesthetic "audience appeal"; ridge regression for likes (model chosen by cross-validation); UMAP style map. Retrains on every import and daily. |
| Visualization | `frontend/src/pages` | Result (gauge, reasons, feature strips, palettes, nearest posts), Team style (model health, style map, palette, ranges, trend, what gets likes) |
| App | `frontend/` (React + Vite + Recharts) | Check my idea, Result, History (record seniors' decisions), Team setup, Plugins |
| Developer API | `main.py`, `/docs`, `/openapi.json` | REST + OpenAPI 3; plugins register a webhook and return a `Panel` that we draw inside our pages |

Rejected drafts and accepted designs only train the approval model (validated leaving one project out); the on-brand
score never trains on them. The first run of text detection downloads EasyOCR's detector (~80 MB) once.

## Plugins (for cross-dev teams)

1. Build a small HTTP service with one POST endpoint.
2. Register it: `POST /plugins {"name": "...", "url": "http://host:port/hook", "slot": "result" | "profile"}` (or on the Plugins page).
3. We POST `{"event": "check.completed", "check": {...score, reasons, plan_style, plan_palette, nearest...}, "team": {...}, "api_base": "..."}`
   (or `profile.viewed`) and draw the `Panel` you return within 5 s: `title`, optional `summary`, `metrics`, `items`, `chart`.
   See `GET /plugins/panel-example` and the `Panel` schema in `/docs`. Your service may call any of our endpoints using `api_base`.

Example: `plugins/contrast_checker/app.py` (run on port 8100).

## Evaluate the model on your data

```bash
.venv/Scripts/python scripts/evaluate.py          # add --dino to also test DINOv2
```
`scripts/embed_variants.py` re-embeds the posts with other CLIP set-ups (framing, B-16, L-14) to compare.
`scripts/synth_benchmark.py` checks which realistic mistakes (wrong colours, clutter, cut-off title...) lower the score
and that harmless edits (mirror, JPEG) don't. `scripts/simulate_seniors.py` estimates how many decided designs the
approval model needs (roughly 30-50 briefs).
Scores every month's posts with a model that only knew older posts, and every series with a model built from the
other series, against the rejected drafts. Use it before changing the scorer.

## Tests

```bash
.venv/Scripts/python -m pytest backend/tests -q
```
Tests use a stand-in for CLIP (`VIBE_FAKE_CLIP=1`) and synthetic posters, so they run offline in seconds.

## Third-party

CLIP weights (OpenAI, via open_clip), EasyOCR (CRAFT text detector), LAION aesthetic predictor, PyTorch, FastAPI, SQLAlchemy, scikit-learn, OpenCV, Pillow, UMAP, Instaloader
(downloading Instagram is against Instagram's terms; used at small scale for a course project), APScheduler, React, Vite, Recharts.
