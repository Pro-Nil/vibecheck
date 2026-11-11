"""Synthetic mistake benchmark: which design mistakes does the on-brand score notice, and does it ignore
harmless changes?

Every real team post is held out (with its near-twin series), the on-brand scorer is built from the other
series, and the post is scored as-is and after each edit:

  mistakes (should score LOWER):  wrong colour scheme, hue shift (mild / strong), washed out, grey,
                                  clutter, busy texture, title cut off, low contrast, neon recolour
  harmless (should score the SAME): mirror, heavy JPEG, small resize, 4 % crop, slightly brighter

This is synthetic data made from the team's own posts: it measures sensitivity and robustness, NOT what
the seniors approve. Never tune the scorer on it alone; check every change on scripts/evaluate.py too.

    .venv/Scripts/python scripts/synth_benchmark.py
"""
from __future__ import annotations

import io
import sqlite3
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from vibe import config, features, model  # noqa: E402


# ----------------------------------------------------------------------------- edits
def _lab_transfer(im, mean, std):
    """Reinhard colour transfer: give the image another colour scheme, keep its layout and text."""
    lab = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2LAB).astype(np.float32)
    m, s = lab.reshape(-1, 3).mean(0), lab.reshape(-1, 3).std(0) + 1e-6
    out = (lab - m) / s * std + mean
    return Image.fromarray(cv2.cvtColor(np.clip(out, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB))


def wrong_scheme(im, rng):      # warm pastel scheme (pink/peach), far from a dark navy/grey identity
    return _lab_transfer(im, np.array([200, 150, 150], np.float32), np.array([30, 10, 12], np.float32))


def neon(im, rng):              # dark with saturated magenta/green accents
    return _lab_transfer(im, np.array([70, 175, 90], np.float32), np.array([60, 30, 35], np.float32))


def hue(deg):
    def f(im, rng):
        hsv = np.asarray(im.convert("HSV")).copy()
        hsv[..., 0] = (hsv[..., 0].astype(int) + int(deg / 360 * 256)) % 256
        return Image.fromarray(hsv, "HSV").convert("RGB")
    return f


def washed(im, rng):
    return ImageEnhance.Contrast(ImageEnhance.Color(im).enhance(0.3)).enhance(0.7)


def grey(im, rng):
    return ImageOps.grayscale(im).convert("RGB")


def clutter(im, rng):
    im = im.copy()
    d = ImageDraw.Draw(im)
    w, h = im.size
    for _ in range(30):
        x, y = int(rng.integers(0, w)), int(rng.integers(0, h))
        s = int(rng.integers(w // 25 + 1, w // 7 + 2))
        col = tuple(int(c) for c in rng.integers(0, 256, 3))
        (d.rectangle if rng.random() < 0.5 else d.ellipse)([x, y, x + s, y + s], fill=col)
    return im


def busy_texture(im, rng):
    w, h = im.size
    noise = rng.integers(0, 256, (h // 8 + 1, w // 8 + 1, 3)).astype(np.uint8)
    tex = Image.fromarray(noise).resize((w, h), Image.NEAREST)
    return Image.blend(im, tex, 0.35)


def title_cut(im, rng):
    w, h = im.size
    return im.crop((0, int(h * 0.22), w, h)).resize((w, h))


def low_contrast(im, rng):
    return ImageEnhance.Contrast(im).enhance(0.4)


def mirror(im, rng):
    return ImageOps.mirror(im)


def jpeg(im, rng):
    b = io.BytesIO()
    im.save(b, "JPEG", quality=30)
    return Image.open(io.BytesIO(b.getvalue())).convert("RGB")


def small(im, rng):
    w, h = im.size
    return im.resize((360, int(360 * h / w))).resize((w, h))


def crop4(im, rng):
    w, h = im.size
    return im.crop((int(w * .04), int(h * .04), int(w * .96), int(h * .96))).resize((w, h))


def brighter(im, rng):
    return ImageEnhance.Brightness(im).enhance(1.06)


MISTAKES = {"wrong colour scheme": wrong_scheme, "neon recolour": neon, "hue shift 40°": hue(40),
            "hue shift 150°": hue(150), "washed out": washed, "greyscale": grey, "clutter": clutter,
            "busy texture": busy_texture, "title cut off": title_cut, "low contrast": low_contrast}
HARMLESS = {"mirror": mirror, "JPEG quality 30": jpeg, "resized small": small, "4% crop": crop4,
            "6% brighter": brighter}


# ----------------------------------------------------------------------------- run
def series_of(clip, sim=model.TWIN_SIM):
    n = len(clip)
    g = np.arange(n)
    S = clip @ clip.T
    for i in range(n):
        for j in np.where(S[i] > sim)[0]:
            g[g == g[j]] = g[i]
    return g


def run(team_id: int = 1, limit: int | None = None, seed: int = 0, scorer_factory=None):
    c = sqlite3.connect(config.DATA_DIR / "vibecheck.db")
    from vibe.features import STYLE_KEYS
    rows = c.execute("select p.id, p.image_path, f.clip, f.hist, " + ", ".join(f"f.{k}" for k in STYLE_KEYS)
                     + " from posts p join features f on f.post_id=p.id "
                     "where p.team_id=? and p.label='team' order by p.id", (team_id,)).fetchall()
    clip = np.stack([np.frombuffer(r[2], np.float32) for r in rows])
    hist = np.stack([np.frombuffer(r[3], np.float32) for r in rows])
    style = np.array([r[4:] for r in rows], np.float32)
    group = series_of(clip)
    idx = list(range(len(rows)))[:limit]
    rng = np.random.default_rng(seed)
    edits = {**MISTAKES, **HARMLESS}
    imgs, owner, kind = [], [], []
    for i in idx:
        im = features.load_image(config.DATA_DIR / rows[i][1])
        im.thumbnail((720, 900))
        for name, f in edits.items():
            imgs.append(f(im, rng))
            owner.append(i)
            kind.append(name)
    vecs = features.embed_images(imgs)
    hists = np.stack([features.colour_hist(x) for x in imgs])
    styles = np.array([[features.style_features(x, v)[k] for k in STYLE_KEYS] for x, v in zip(imgs, vecs)], np.float32)
    factory = scorer_factory or (lambda C, H, S: model._OnBrand(C, H, S))
    cache, orig, edited = {}, {}, {}
    for j, (i, name) in enumerate(zip(owner, kind)):
        g = group[i]
        if g not in cache:
            ref = group != g
            cache[g] = factory(clip[ref], hist[ref], style[ref])
        ob = cache[g]
        if i not in orig:
            orig[i] = 100 * ob.parts(clip[i], hist[i], style[i])["on_brand"]
        edited[(i, name)] = 100 * ob.parts(vecs[j], hists[j], styles[j])["on_brand"]
    return orig, edited, edits


def report(orig, edited, th):
    o = np.array(list(orig.values()))
    print(f"{len(o)} real team posts, each held out with its series. Lines: Off-brand < {th['borderline']}, "
          f"On-brand >= {th['approve']}. Originals: {np.mean(o < th['borderline']):.0%} Off-brand, "
          f"median score {np.median(o):.0f}\n")
    print(f"{'edit':22s} {'median score':>12s} {'scored lower':>13s} {'now Off-brand':>14s} {'verdict changed':>16s}")
    res = {}
    for kind_name, group in (("MISTAKES (should drop)", MISTAKES), ("HARMLESS (should stay)", HARMLESS)):
        print(kind_name)
        for name in group:
            e = np.array([edited[(i, name)] for i in orig])
            tier = lambda v: np.digitize(v, [th["borderline"], th["approve"]])
            lower = np.mean(e < o - 1)
            off = np.mean((e < th["borderline"]) & (o >= th["borderline"])) / max(1e-9, np.mean(o >= th["borderline"]))
            changed = np.mean(tier(e) != tier(o))
            res[name] = {"median": float(np.median(e)), "lower": float(lower), "off": float(off), "changed": float(changed)}
            print(f"  {name:20s} {np.median(e):12.0f} {lower:13.0%} {off:14.0%} {changed:16.0%}")
    return res


if __name__ == "__main__":
    _, art = model.latest(1)
    o, e, _ = run(1)
    report(o, e, art["thresholds"])
