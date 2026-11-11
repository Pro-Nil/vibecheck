"""Honest evaluation of on-brand scorers on real data, without needing many accepted designs.

The product question is "will a NEW design be accepted?". We have only 2 accepted one-off designs, but every
post the team published later IS a new, approved design. So:

  A. time-forward: for every month M after the first, the model only knows posts published before M; it scores
     the posts of month M (positives) and the rejected drafts (negatives).
  B. leave-one-series-out: posts are grouped into series (CLIP similarity > 0.90, connected); each series is
     scored with the model built from all other series. Uses every post, ignores time.

Reported per scorer: AUC new-team-posts vs rejected drafts (95 % bootstrap CI), how often a genuine new team post
would be called Off-brand (< 12th percentile line), FinLit final-vs-own-drafts wins, Pandiya percentile.
Rejected drafts all come from ONE brief, so prefer simple scorers and look at the CI, not the 3rd decimal.

    .venv/Scripts/python scripts/evaluate.py [--dino]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from vibe import config, features  # noqa: E402

CACHE = ROOT / "data" / "eval_cache.npz"


# ----------------------------------------------------------------------------- data
def load(dino: bool, team_id: int = 1):
    c = sqlite3.connect(config.DATA_DIR / "vibecheck.db")
    rows = c.execute("select p.id, p.label, p.image_path, p.posted_at, p.decision, p.project, f.clip, f.hist, "
                     "f.typo_json, f.aesthetic from posts p join features f on f.post_id=p.id "
                     "where p.label in ('team','rejected') and p.team_id=? order by p.id", (team_id,)).fetchall()
    d = {"id": np.array([r[0] for r in rows]), "label": np.array([r[1] for r in rows], object),
         "month": np.array([(r[3] or "9999-99")[:7] for r in rows], object),
         "decision": np.array([r[4] or "" for r in rows], object), "project": [r[5] for r in rows],
         "clip": np.stack([np.frombuffer(r[6], np.float32) for r in rows]),
         "hist": np.stack([np.frombuffer(r[7], np.float32) for r in rows]),
         "typo": [json.loads(r[8]) if r[8] else {} for r in rows], "paths": [r[2] for r in rows]}
    from vibe.features import STYLE_KEYS
    st = {r[0]: r[1:] for r in c.execute(f"select post_id, {', '.join(STYLE_KEYS)} from features")}
    d["style"] = np.array([st[i] for i in d["id"]], np.float32)
    if dino:
        cache = dict(np.load(CACHE)) if CACHE.exists() else {}
        if "ids" in cache and np.array_equal(cache["ids"], d["id"]):
            d["dino"] = cache["dino"]
        else:
            d["dino"] = embed_dino([config.DATA_DIR / p for p in d["paths"]])
            np.savez(CACHE, ids=d["id"], dino=d["dino"])
    return d


def embed_dino(paths, name="vit_base_patch14_dinov2.lvd142m"):
    import timm
    import torch
    m = timm.create_model(name, pretrained=True, num_classes=0, img_size=224).eval()
    cfg = timm.data.resolve_data_config({}, model=m)
    cfg.update(input_size=(3, 224, 224), crop_pct=1.0)
    tf = timm.data.create_transform(**cfg)
    out = []
    with torch.no_grad():
        for i in range(0, len(paths), 16):
            out.append(m(torch.stack([tf(features.load_image(p)) for p in paths[i:i + 16]])).numpy())
    x = np.vstack(out)
    return (x / np.linalg.norm(x, axis=1, keepdims=True)).astype(np.float32)


# ----------------------------------------------------------------------------- scorers
def chi(x, R):
    return -np.sum((R - x) ** 2 / (R + x + 1e-9), axis=1)


def series(clip, sim=0.90):
    n = len(clip)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    S = clip @ clip.T
    for i in range(n):
        for j in range(i + 1, n):
            if S[i, j] > sim:
                parent[find(i)] = find(j)
    return np.array([find(i) for i in range(n)])


class Scorer:
    """raw(i, ref) -> closeness of item i to reference rows `ref` (indices into d). Percentiles are taken
    against the reference posts' own leave-one-out raw values, exactly as the app does."""

    def __init__(self, d, view="clip", how="topk", k=5, topic_k=8, twin=0.90, topic_by="clip", whiten=False,
                 smooth=False):
        self.smooth = smooth
        self.d, self.view, self.how, self.k, self.topic_k, self.twin, self.topic_by = d, view, how, k, topic_k, twin, topic_by
        self.whiten = whiten

    def _X(self, ref):
        X = self.d[self.view] if self.view != "typo" else self.d["typo_vec"]
        if self.whiten and self.view in ("clip", "dino"):   # centre on the team, so shared "poster-ness" drops out
            mu = X[ref].mean(0)
            Y = X - mu
            return Y / (np.linalg.norm(Y, axis=1, keepdims=True) + 1e-9)
        return X

    def raw(self, i, ref, X=None):
        d = self.d
        X = self._X(ref) if X is None else X
        cand = np.array([j for j in ref if j != i and (self.twin is None or d["clip"][i] @ d["clip"][j] < self.twin)])
        if len(cand) < 3:
            cand = np.array([j for j in ref if j != i])
        if self.how == "topk":
            s = X[cand] @ X[i]
            return float(np.sort(s)[-self.k:].mean())
        tb = d[self.topic_by]
        topic = cand[np.argsort(-(tb[cand] @ tb[i]))[:self.topic_k]]
        if self.view == "hist":
            return float(chi(X[i], X[topic]).mean())
        if self.view == "typo":
            return float(-np.linalg.norm(X[topic] - X[i], axis=1).mean())
        return float((X[topic] @ X[i]).mean())

    def pct(self, items, ref):
        X = self._X(ref)
        base = np.sort([self.raw(j, ref, X) for j in ref])
        vals = np.array([self.raw(i, ref, X) for i in items])
        if self.smooth:
            return smooth_ecdf(base, vals)
        return np.searchsorted(base, vals, side="right") / len(base)


