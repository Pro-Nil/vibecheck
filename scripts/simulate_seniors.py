"""How many decided designs does the approval model need? A simulation with synthetic "seniors".

Each simulated project (brief) has one ACCEPTED design (a real team post) and REJECTED versions of it (the
same post with a realistic mistake from scripts/synth_benchmark.py). Some decisions are flipped to mimic
inconsistent seniors. For a growing number of projects we train the app's own approval model
(vibe.model._approval, leave-one-project-out) and compare it with the plain on-brand score.

What this does and does not show: it checks that the approval model learns a real signal when one exists,
and roughly how much data that takes. The simulated seniors reject exactly the mistakes we made up, so the
numbers are optimistic about real seniors, whose reasons are subtler.

    .venv/Scripts/python scripts/simulate_seniors.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))
import synth_benchmark as B  # noqa: E402
from vibe import config, features, model  # noqa: E402
from vibe.features import STYLE_KEYS  # noqa: E402

REJECT_EDITS = ["wrong colour scheme", "neon recolour", "hue shift 150°", "washed out", "greyscale",
                "clutter", "busy texture", "title cut off", "low contrast"]


def main(sizes=(3, 5, 8, 12, 20, 30), rejects_per_project=2, flip=0.15, repeats=5, variants=None):
    d = model.load_team_data(1)
    team = np.where(d["label"] == "team")[0]
    d = {k: (v[team] if isinstance(v, np.ndarray) else [v[i] for i in team]) for k, v in d.items()}
    n = len(team)
    groups = B.series_of(d["clip"])
    sources = [np.where(groups == g)[0][0] for g in sorted(set(groups))]   # one post per series
    rng = np.random.default_rng(0)
    # make the rejected versions once (all sources), with features
    rej_src, rej_imgs = [], []
    for i in sources:
        im = features.load_image(config.DATA_DIR / Post_path(d, i))
        im.thumbnail((720, 900))
        for name in rng.choice(REJECT_EDITS, rejects_per_project, replace=False):
            rej_imgs.append(B.MISTAKES[name](im, rng))
            rej_src.append(i)
    print(f"{len(sources)} series -> up to {len(sources)} projects; making {len(rej_imgs)} rejected versions...", flush=True)
    feats = features.extract(rej_imgs)
    R = {"clip": np.stack([f["clip"] for f in feats]), "hist": np.stack([f["hist"] for f in feats]),
         "style": np.array([[f[k] for k in STYLE_KEYS] for f in feats], np.float32),
         "aesthetic": np.array([f["aesthetic"] if f["aesthetic"] is not None else np.nan for f in feats], np.float32)}
    ob = model._OnBrand(d["clip"], d["hist"], d["style"])
    ranges = model._style_ranges(d["style"], np.zeros((0, len(STYLE_KEYS))))
    aes = np.sort(d["aesthetic"][np.isfinite(d["aesthetic"])])
    model.MIN_DECIDED, model.MIN_PROJECTS, model.MIN_APPROVAL_AUC = 2, 2, 0.0   # measure at every size
    for vname, setup in (variants or {"as shipped": None}).items():
        if setup:
            setup(d)
        print(f"\n[{vname}]\n{'projects':>8s} {'decided designs':>16s} {'approval AUC (LOPO)':>20s} {'on-brand AUC':>13s}")
        _curve(d, n, sources, rej_src, rej_imgs, R, ob, ranges, aes, sizes, rejects_per_project, flip, repeats)


def _curve(d, n, sources, rej_src, rej_imgs, R, ob, ranges, aes, sizes, rejects_per_project, flip, repeats):
    for P in sizes:
        if P > len(sources):
            break
        a_auc, o_auc, a_pair, o_pair, on = [], [], [], [], []
        for rep in range(repeats):
            r = np.random.default_rng(100 + rep)
            chosen = r.choice(len(sources), P, replace=False)
            rows = []
            for c in chosen:
                src = sources[c]
                rows.append(("team", src, "accepted", f"p{c}"))
                rows += [("rej", j, "rejected", f"p{c}") for j in np.where(np.array(rej_src) == src)[0]]
            dec = [x[2] if r.random() >= flip else ("rejected" if x[2] == "accepted" else "accepted") for x in rows]
            D = {"clip": np.vstack([d["clip"], R["clip"]]), "hist": np.vstack([d["hist"], R["hist"]]),
                 "style": np.vstack([d["style"], R["style"]]), "aesthetic": np.concatenate([d["aesthetic"], R["aesthetic"]]),
                 "id": np.arange(n + len(rej_imgs)), "typo": [None] * (n + len(rej_imgs)),
                 "decision": [None] * (n + len(rej_imgs)), "project": [""] * (n + len(rej_imgs))}
            for (kind, j, _, proj), dd in zip(rows, dec):
                k = j if kind == "team" else n + j
                D["decision"][k], D["project"][k] = dd, proj
            _, st = model._approval(D, ob, np.arange(n), ranges, {}, aes)
            if st.get("auc") is not None:
                a_auc.append(st["auc"])
            if st.get("on_brand_auc") is not None:
                o_auc.append(st["on_brand_auc"])
            if st.get("pairs_right") is not None:
                a_pair.append(st["pairs_right"])
            o_pair.append(st["on_brand_pairs_right"])
            on.append(st.get("auc_ci_low", 0) > model.APPROVAL_CI_LOW and st.get("auc", 0) >= (st.get("on_brand_auc") or .5) - .02)
        print(f"{P:8d} {P * (1 + rejects_per_project):16d} {np.mean(a_auc):13.2f} ± {np.std(a_auc):.2f} {np.mean(o_auc):13.2f}"
              f"   | same-project pairs right: approval {np.mean(a_pair):.2f}, on-brand {np.mean(o_pair):.2f}"
              f" | switches on {np.mean(on):.0%}", flush=True)


def Post_path(d, i):
    from vibe.db import Post, SessionLocal
    with SessionLocal() as s:
        return s.get(Post, int(d["id"][i])).image_path


if __name__ == "__main__":
    main()
