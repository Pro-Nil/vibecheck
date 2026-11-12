"""Build "Demo Studio (synthetic)": an imaginary design team with generated posters and simulated senior
decisions, so every part of VibeCheck (including the approval model, which needs many decided designs)
can be shown working. Everything is generated from a seed, so anyone can rebuild it; nothing is real.

What is generated
  * House style (what the team posts): deep navy or warm off-white background, coral + teal accents,
    heavy sans-serif title left-aligned near the top, one big accent circle or stripe, date block bottom
    left, small "DEMO STUDIO" mark bottom right, lots of empty space. Small natural variation.
  * Posting history: 90 posts, Mar-Nov 2026, with likes (simulated audience).
  * Other pages: 60 posts from imaginary other clubs in other styles.
  * 40 briefs, each with 3 versions. Each version may break 0-2 house rules. Simulated seniors give every
    version a penalty from HIDDEN weights + noise, accept the best version and any other close to ideal,
    and 10 % of decisions are flipped (seniors are not perfectly consistent).
  * A live-demo kit: 3 NEW briefs (not imported) with versions and the seniors' verdicts, for the demo.

The model never sees SENIOR_WEIGHTS; it has to learn the taste from decisions. Remember when presenting:
this shows the learning loop works on a team with consistent rules we invented, not how well it predicts
a real team.

    .venv/Scripts/python scripts/make_demo_team.py            # builds into data_demo/ (port 8001 config)
    VIBE_DATA_DIR=some/dir .venv/Scripts/python scripts/make_demo_team.py
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("VIBE_DATA_DIR", str(ROOT / "data_demo"))
os.environ.setdefault("VIBE_SCHEDULER", "0")
sys.path.insert(0, str(ROOT / "backend"))

W, H = 540, 675  # 4:5, half of 1080x1350
TEAM_NAME = "Demo Studio (synthetic)"

# ----------------------------------------------------------------------------- fonts
_FONT_CANDIDATES = {
    "heavy": ["ariblk.ttf", "Arial Black.ttf", "impact.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"],
    "sans": ["arial.ttf", "Arial.ttf", "calibri.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"],
    "serif": ["georgia.ttf", "Georgia.ttf", "times.ttf", "DejaVuSerif.ttf", "LiberationSerif-Regular.ttf"],
    "comic": ["comicbd.ttf", "comic.ttf", "Comic Sans MS.ttf", "DejaVuSans-Oblique.ttf"],
    "script": ["Gabriola.ttf", "palai.ttf", "DejaVuSerif-Italic.ttf"],
}
_FONT_DIRS = [Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu"), Path("/usr/share/fonts/truetype/liberation"),
              Path("/Library/Fonts"), Path("/System/Library/Fonts/Supplemental")]


def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    for name in _FONT_CANDIDATES[kind]:
        for d in _FONT_DIRS:
            if (d / name).exists():
                return ImageFont.truetype(str(d / name), size)
    return ImageFont.load_default(size)


# ----------------------------------------------------------------------------- poster spec
HOUSE_BG = [(20, 33, 61), (24, 38, 70), (244, 239, 230), (240, 234, 222)]   # navy x2, off-white x2
CORAL, TEAL = (255, 107, 74), (46, 196, 182)
OFF_PALETTES = [((255, 214, 232), (186, 120, 255), (90, 60, 140)),       # pastel pink / purple
                ((10, 10, 10), (57, 255, 20), (255, 0, 200)),            # neon on black
                ((255, 230, 0), (230, 30, 30), (20, 20, 200)),           # primary red/yellow/blue
                ((120, 90, 60), (200, 170, 120), (60, 40, 20))]          # brown/beige
TOPICS = ["HACK NIGHT", "AI TALK", "ROBO WARS", "DESIGN SPRINT", "CODE CAMP", "OPEN MIC", "STARTUP 101",
          "DATA DAY", "GAME JAM", "CYBER WEEK", "SPACE QUIZ", "MAKER FAIR", "WEB DEV 101", "PITCH NIGHT",
          "ML WORKSHOP", "ARDUINO LAB", "UX CLINIC", "QUANT TALK", "CTF FINALS", "DRONE RACE"]
RULES = ["off_palette", "wrong_font", "centered", "small_title", "clutter", "low_contrast", "no_accent", "busy_bg",
         "cramped"]
# The simulated seniors' taste. The model never sees these numbers.
SENIOR_WEIGHTS = {"off_palette": 1.6, "small_title": 1.4, "low_contrast": 1.3, "clutter": 1.1, "wrong_font": 1.0,
                  "busy_bg": 0.9, "cramped": 0.8, "centered": 0.5, "no_accent": 0.4}


def random_spec(rng, topic: str, breaks: list[str] = ()) -> dict:
    bg = HOUSE_BG[int(rng.integers(len(HOUSE_BG)))]
    dark = bg[0] < 128
    s = {"topic": topic, "bg": bg, "dark": dark, "accent": [CORAL, TEAL][int(rng.integers(2))],
         "accent2": [TEAL, CORAL][int(rng.integers(2))], "title_font": "heavy", "align": "left",
         "title_size": int(rng.integers(62, 84)), "accent_shape": ["circle", "stripe"][int(rng.integers(2))],
         "clutter": 0, "busy_bg": False, "margin": int(rng.integers(36, 52)),
         "text": (244, 239, 230) if dark else (20, 33, 61), "seed": int(rng.integers(1 << 30)),
         "date": f"{int(rng.integers(1, 29))} {['MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV'][int(rng.integers(9))]}",
         "venue": ["L-7 HALL", "CC LAWNS", "OAT", "LHC 101", "KD LAB"][int(rng.integers(5))], "breaks": list(breaks)}
    for b in breaks:
        if b == "off_palette":
            p = OFF_PALETTES[int(rng.integers(len(OFF_PALETTES)))]
            s["bg"], s["accent"], s["accent2"] = p
            s["dark"] = p[0][0] < 128
            s["text"] = (250, 250, 250) if s["dark"] else (30, 30, 30)
        elif b == "wrong_font":
            s["title_font"] = ["serif", "comic", "script"][int(rng.integers(3))]
        elif b == "centered":
            s["align"] = "center"
        elif b == "small_title":
            s["title_size"] = int(rng.integers(26, 36))
        elif b == "clutter":
            s["clutter"] = int(rng.integers(14, 26))
        elif b == "low_contrast":
            s["text"] = tuple(int(0.8 * c + 0.2 * (255 - c)) for c in s["bg"])  # text close to background
        elif b == "no_accent":
            s["accent_shape"] = None
        elif b == "busy_bg":
            s["busy_bg"] = True
        elif b == "cramped":
            s["margin"] = 6
    return s


def render(s: dict) -> Image.Image:
    rng = np.random.default_rng(s["seed"])
    im = Image.new("RGB", (W, H), s["bg"])
    d = ImageDraw.Draw(im)
    if s["busy_bg"]:
        for _ in range(60):
            x, y, r = int(rng.integers(0, W)), int(rng.integers(0, H)), int(rng.integers(10, 70))
            col = tuple(int(np.clip(c + rng.integers(-60, 60), 0, 255)) for c in s["bg"])
            d.ellipse([x - r, y - r, x + r, y + r], fill=col)
        im = im.filter(ImageFilter.GaussianBlur(1.5))
        d = ImageDraw.Draw(im)
    # accent shape
    if s["accent_shape"] == "circle":
        r = int(rng.integers(130, 190))
        cx, cy = W - int(rng.integers(20, 110)), int(rng.integers(r + 260, 560))   # below the title block
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=s["accent"])
        d.ellipse([cx - r // 3, cy - r // 3, cx + r // 3, cy + r // 3], fill=s["accent2"])
    elif s["accent_shape"] == "stripe":
        y0 = int(rng.integers(300, 430))
        d.polygon([(0, y0 + 90), (W, y0 - 40), (W, y0 + 30), (0, y0 + 160)], fill=s["accent"])
        d.rectangle([0, y0 + 175, W, y0 + 185], fill=s["accent2"])
    # simple "illustration": a few geometric icons, half the time
    if rng.random() < 0.5:
        x0, y0 = int(rng.integers(60, 200)), int(rng.integers(380, 470))
        for k in range(3):
            d.rectangle([x0 + 50 * k, y0, x0 + 50 * k + 34, y0 + 34], outline=s["text"], width=4)
    # clutter: stickers, stars, extra labels
    for _ in range(s["clutter"]):
        x, y, z = int(rng.integers(0, W - 40)), int(rng.integers(0, H - 40)), int(rng.integers(14, 46))
        col = tuple(int(c) for c in rng.integers(0, 256, 3))
        if rng.random() < 0.5:
            d.ellipse([x, y, x + z, y + z], fill=col)
        else:
            d.text((x, y), ["NEW!", "FREE", "WOW", "!!", "GO"][int(rng.integers(5))], fill=col, font=font("sans", 18))
    # title (wrapped to two lines)
    m = s["margin"]
    f = font(s["title_font"], s["title_size"])
    words = s["topic"].split()
    lines = [" ".join(words[:max(1, len(words) // 2)]), " ".join(words[max(1, len(words) // 2):])]
    y = m + 30
    for line in [l for l in lines if l]:
        tw = d.textlength(line, font=f)
        x = (W - tw) / 2 if s["align"] == "center" else m
        d.text((x, y), line, fill=s["text"], font=f)
        y += int(s["title_size"] * 1.05)
    sub = font("sans", 20)
    tag = "INTRO SESSION · ALL WELCOME"
    d.text(((W - d.textlength(tag, font=sub)) / 2 if s["align"] == "center" else m, y + 12), tag, fill=s["accent"] if not s["dark"] or s["accent"] != s["bg"] else s["text"], font=sub)
    # date block bottom-left, mark bottom-right
    fd = font("heavy", 30)
    d.text((m, H - m - 70), s["date"], fill=s["text"], font=fd)
    d.text((m, H - m - 32), s["venue"] + " · 6 PM", fill=s["text"], font=font("sans", 18))
    mark = "DEMO STUDIO"
    fm = font("heavy", 14)
    d.text((W - m - d.textlength(mark, font=fm), H - m - 18), mark, fill=s["text"], font=fm)
    return im


def other_page_poster(rng, topic: str) -> Image.Image:
    """Posts from imaginary OTHER clubs: different palettes, fonts and layouts."""
    pal = OFF_PALETTES[int(rng.integers(len(OFF_PALETTES)))]
    s = random_spec(rng, topic, breaks=[])
    s.update({"bg": pal[0], "accent": pal[1], "accent2": pal[2], "dark": pal[0][0] < 128,
              "title_font": ["serif", "comic", "script", "sans"][int(rng.integers(4))],
              "align": ["center", "left"][int(rng.integers(2))], "clutter": int(rng.integers(0, 18)),
              "busy_bg": bool(rng.random() < 0.5), "accent_shape": [None, "circle", "stripe"][int(rng.integers(3))]})
    s["text"] = (250, 250, 250) if s["dark"] else (25, 25, 25)
    return render(s)


def senior_penalty(breaks, rng) -> float:
    return sum(SENIOR_WEIGHTS[b] for b in breaks) + float(rng.normal(0, 0.35))


def make_brief(rng, topic: str, n_versions: int = 3, noisy: bool = True) -> list[dict]:
    """Versions of one brief and the seniors' decision on each.

    noisy=True flips 10 % of decisions at random (real seniors are inconsistent), which is right for TRAINING data.
    The test kit uses noisy=False: an answer key must say what the seniors' rules decide. The random draw still
    happens either way, so the generated images are identical."""
    versions = []
    for v in range(n_versions):
        k = int(rng.choice([0, 1, 1, 2, 2], 1)[0]) if v else int(rng.choice([0, 0, 1], 1)[0])
        breaks = list(rng.choice(RULES, k, replace=False)) if k else []
        versions.append({"breaks": breaks, "spec": random_spec(rng, topic, breaks)})
    pen = [senior_penalty(v["breaks"], rng) for v in versions]
    best = int(np.argmin(pen))
    for i, v in enumerate(versions):
        accepted = i == best or pen[i] < 0.6
        if rng.random() < 0.10 and noisy:    # inconsistent seniors (training data only)
            accepted = not accepted
        v["decision"] = "accepted" if accepted else "rejected"
        v["penalty"] = round(pen[i], 2)
    return versions


# ----------------------------------------------------------------------------- build
def build(out_root: Path, seed: int = 7, n_history: int = 90, n_other: int = 60, n_briefs: int = 40):
    rng = np.random.default_rng(seed)
    gen = out_root / "generated"
    if gen.exists():
        shutil.rmtree(gen)
    hist_dir, other_dir, briefs_dir, kit_dir = gen / "history", gen / "other_pages", gen / "briefs", gen / "demo_kit"
    for p in (hist_dir, other_dir, briefs_dir, kit_dir):
        p.mkdir(parents=True)
    # posting history: house style, a few minor slips, dated Mar-Nov 2026, simulated likes
    start = datetime(2026, 3, 1)
    rows = [["filename", "caption", "posted_at", "likes", "comments"]]
    for i in range(n_history):
        topic = TOPICS[int(rng.integers(len(TOPICS)))]
        slips = list(rng.choice(["centered", "no_accent", "cramped"], 1)) if rng.random() < 0.2 else []
        s = random_spec(rng, topic, slips)
        render(s).save(hist_dir / f"post_{i:03d}.png")
        when = start + timedelta(days=int(i * 260 / n_history + rng.integers(0, 3)))
        likes = int(np.exp(rng.normal(5.3 + 0.25 * (s["accent_shape"] == "circle") + 0.003 * s["title_size"]
                                      - 0.3 * bool(slips), 0.35)))
        rows.append([f"post_{i:03d}.png", f"{topic.title()} by Demo Studio", when.strftime("%Y-%m-%d"), likes, int(likes * 0.04)])
    with open(hist_dir / "meta.csv", "w", newline="") as f:
        csv.writer(f).writerows(rows)
    for i in range(n_other):
        other_page_poster(rng, TOPICS[int(rng.integers(len(TOPICS)))]).save(other_dir / f"other_{i:03d}.png")
    # decided briefs
    briefs = []
    for b in range(n_briefs):
        topic = TOPICS[b % len(TOPICS)]
        vs = make_brief(rng, topic)
        for j, v in enumerate(vs):
            fn = briefs_dir / f"brief{b:02d}_v{j}_{v['decision']}.png"
            render(v["spec"]).save(fn)
            v["file"] = fn.name
        briefs.append({"project": f"brief-{b:02d}-{topic.lower().replace(' ', '-')}",
                       "versions": [{k: v[k] for k in ("file", "breaks", "decision", "penalty")} for v in vs]})
    (briefs_dir / "decisions.json").write_text(json.dumps(briefs, indent=1))
    # live-demo kit: 3 NEW briefs, not imported
    kit = []
    for b, topic in enumerate(["NEURAL NIGHTS", "BUILD WEEK", "TECH TALK"]):
        vs = make_brief(rng, topic, n_versions=3, noisy=False)
        for j, v in enumerate(vs):
            fn = kit_dir / f"{topic.lower().replace(' ', '_')}_v{j + 1}.png"
            Image.Image.resize(render(v["spec"]), (1080, 1350), Image.LANCZOS).save(fn)
            kit.append({"file": fn.name, "seniors": v["decision"], "breaks": [str(b) for b in v["breaks"]],
                        "penalty": v["penalty"]})
    (kit_dir / "ANSWERS.json").write_text(json.dumps(kit, indent=1))
    return hist_dir, other_dir, briefs_dir, briefs, kit_dir


def import_and_train(hist_dir, other_dir, briefs_dir, briefs):
    from vibe import importers, pipeline
    from vibe.db import SessionLocal, Team, init_db
    init_db()
    with SessionLocal() as s:
        t = Team(name=TEAM_NAME, instagram_handle=None, other_pages_json="[]")
        s.add(t)
        s.commit()
        tid = t.id
    importers.import_folder(tid, str(hist_dir), "team", "demostudio")
    importers.import_folder(tid, str(other_dir), "other", "other-clubs")
    for b in briefs:
        for v in b["versions"]:
            data = (briefs_dir / v["file"]).read_bytes()
            importers.add_upload(tid, data, v["file"], "team" if v["decision"] == "accepted" else "rejected",
                                 caption=f"{b['project']} version", decision=v["decision"], project=b["project"])
    job = pipeline.new_job("refresh", tid)
    pipeline.run_refresh(job, tid, fetch=False)
    from vibe.db import Job
    with SessionLocal() as s:
        j = s.get(Job, job)
        print(f"job {j.status}: {j.message}")
    return tid


if __name__ == "__main__":
    from vibe import config
    root = config.DATA_DIR
    if (root / "vibecheck.db").exists():
        backup = root.with_name(root.name + "_backup_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
        shutil.move(str(root), str(backup))
        root.mkdir(parents=True)
        for sub in ("images", "raw", "models", "uploads"):
            (root / sub).mkdir(exist_ok=True)
        print(f"moved the old {root.name} to {backup.name}")
    h, o, b, briefs, kit = build(root)
    n_acc = sum(v["decision"] == "accepted" for x in briefs for v in x["versions"])
    print(f"generated: 90 history posts, 60 other-page posts, {len(briefs)} briefs "
          f"({n_acc} accepted / {3 * len(briefs) - n_acc} rejected versions), demo kit in {kit}")
    tid = import_and_train(h, o, b, briefs)
    print(f"team {tid} '{TEAM_NAME}' ready in {root}")
