"""Typography and finish checks for a FINISHED design (not for inspiration images).

Text is found with EasyOCR's text detector (CRAFT; only boxes are needed, nothing is read). For every
image we keep a small "typography" summary, so the team's usual habits (how much text, how big the
headline, how close text sits to the edge) are learned from its posts like the other style features.

The finish checks are about whether a design is ready to post: legibility (contrast of text against
what is behind it, WCAG ratio), how much text and how big the headline is, resolution and shape. All but
resolution are calibrated on the team's own posts so they do not flag what the team routinely does.
"""
from __future__ import annotations

import os
import threading
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image

from . import config

WORK_W = 540                 # images are measured at this width
MIN_CONTRAST = 3.0           # WCAG AA for large text
MIN_WIDTH = 1080             # Instagram's full-quality width
EDGE_FRAC = 0.03             # used by the approval model's inputs only
TYPO_KEYS = ("text_area", "n_lines", "headline", "smallest", "min_contrast", "edge_margin", "aspect")
TYPO_LABELS = {"text_area": "Area covered by text", "n_lines": "Number of text blocks",
               "headline": "Headline size", "smallest": "Smallest text size",
               "edge_margin": "Text distance from the edge"}
_lock = threading.Lock()


@lru_cache(maxsize=1)
def _reader():
    if config.FAKE_CLIP or os.environ.get("VIBE_OCR") == "0":
        return None
    try:
        import easyocr
        with _lock:
            return easyocr.Reader(["en"], gpu=False, verbose=False, recognizer=False)
    except Exception:
        return None


def _fallback_boxes(rgb: np.ndarray) -> list[list[float]]:
    """Cheap text-like region finder (tests and machines without EasyOCR): strong local gradients
    merged horizontally into line-shaped blobs."""
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    grad = cv2.morphologyEx(g, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
    _, bw = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (15, 3)))
    n, _, stats, _ = cv2.connectedComponentsWithStats(bw)
    h, w = g.shape
    out = []
    for x, y, bw_, bh, area in stats[1:]:
        if 6 <= bh <= h * 0.25 and bw_ >= 2 * bh and area > 0.35 * bw_ * bh:
            out.append([x, x + bw_, y, y + bh])
    return out


def detect_text(img: Image.Image) -> tuple[np.ndarray, list[list[float]]]:
    """(RGB array at WORK_W wide, boxes [x0, x1, y0, y1] in that array's pixels)."""
    im = img.convert("RGB")
    h = max(1, int(round(WORK_W * im.height / im.width)))
    rgb = np.asarray(im.resize((WORK_W, h)))
    r = _reader()
    if r is None:
        return rgb, _fallback_boxes(rgb)
    try:
        with _lock:
            boxes = r.detect(rgb)[0][0]
        return rgb, [[float(v) for v in b] for b in boxes]
    except Exception:
        return rgb, _fallback_boxes(rgb)


def _lum(rgb: np.ndarray) -> np.ndarray:
    """WCAG relative luminance (0..1) per pixel."""
    c = rgb.astype(np.float32) / 255.0
    c = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2]


def box_contrast(rgb: np.ndarray, box) -> float:
    """WCAG contrast ratio between the two tones inside a text box (letters vs what is behind them).
    Pixels are split into a light and a dark group (Otsu); the ratio of their mean luminance is used."""
    x0, x1, y0, y1 = (int(round(v)) for v in box)
    patch = rgb[max(0, y0):max(y0 + 1, y1), max(0, x0):max(x0 + 1, x1)]
    if patch.size < 12:
        return 21.0
    L = _lum(patch).reshape(-1)
    g = (L * 255).astype(np.uint8)
    t, _ = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    hi, lo = L[g > t], L[g <= t]
    if len(hi) < 3 or len(lo) < 3:
        return 1.0
    return float((hi.mean() + 0.05) / (lo.mean() + 0.05))


