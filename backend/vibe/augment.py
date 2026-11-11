"""Near-misses: deliberately broken copies of the team's own posts.

They look *almost* like the team's work but with one thing wrong, so the model learns
"close, but not us" instead of only "a completely different page".
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps


def hue_shift(img: Image.Image, rng) -> Image.Image:
    hsv = np.asarray(img.convert("HSV")).copy()
    hsv[..., 0] = (hsv[..., 0].astype(int) + int(rng.integers(70, 186))) % 256
    return Image.fromarray(hsv, "HSV").convert("RGB")


def oversaturate(img, rng):
    return ImageEnhance.Contrast(ImageEnhance.Color(img).enhance(rng.uniform(2.2, 3.2))).enhance(1.3)


def wash_out(img, rng):
    return ImageEnhance.Contrast(ImageEnhance.Color(img).enhance(0.15)).enhance(0.6)


def invert(img, rng):
    return ImageOps.invert(img)


def clutter(img, rng):
    im = img.copy()
    d = ImageDraw.Draw(im)
    w, h = im.size
    for _ in range(int(rng.integers(25, 45))):
        x, y = int(rng.integers(0, w)), int(rng.integers(0, h))
        s = int(rng.integers(w // 30 + 1, w // 6 + 2))
        col = tuple(int(c) for c in rng.integers(0, 256, 3))
        if rng.random() < 0.5:
            d.rectangle([x, y, x + s, y + s // 2], fill=col)
        else:
            d.ellipse([x, y, x + s, y + s], outline=col, width=3)
    for _ in range(int(rng.integers(8, 16))):
        x, y = int(rng.integers(0, w - 10)), int(rng.integers(0, h - 10))
        d.text((x, y), "SALE  NEW  50% OFF  REGISTER NOW", fill=tuple(int(c) for c in rng.integers(0, 256, 3)))
    return im


def bad_crop(img, rng):
    w, h = img.size
    z = rng.uniform(0.35, 0.55)
    cw, ch = int(w * z), int(h * z)
    x, y = int(rng.integers(0, w - cw + 1)), int(rng.integers(0, h - ch + 1))
    return img.crop((x, y, x + cw, y + ch)).resize((w, h))


def blur_flat(img, rng):
    return img.filter(ImageFilter.GaussianBlur(radius=max(2, img.size[0] // 60))).quantize(6).convert("RGB")


def channel_swap(img, rng):
    r, g, b = img.split()
    order = [(b, r, g), (g, b, r), (b, g, r)][int(rng.integers(0, 3))]
    return Image.merge("RGB", order)


TRANSFORMS = {
    "hue_shift": hue_shift, "oversaturate": oversaturate, "wash_out": wash_out, "invert": invert,
    "clutter": clutter, "bad_crop": bad_crop, "blur_flat": blur_flat, "channel_swap": channel_swap,
}


def near_miss(img: Image.Image, seed: int) -> tuple[Image.Image, str]:
    rng = np.random.default_rng(seed)
    name = list(TRANSFORMS)[int(rng.integers(0, len(TRANSFORMS)))]
    im = img.copy()
    im.thumbnail((768, 768))
    return TRANSFORMS[name](im, rng), name
