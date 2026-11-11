"""Embed every team post and rejected draft with alternative CLIP set-ups, for scripts/evaluate.py.

Variants (name -> how the poster is fed to the model):
  b32_center : the app's v4 set-up (open_clip ViT-B-32, resize + CENTER CROP: a 4:5 poster loses ~10 % top and bottom)
  b32_pad    : pad to a square with the poster's own edge colour first, so the whole poster is seen
  b32_crops  : mean of three square crops (top, middle, bottom)
  b16_pad / l14_pad : bigger CLIP models (ViT-B-16, ViT-L-14, OpenAI weights), padded

    .venv/Scripts/python scripts/embed_variants.py b32_pad b32_crops l14_pad
Results are cached in data/eval_variants.npz (keyed by post id).
"""
from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from vibe import config, features  # noqa: E402

OUT = ROOT / "data" / "eval_variants.npz"
MODELS = {"b32": ("ViT-B-32", "openai"), "b16": ("ViT-B-16", "openai"), "l14": ("ViT-L-14", "openai")}


def pad_square(im: Image.Image) -> Image.Image:
    a = np.asarray(im)
    edge = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]]).reshape(-1, 3)
    fill = tuple(int(v) for v in np.median(edge, 0))
    s = max(im.size)
    bg = Image.new("RGB", (s, s), fill)
    bg.paste(im, ((s - im.width) // 2, (s - im.height) // 2))
    return bg


def three_crops(im: Image.Image) -> list[Image.Image]:
    w, h = im.size
    s = min(w, h)
    if w >= h:
        xs = [0, (w - s) // 2, w - s]
        return [im.crop((x, 0, x + s, s)) for x in xs]
    ys = [0, (h - s) // 2, h - s]
    return [im.crop((0, y, s, y + s)) for y in ys]


def main(names):
    import open_clip
    import torch
    c = sqlite3.connect(config.DATA_DIR / "vibecheck.db")
    rows = c.execute("select p.id, p.image_path from posts p join features f on f.post_id=p.id "
                     "where p.label in ('team','rejected') order by p.id").fetchall()
    ids = np.array([r[0] for r in rows])
    imgs = [features.load_image(config.DATA_DIR / r[1]) for r in rows]
    have = dict(np.load(OUT)) if OUT.exists() else {}
    if "ids" in have and not np.array_equal(have["ids"], ids):
        have = {}
    have["ids"] = ids
    by_model = {}
    for n in names:
        by_model.setdefault(n.split("_")[0], []).append(n)
    for mk, variants in by_model.items():
        arch, pre = MODELS[mk]
        t = time.time()
        model, _, prep = open_clip.create_model_and_transforms(arch, pretrained=pre)
        model.eval()

        def enc(batch):
            with torch.no_grad():
                x = model.encode_image(torch.stack([prep(i) for i in batch])).float().numpy()
            return x / np.linalg.norm(x, axis=1, keepdims=True)
        for v in variants:
            how = v.split("_")[1]
            out = []
            for i in range(0, len(imgs), 8):
                chunk = imgs[i:i + 8]
                if how == "center":
                    out.append(enc(chunk))
                elif how == "pad":
                    out.append(enc([pad_square(im) for im in chunk]))
                elif how == "crops":
                    e = enc([cr for im in chunk for cr in three_crops(im)]).reshape(len(chunk), 3, -1).mean(1)
                    out.append(e / np.linalg.norm(e, axis=1, keepdims=True))
            have[v] = np.vstack(out).astype(np.float32)
            print(f"{v}: {have[v].shape} in {time.time() - t:.0f}s", flush=True)
        del model
    np.savez(OUT, **have)


if __name__ == "__main__":
    main(sys.argv[1:] or ["b32_center", "b32_pad", "b32_crops"])
