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

## Try it without any private data: the synthetic demo team

```bash
.venv/Scripts/python scripts/make_demo_team.py      # ~6 min: generates "Demo Studio (synthetic)" into data_demo/ and trains
.venv/Scripts/python scripts/eval_demo_team.py      # held-out test on new briefs
```
Then run the app with `VIBE_DATA_DIR=data_demo`. Demo Studio is an imaginary team with generated posters and simulated
seniors (hidden rules + 10 % inconsistent decisions), so the approval model has enough decided designs to switch on.
It shows the learning loop works; it says nothing about a real team's taste. See [DEMO.md](DEMO.md).

**Or set the same team up from zero through the app** (nothing pre-trained):

```bash
.venv/Scripts/python scripts/export_synthetic_dataset.py   # upload-ready folders in synthetic_dataset/, no training
```
Start the app on an empty data folder (`VIBE_DATA_DIR=data_test`), create the team, and upload the four folders in
Team setup (select all files in each folder, including its `meta.csv`, which adds dates, likes and per-image projects).
`synthetic_dataset/README.md` has the steps; `5_test_kit/` has new posters to check, with the seniors' answers.

## Run it

```bash
python -m venv .venv
.venv/Scripts/python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python scripts/get_fonts.py                 # once: UI fonts into frontend/src/fonts (works offline after)
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
| Adaptive | `model.py`, `augment.py`, `finish.py` | Approval model trained on designs the seniors decided on (leave-one-project-out validated, switches on at 5 accepted + 5 rejected from 3 projects once it beats the on-brand score); finish checks from text detection (EasyOCR), calibrated on team posts; on-brand score: percentile among the team's own posts from CLIP look (near-twins ignored) + colour match against same-topic past posts; a logistic regression (team vs other pages + near-misses) is blended in once ≥ 20 other-page posts exist; text scored against 40 reference descriptions; LAION aesthetic "audience appeal"; ridge regression for likes (model chosen by cross-validation); UMAP style map. Retrains on every import and daily. |
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

### Plugin ideas

**Suggested: Palette Fixer** (slot `result`). When a check is off-brand because of colour, suggest the closest
on-brand swaps (e.g. "replace #8A2BE2 with team coral #FF6F61") and show the gain ("score 34 → 71 if you swap these
2 colours").
- Reads `plan_palette` and `reasons` from the `check.completed` event, fetches the team's signature palette and
  re-scores through `api_base`, so it uses the API in both directions.
- VibeCheck says *what* is wrong; this says *how to fix it*.
- No ML needed: nearest colour in Lab space. Return a `Panel` with `metrics` (old/new score), `items` (the swaps)
  and `chart`.

**Alternatives**
- **Posting-time advisor** (slot `profile`): from the team's posting history and likes, answer "post on Thursday
  at 7 pm, your best slot", with a chart.
- **Caption writer** (slot `result`): draft an Instagram caption and hashtags in the team's tone from the check's
  description and reasons (needs an LLM API key).

**More creative ones** (each fits the existing contract: one webhook, one `Panel` back)
- **Senior Simulator** (`result`): turns the reasons into the feedback a senior would actually say, e.g. "Love the
  layout, but that purple isn't us. Coral or teal?". Rule-based templates per reason, so no LLM is needed; an LLM
  version is optional. Good for a laugh in the demo, and it makes the reasons feel human.
- **Doppelgänger Finder** (`result`): "Your poster's closest twin is the Hack Night post from 14 Aug (91%)". Reads
  `nearest`, shows what that twin did differently (colour, text amount) and how many likes it got. Warns when a design
  is *too* close to an old post ("people may think it's a repost").
- **Streak and Badges** (`profile`): a light game for the design team: "3 on-brand checks in a row", "first design
  approved without changes", "palette purist (5 checks, no off-palette colours)". Counts come from `GET /teams/{id}/checks`.
- **Brief-to-Moodboard** (`result`, plan checks): from the plan's description and the team's signature palette, list
  the 4–6 team posts to look at before designing, plus a do/don't list taken from the team's usual ranges.
- **Accessibility Lint** (`result`): extends the finish checklist with colour-blind simulation notes ("the coral
  title on teal is hard to tell apart for red-green colour blindness"), using `plan_palette` and Okabe-Ito style
  checks. Pure maths, no ML.
- **Trend Radar** (`profile`): "this team has been getting darker and busier since August" from the style trend, with
  the posts that started it. A short weekly summary the design head can paste into the group chat.
- **A/B Version Picker** (`result`, final checks with a project): compares every version checked for the same project
  and recommends which one to send to the seniors, with the reason ("v1: same score, but cleaner text area").
- **Festival Countdown Planner** (`profile`): given an event date, lays out a posting plan (teaser, reveal, reminders)
  using the weekdays and post types that got the most likes for this team.

Pick one that the plugin team can finish and demo; a small plugin that works end to end beats an ambitious one that
half works.

Current limits to know before building: the event carries features, not an image URL, so recolouring the actual
poster isn't possible yet; plugin charts are drawn in one colour (see KNOWN_ISSUES.md).

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