def smooth_ecdf(base, vals):
    """Kernel-smoothed percentile: like the ECDF in the middle, but keeps ordering beyond the extremes
    (a design far below every reference post gets a smaller value than one just below)."""
    from scipy.stats import norm
    base = np.asarray(base, float)
    h = 1.06 * base.std() * len(base) ** -0.2 + 1e-9   # Silverman bandwidth
    return norm.cdf((np.asarray(vals, float)[:, None] - base[None]) / h).mean(1)


class Mean:
    """Average of several scorers' percentiles (optionally weighted), re-ranked among the reference posts."""

    def __init__(self, parts, w=None, probit=False):
        self.parts, self.w = parts, np.array(w if w is not None else [1.0] * len(parts), float)
        self.probit = probit   # combine on the normal (z) scale and keep a smooth tail

    def pct(self, items, ref):
        from scipy.stats import norm
        ref = np.asarray(ref)
        both = np.concatenate([ref, items])
        P = np.array([p.pct(both, ref) for p in self.parts])
        if self.probit:
            P = norm.ppf(np.clip(P, 1e-4, 1 - 1e-4))
        comb = (self.w[:, None] * P).sum(0) / self.w.sum()
        base = np.sort(comb[:len(ref)])
        if self.probit:
            return smooth_ecdf(base, comb[len(ref):])
        return np.searchsorted(base, comb[len(ref):], side="right") / len(base)


# ----------------------------------------------------------------------------- protocols
def auc(pos, neg):
    pos, neg = np.asarray(pos), np.asarray(neg)
    return float(((pos[:, None] > neg[None]) + 0.5 * (pos[:, None] == neg[None])).mean())


def time_forward(d, scorer):
    team = np.where(d["label"] == "team")[0]
    rej = np.where(d["label"] == "rejected")[0]
    months = sorted(set(d["month"][team]))
    pos, negs, fold_aucs = [], [], []
    for m in months[1:]:
        ref = team[d["month"][team] < m]
        test = team[d["month"][team] == m]
        if len(ref) < 10 or not len(test):
            continue
        p = scorer.pct(np.concatenate([test, rej]), ref)
        pos += list(p[:len(test)])
        negs.append(p[len(test):])
        fold_aucs.append((len(test), auc(p[:len(test)], p[len(test):])))
    neg = np.concatenate(negs)
    pooled = sum(n * a for n, a in fold_aucs) / sum(n for n, _ in fold_aucs)
    return np.array(pos), neg, pooled


def leave_series_out(d, scorer):
    team = np.where(d["label"] == "team")[0]
    rej = np.where(d["label"] == "rejected")[0]
    g = series(d["clip"][team])
    pos = np.zeros(len(team))
    for s in set(g):
        out = team[g == s]
        ref = team[g != s]
        pos[g == s] = scorer.pct(out, ref)
    neg = scorer.pct(rej, team)
    return pos, neg, auc(pos, neg)


def boot_ci(pos, neg, n=2000, seed=0):
    rng = np.random.default_rng(seed)
    vals = [auc(rng.choice(pos, len(pos)), rng.choice(neg, len(neg))) for _ in range(n)]
    return np.percentile(vals, [2.5, 97.5])


