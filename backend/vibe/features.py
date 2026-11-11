"""Turn an image (or a sentence) into numbers.

Two kinds of numbers:
  * a 512-number CLIP embedding: "what it looks like / feels like"; images and text share the space
  * eight hand-made style features, each 0..1, that a person can read ("how bright", "how busy")
"""
from __future__ import annotations

import threading
import zlib
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from . import config

STYLE_KEYS = ("brightness", "saturation", "warmth", "text_amount", "busyness",
              "whitespace", "contrast", "illustration")

# Plain-English names used in the reasons and the charts.
STYLE_LABELS = {
    "brightness": "Brightness",
    "saturation": "Colour saturation",
    "warmth": "Colour warmth",
    "text_amount": "Amount of text",
    "busyness": "Busyness (detail / clutter)",
    "whitespace": "Empty space",
    "contrast": "Contrast",
    "illustration": "Illustration vs photo",
}
# Words for "higher" and "lower" on each feature.
STYLE_WORDS = {
    "brightness": ("brighter", "darker"),
    "saturation": ("more saturated", "more muted"),
    "warmth": ("warmer", "cooler"),
    "text_amount": ("more text-heavy", "lighter on text"),
    "busyness": ("busier", "plainer"),
    "whitespace": ("emptier", "more filled"),
    "contrast": ("higher-contrast", "flatter"),
    "illustration": ("more illustrated", "more photographic"),
}

CLIP_DIM = 512
_lock = threading.Lock()
# Stored CLIP vectors are only comparable when made the same way; posts embedded differently are re-embedded.
EMBED_VERSION = f"{config.CLIP_MODEL}/{config.CLIP_PRETRAINED}/{config.CLIP_FRAMING}" if not config.FAKE_CLIP else "fake"


def pad_square(im: Image.Image) -> Image.Image:
    """Pad to a square with the image's own (median) edge colour, so a centre crop keeps the whole poster."""
    if im.width == im.height:
        return im
    a = np.asarray(im)
    edge = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]]).reshape(-1, 3)
    fill = tuple(int(v) for v in np.median(edge, 0))
    s = max(im.size)
    bg = Image.new("RGB", (s, s), fill)
    bg.paste(im, ((s - im.width) // 2, (s - im.height) // 2))
    return bg


def load_image(path: str | Path) -> Image.Image:
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, img)
    return img.convert("RGB")


# --------------------------------------------------------------------------- CLIP
class _FakeClip:
    """Deterministic stand-in for CLIP: random projection of a tiny thumbnail.
    Used by tests (VIBE_FAKE_CLIP=1) so nothing is downloaded."""

    def __init__(self):
        rng = np.random.default_rng(0)
        self.proj = rng.standard_normal((16 * 16 * 3, CLIP_DIM)).astype(np.float32)
        self.vocab_rng_seed = 1

    def images(self, imgs):
        out = []
        for im in imgs:
            a = np.asarray(im.resize((16, 16)), dtype=np.float32).reshape(-1) / 255.0 - 0.5
            out.append(a @ self.proj)
        return _norm(np.stack(out))

    def texts(self, texts):
        out = []
        for t in texts:
            seed = zlib.crc32(t.encode("utf-8"))
            out.append(np.random.default_rng(seed).standard_normal(CLIP_DIM).astype(np.float32))
        return _norm(np.stack(out))


class _OpenClip:
    def __init__(self):
        import open_clip
        import torch
        self.torch = torch
        torch.set_num_threads(max(1, (torch.get_num_threads() or 4)))
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            config.CLIP_MODEL, pretrained=config.CLIP_PRETRAINED)
        self.model.eval()
        self.tokenizer = open_clip.get_tokenizer(config.CLIP_MODEL)

    def images(self, imgs):
        with self.torch.no_grad():
            if config.CLIP_FRAMING == "pad":
                imgs = [pad_square(im) for im in imgs]
            batch = self.torch.stack([self.preprocess(im) for im in imgs])
            return _norm(self.model.encode_image(batch).float().numpy())

    def texts(self, texts):
        with self.torch.no_grad():
            toks = self.tokenizer(list(texts))
            return _norm(self.model.encode_text(toks).float().numpy())


@lru_cache(maxsize=1)
def clip():
    with _lock:
        return _FakeClip() if config.FAKE_CLIP else _OpenClip()