def typography(img: Image.Image) -> dict:
    rgb, boxes = detect_text(img)
    h, w = rgb.shape[:2]
    out = {"aspect": round(img.width / img.height, 4), "width": img.width, "height": img.height,
           "boxes": [[round(v / w, 4) if i < 2 else round(v / h, 4) for i, v in enumerate(b)] for b in boxes[:60]]}
    if not boxes:
        out.update({"text_area": 0.0, "n_lines": 0.0, "headline": 0.0, "smallest": None,
                    "min_contrast": None, "edge_margin": None, "contrasts": []})
        return out
    b = np.array(boxes, float)
    bw, bh = (b[:, 1] - b[:, 0]) / w, (b[:, 3] - b[:, 2]) / h
    contrasts = [box_contrast(rgb, x) for x in boxes[:60]]
    edge = np.minimum(b[:, 0] / w, 1 - b[:, 1] / w)
    out.update({"text_area": float(np.clip((bw * bh).sum(), 0, 1)), "n_lines": float(min(len(b), 40) / 40),
                "headline": float(bh.max()), "smallest": float(bh.min()),
                "min_contrast": float(min(contrasts)), "edge_margin": float(max(0.0, edge.min())),
                "contrasts": [round(c, 2) for c in contrasts]})
    return out


# ------------------------------------------------------------------ layout, typeface, clutter
# Measured from the image plus the text boxes already found above, so older images do not need the slow text
# detector again. Bump LAYOUT_VERSION when these change: training recomputes them for older posts.
LAYOUT_VERSION = 1
LAYOUT_KEYS = ("title_center", "stroke", "stroke_var", "outline", "small_text", "small_shapes")
LAYOUT_LABELS = {"title_center": "Title alignment (0 centred, 1 at the edge)", "stroke": "Title stroke weight",
                 "stroke_var": "Title stroke unevenness", "outline": "Title letter-outline complexity",
                 "small_text": "Small text fragments", "small_shapes": "Small separate shapes"}


def _title_boxes(b: np.ndarray) -> np.ndarray:
    """The headline: the tallest text box plus any other line nearly as tall (a title set on two lines)."""
    bh = b[:, 3] - b[:, 2]
    return b[bh >= 0.7 * bh.max()]


def _ink(patch: np.ndarray) -> np.ndarray | None:
    """Letter pixels in a text box: the tone that differs from the box's border (the background)."""
    g = cv2.cvtColor(patch, cv2.COLOR_RGB2GRAY)
    if g.size < 60:
        return None
    _, bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    border = np.concatenate([bw[0], bw[-1], bw[:, 0], bw[:, -1]])
    ink = bw == 0 if border.mean() > 127 else bw == 255
    return ink if 0.03 < ink.mean() < 0.85 else None