def report(d, scorers):
    team = np.where(d["label"] == "team")[0]
    rej = np.where(d["label"] == "rejected")[0]
    acc = np.where(d["decision"] == "accepted")[0]
    finlit_final = [i for i in acc if d["project"][i] == "finlit-talk"]
    pandiya = [i for i in acc if d["project"][i] == "pandiya-night"]
    print(f"team posts {len(team)}, rejected drafts {len(rej)}, accepted designs {len(acc)}\n")
    print(f"{'scorer':44s} {'A: time-fwd AUC':>16s} {'95% CI':>12s} {'A: new posts Off-brand':>23s} "
          f"{'B: series-out AUC':>18s} {'95% CI':>12s} {'FinLit wins':>11s} {'Pandiya':>7s}")
    out = {}
    for name, sc in scorers.items():
        pa, na, auc_a = time_forward(d, sc)
        pb, nb, auc_b = leave_series_out(d, sc)
        ca, cb = boot_ci(pa, na), boot_ci(pb, nb)
        # accepted one-offs: scored against every other team post (they are team posts themselves)
        others = np.array([j for j in team if j not in acc])
        pf = sc.pct(np.array(finlit_final + pandiya + list(rej)), others)
        wins = int((pf[0] > pf[len(finlit_final) + len(pandiya):]).sum()) if finlit_final else -1
        pan = pf[len(finlit_final)] if pandiya else float("nan")
        off = float((pa < 0.12).mean())
        print(f"{name:44s} {auc_a:16.2f} {ca[0]:5.2f}-{ca[1]:4.2f} {off:22.0%} {auc_b:18.2f} {cb[0]:5.2f}-{cb[1]:4.2f} "
              f"{wins:8d}/9 {100 * pan:6.0f}")
        out[name] = {"time_auc": auc_a, "series_auc": auc_b, "new_off": off, "wins": wins, "pandiya": pan}
    return out


class AppScorer:
    """The on-brand scorer exactly as the app ships it (vibe.model._OnBrand)."""

    def __init__(self, d):
        self.d = d

    def pct(self, items, ref):
        from vibe.model import _OnBrand
        ref = np.asarray(ref)
        st = self.d.get("style")
        ob = _OnBrand(self.d["clip"][ref], self.d["hist"][ref], None if st is None else st[ref])
        pos = {int(r): j for j, r in enumerate(ref)}
        return np.array([ob.parts(self.d["clip"][i], self.d["hist"][i], None if st is None else st[i],
                                  exclude=pos.get(int(i)))["on_brand"] for i in items])


def build(d, dino: bool):
    tv = []
    for t in d["typo"]:
        tv.append([t.get("text_area", 0) or 0, t.get("headline", 0) or 0, t.get("n_lines", 0) or 0,
                   min(1.0, (t.get("min_contrast") or 21) / 21)])
    d["typo_vec"] = np.array(tv, np.float32)
    S = {
        "APP (as shipped)": AppScorer(d),
        "v2: clip look": Scorer(d, "clip"),
        "v2: colour vs topic": Scorer(d, "hist", "topic"),
    }
    S["v2/v3 (look + colour, plain percentiles)"] = Mean([S["v2: clip look"], S["v2: colour vs topic"]])
    sm = dict(smooth=True)
    S["v4 (smooth look k10 x2 + colour, z)"] = Mean([Scorer(d, "clip", k=10, **sm), Scorer(d, "hist", "topic", **sm)],
                                                    [2, 1], probit=True)
    S["clip look, team-centred"] = Scorer(d, "clip", whiten=True)
    S["clip look k=10"] = Scorer(d, "clip", k=10)
    S["clip vs topic (8)"] = Scorer(d, "clip", "topic")
    S["colour vs topic (5)"] = Scorer(d, "hist", "topic", topic_k=5)
    S["colour vs topic (15)"] = Scorer(d, "hist", "topic", topic_k=15)
    S["colour vs ALL posts (k=8)"] = Scorer(d, "hist", "topic", topic_k=10_000)
    S["typography vs topic"] = Scorer(d, "typo", "topic")
    S["centred look + colour"] = Mean([S["clip look, team-centred"], S["v2: colour vs topic"]])
    S["colour only"] = S["v2: colour vs topic"]
    S["look + colour + typography"] = Mean([S["v2: clip look"], S["v2: colour vs topic"], S["typography vs topic"]])
    S["look + 2x colour"] = Mean([S["v2: clip look"], S["v2: colour vs topic"]], [1, 2])
    if dino:
        S["dino look"] = Scorer(d, "dino")
        S["dino look, team-centred"] = Scorer(d, "dino", whiten=True)
        S["dino vs topic"] = Scorer(d, "dino", "topic")
        S["dino look + colour"] = Mean([S["dino look"], S["v2: colour vs topic"]])
        S["clip + dino + colour"] = Mean([S["v2: clip look"], S["dino look"], S["v2: colour vs topic"]])
    return S


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dino", action="store_true", help="also test DINOv2-base (downloads ~350 MB once)")
    ap.add_argument("--only", nargs="*", help="names of scorers to run")
    ap.add_argument("--team", type=int, default=1)
    a = ap.parse_args()
    data = load(a.dino, a.team)
    scs = build(data, a.dino)
    if a.only:
        scs = {k: v for k, v in scs.items() if k in a.only}
    report(data, scs)