def _norm(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    return x / (np.linalg.norm(x, axis=-1, keepdims=True) + 1e-8)


def embed_images(imgs: list[Image.Image], batch: int = 32) -> np.ndarray:
    parts = [clip().images(imgs[i:i + batch]) for i in range(0, len(imgs), batch)]
    return np.concatenate(parts) if parts else np.zeros((0, CLIP_DIM), np.float32)


def embed_texts(texts: list[str]) -> np.ndarray:
    return clip().texts(texts)


# Zero-shot prompts: two features come from asking CLIP which description fits better.
_PROMPTS = {
    "text_amount": (["a poster covered in lots of text and small print",
                     "a text-heavy flyer with many lines of words"],
                    ["an image with almost no text", "a picture with no words on it"]),
    "illustration": (["a flat graphic illustration", "a digital vector artwork", "a drawn cartoon poster"],
                     ["a real photograph", "a photo taken with a camera"]),
}


@lru_cache(maxsize=1)
def _prompt_vectors():
    out = {}
    for key, (pos, neg) in _PROMPTS.items():
        p = embed_texts(pos).mean(0)
        n = embed_texts(neg).mean(0)
        out[key] = (p / np.linalg.norm(p), n / np.linalg.norm(n))
    return out


def _zero_shot(vec: np.ndarray, key: str) -> float:
    p, n = _prompt_vectors()[key]
    logit = 100.0 * (float(vec @ p) - float(vec @ n))  # CLIP's usual temperature
    return float(1.0 / (1.0 + np.exp(-logit / 2.0)))


# --------------------------------------------------------------------------- style
def palette(img: Image.Image, k: int = 5) -> list[dict]:
    """The k main colours (k-means on pixels), biggest share first."""
    small = np.asarray(img.resize((64, 64)), dtype=np.float32).reshape(-1, 3)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    cv2.setRNGSeed(0)
    _, labels, centers = cv2.kmeans(small, k, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labels.reshape(-1), minlength=k).astype(float)
    order = np.argsort(-counts)
    return [{"hex": "#%02x%02x%02x" % tuple(int(round(c)) for c in centers[i]),
             "share": round(float(counts[i] / counts.sum()), 3)} for i in order]


def style_features(img: Image.Image, clip_vec: np.ndarray) -> dict:
    im = img.copy()
    im.thumbnail((384, 384))
    rgb = np.asarray(im, dtype=np.float32) / 255.0
    hsv = cv2.cvtColor((rgb * 255).astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)
    gray = cv2.cvtColor((rgb * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)

    brightness = float(hsv[..., 2].mean() / 255.0)
    saturation = float(hsv[..., 1].mean() / 255.0)
    warmth = float(np.clip(0.5 + (rgb[..., 0].mean() - rgb[..., 2].mean()), 0, 1))
    edges = cv2.Canny(gray, 80, 160)
    busyness = float(np.clip((edges > 0).mean() * 5.0, 0, 1))  # 20 % edge pixels = max
    # empty space: share of 16x16 tiles that are nearly flat
    h, w = gray.shape
    tiles = [gray[y:y + 16, x:x + 16] for y in range(0, h - 15, 16) for x in range(0, w - 15, 16)]
    whitespace = float(np.mean([t.std() < 6 for t in tiles])) if tiles else 0.0
    contrast = float(np.clip(gray.std() / 128.0 * 1.5, 0, 1))  # RMS contrast, scaled
    return {
        "brightness": brightness, "saturation": saturation, "warmth": warmth,
        "text_amount": _zero_shot(clip_vec, "text_amount"), "busyness": busyness,
        "whitespace": whitespace, "contrast": contrast,
        "illustration": _zero_shot(clip_vec, "illustration"),
        "palette": palette(img),
    }


HIST_BINS = 4  # per Lab channel -> 64 numbers


def colour_hist(img: Image.Image) -> np.ndarray:
    """Share of the image in each of 4x4x4 Lab colour bins (sums to 1). Captures which colours a
    poster is made of and in what amounts, which CLIP (mostly about subject matter) largely ignores."""
    a = np.asarray(img.resize((96, 120)), np.uint8)
    lab = cv2.cvtColor(a, cv2.COLOR_RGB2LAB)
    h = cv2.calcHist([lab], [0, 1, 2], None, [HIST_BINS] * 3, [0, 256] * 3).reshape(-1)
    return (h / max(1.0, h.sum())).astype(np.float32)


@lru_cache(maxsize=1)
def _aesthetic_weights():
    f = config.ROOT / "models_pretrained" / "laion_aesthetic_vit_b_32.npz"
    if not f.exists():
        return None
    z = np.load(f)
    return z["weight"], float(z["bias"][0])


def aesthetic(clip_vec: np.ndarray) -> float | None:
    """LAION aesthetic score (about 1-10) from a normalised CLIP ViT-B/32 vector. General visual
    appeal as rated by many people; it is NOT the team's taste, so it only feeds the likes model."""
    w = _aesthetic_weights()
    return None if w is None else float(np.asarray(clip_vec, np.float32) @ w[0] + w[1])


def extract(imgs: list[Image.Image]) -> list[dict]:
    """Full features for a list of images: {'clip', style..., 'palette', 'hist', 'aesthetic'}"""
    vecs = embed_images(imgs)
    return [{"clip": v, **style_features(im, v), "hist": colour_hist(im), "aesthetic": aesthetic(v)}
            for im, v in zip(imgs, vecs)]