def _type_metrics(rgb: np.ndarray, title: np.ndarray) -> dict:
    """Stroke weight, stroke unevenness and outline complexity of the headline letters.

    A heavy sans has thick, even strokes and simple outlines; serif, script and comic faces have thinner or more
    uneven strokes and busier outlines. Measured with a distance transform on the letter pixels."""
    widths, perim, area, heights = [], 0.0, 0.0, []
    for x0, x1, y0, y1 in title.astype(int):
        patch = rgb[max(0, y0):y1, max(0, x0):x1]
        ink = _ink(patch) if patch.size else None
        if ink is None:
            continue
        m = ink.astype(np.uint8)
        dt = cv2.distanceTransform(m, cv2.DIST_L2, 3)
        ridge = (dt >= cv2.dilate(dt, np.ones((3, 3), np.uint8))) & (m > 0) & (dt >= 1)
        widths += list(2 * dt[ridge])
        cs, _ = cv2.findContours(m, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
        perim += sum(cv2.arcLength(c, True) for c in cs)
        area += float(m.sum())
        heights.append(max(1, y1 - y0))
    if len(widths) < 10 or area < 30:
        return {"stroke": None, "stroke_var": None, "outline": None}
    w = np.array(widths)
    h = float(np.median(heights))
    return {"stroke": float(np.median(w) / h), "stroke_var": float(w.std() / max(w.mean(), 1e-6)),
            "outline": float(perim / np.sqrt(area) / max(1, len(heights)))}


def _small_shapes(rgb: np.ndarray, boxes: np.ndarray) -> int:
    """Small separate shapes (stickers, dots, badges) away from text: blobs that stand out from their
    surroundings, between ~0.03 % and 1 % of the image."""
    small = cv2.resize(rgb, (270, max(1, int(270 * rgb.shape[0] / rgb.shape[1]))), interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(small, cv2.COLOR_RGB2LAB).astype(np.float32)
    bg = cv2.medianBlur(small, 31)
    diff = np.linalg.norm(lab - cv2.cvtColor(bg, cv2.COLOR_RGB2LAB).astype(np.float32), axis=2)
    mask = (diff > 28).astype(np.uint8)
    sx, sy = small.shape[1] / rgb.shape[1], small.shape[0] / rgb.shape[0]
    for x0, x1, y0, y1 in boxes:                       # text is counted separately
        mask[int(y0 * sy):int(np.ceil(y1 * sy)) + 1, int(x0 * sx):int(np.ceil(x1 * sx)) + 1] = 0
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    total = mask.shape[0] * mask.shape[1]
    return int(sum(1 for a in stats[1:, cv2.CC_STAT_AREA] if 0.0003 * total <= a <= 0.01 * total))


def layout(img: Image.Image, typo: dict) -> dict:
    """Layout, typeface and clutter measures for one image, using the text boxes in `typo`."""
    im = img.convert("RGB")
    h = max(1, int(round(WORK_W * im.height / im.width)))
    rgb = np.asarray(im.resize((WORK_W, h)))
    boxes = np.array([[b[0] * WORK_W, b[1] * WORK_W, b[2] * h, b[3] * h] for b in (typo.get("boxes") or [])], float)
    out = {"lv": LAYOUT_VERSION, "title_center": None, "stroke": None, "stroke_var": None, "outline": None,
           "small_text": 0.0, "small_shapes": float(min(_small_shapes(rgb, boxes.reshape(-1, 4)), 60)) / 60}
    if len(boxes):
        title = _title_boxes(boxes)
        cx = ((title[:, 0] + title[:, 1]) / 2).mean() / WORK_W
        out["title_center"] = float(min(1.0, abs(cx - 0.5) * 2))
        out.update(_type_metrics(rgb, title))
        th = (title[:, 3] - title[:, 2]).max()
        out["small_text"] = float(min(int(((boxes[:, 3] - boxes[:, 2]) < 0.45 * th).sum()), 40)) / 40
    return out


def typography_full(img: Image.Image) -> dict:
    """typography() plus layout(): everything stored per image."""
    t = typography(img)
    t.update(layout(img, t))
    return t


# ------------------------------------------------------------------ team habits + checks
# Every check is calibrated on the team's own posted designs: a check that would flag many of the
# team's approved posts is wrong for this team. (First version used fixed rules; on Techkriti's
# posts "low contrast" fired on 72 %, "small text" on 54 %, "text near the edge" on 58 %. Smallest-text
# and edge checks were dropped: small print at the edges is part of this team's style, and the text
# detector cannot see text below ~1 % of the height anyway.)

def _weak_share(t: dict) -> float | None:
    cs = t.get("contrasts") or []
    return float(np.mean([c < MIN_CONTRAST for c in cs])) if cs else None


def _headline_contrast(t: dict) -> float | None:
    boxes, cs = t.get("boxes") or [], t.get("contrasts") or []
    if not boxes or not cs:
        return None
    hs = [b[3] - b[2] for b in boxes[:len(cs)]]
    return float(cs[int(np.argmax(hs))])


def team_ranges(typos: list[dict]) -> dict:
    typos = [t for t in typos if t]
    cols = {k: [t.get(k) for t in typos] for k in ("text_area", "n_lines", "headline", "aspect", "edge_margin") + LAYOUT_KEYS}
    cols["weak_share"] = [_weak_share(t) for t in typos]
    cols["headline_contrast"] = [_headline_contrast(t) for t in typos]
    out = {}
    for k, raw in cols.items():
        vals = np.array([v for v in raw if v is not None], float)
        if len(vals) >= 5:
            out[k] = {"p10": float(np.percentile(vals, 10)), "p50": float(np.percentile(vals, 50)),
                      "p90": float(np.percentile(vals, 90)), "n": int(len(vals))}
    asp = np.array([t["aspect"] for t in typos if t.get("aspect")], float)
    if len(asp) >= 5:   # shapes the team actually uses (each on >= 10 % of its posts)
        shapes = []
        for a in asp:
            if not any(abs(a - s) <= 0.03 for s in shapes) and np.mean(np.abs(asp - a) <= 0.03) >= 0.10:
                shapes.append(float(a))
        out["shapes"] = shapes
    return out


def _p(v: float) -> str:
    return f"{100 * v:.1f}%" if v < 0.1 else f"{100 * v:.0f}%"


def checks(t: dict, ranges: dict) -> list[dict]:
    """Finish checklist for one final design. Each item: ok, feature, label, text, severity."""
    items = []

    def add(ok, feature, label, text, severity="warn"):
        items.append({"ok": bool(ok), "feature": feature, "label": label, "text": text,
                      "severity": "ok" if ok else severity})

    # legibility: the headline, then low-contrast text overall, both against the team's own posts
    hc, r = _headline_contrast(t), ranges.get("headline_contrast")
    if hc is not None and r is not None:
        bad = hc < min(MIN_CONTRAST, r["p10"])
        add(not bad, "headline_contrast", "Headline legibility",
            f"The biggest text stands out from its background (contrast {hc:.1f}:1)." if not bad else
            f"The biggest text is hard to read: contrast {hc:.1f}:1 against what is behind it. WCAG asks for 3:1, "
            f"and 90% of this team's posts manage at least {r['p10']:.1f}:1. Darken or lighten it, or add a backing shape.",
            "fail")
    ws, r = _weak_share(t), ranges.get("weak_share")
    if ws is not None and r is not None:
        bad = ws > max(r["p90"], 0.2)
        n = len(t.get("contrasts") or [])
        add(not bad, "legibility", "Low-contrast text",
            f"{round(ws * n)} of {n} text blocks are low-contrast; normal for this team (up to {_p(r['p90'])} of blocks)."
            if not bad else
            f"{round(ws * n)} of {n} text blocks are low-contrast (under 3:1). That is more than 90% of this team's "
            f"posts (they stay under {_p(r['p90'])}).")
    # how much text / headline size vs the team
    for k, more, less in (("text_area", "more text", "less text"), ("headline", "a bigger headline", "a smaller headline")):
        r = ranges.get(k)
        if r is None or t.get(k) is None:
            continue
        v = t[k]
        inside = r["p10"] * 0.8 <= v <= r["p90"] * 1.2
        add(inside, k, TYPO_LABELS[k],
            f"{TYPO_LABELS[k]} fits: yours {_p(v)}, this team usually {_p(r['p10'])}-{_p(r['p90'])}." if inside else
            f"{TYPO_LABELS[k]}: yours {_p(v)}, this team usually {_p(r['p10'])}-{_p(r['p90'])} "
            f"(your design has {more if v > r['p50'] else less} than usual).")
    # resolution (of the file you export; downloaded posts are smaller, so this one is a fixed rule)
    add(t["width"] >= MIN_WIDTH, "resolution", "Resolution",
        f"{t['width']}×{t['height']} px: sharp on Instagram." if t["width"] >= MIN_WIDTH else
        f"Only {t['width']} px wide; Instagram shows posts at 1080 px, so it will look soft. Export at 1080 px or more.")
    shapes = ranges.get("shapes")
    if shapes:
        ok = any(abs(t["aspect"] - s) <= 0.03 for s in shapes)
        names = ", ".join(_ratio(s) for s in shapes)
        add(ok, "aspect", "Shape",
            f"{_ratio(t['aspect'])}, a shape this team uses ({names})." if ok else
            f"Your design is {_ratio(t['aspect'])}; this team posts {names}. Instagram will crop or letterbox it.")
    order = {"fail": 0, "warn": 1, "ok": 2}
    return sorted(items, key=lambda i: order[i["severity"]])


def _ratio(a: float) -> str:
    for name, v in (("4:5", 0.8), ("1:1", 1.0), ("3:4", 0.75), ("9:16", 0.5625), ("16:9", 1.7778), ("1.91:1", 1.91)):
        if abs(a - v) < 0.02:
            return name
    return f"{a:.2f}:1"
