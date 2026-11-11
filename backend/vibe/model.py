"""The adaptive core: learns one team's style and scores a designer's plan against it.

Score = 100 x (0.5 x classifier probability + 0.5 x similarity percentile)       [images]
        blended 75 / 25 with a text score when a written description is given.

  * classifier  - logistic regression, team posts vs (other pages + near-misses), on CLIP + style
  * similarity  - mean cosine similarity to the 5 nearest team posts, turned into a percentile:
                  "more team-like than X % of other pages' posts"
  * text        - is the description closer to this team's posts than to other pages' posts?
Real rejected drafts are never trained on; they are only used to test the model.
"""
from __future__ import annotations

import json
import threading
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
from PIL import Image
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import roc_auc_score, roc_curve
from sklearn.model_selection import KFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy import select

from . import config, features
from .db import ModelVersion, Post, SessionLocal
from .features import STYLE_KEYS, STYLE_LABELS, STYLE_WORDS

TOP_K = 5
IMG_WEIGHT, TEXT_WEIGHT = 0.75, 0.25
DEFAULT_THRESHOLDS = {"approve": 70.0, "borderline": 45.0}
NEAR_MISS_MAX_SIM = 0.85  # near-misses closer than this to their original are not used
STYLE_TOLERANCE = 0.04  # a feature within 4 points of the team's usual range still counts as fitting
_cache: dict[int, tuple[int, dict]] = {}
_cache_lock = threading.Lock()


class NotTrained(Exception):
    pass


# ----------------------------------------------------------------------- data
def load_team_data(team_id: int) -> dict:
    with SessionLocal() as s:
        rows = s.execute(select(Post).where(Post.team_id == team_id, Post.features.has())).scalars().all()
        out = defaultdict(list)
        for p in rows:
            f = p.features
            out["id"].append(p.id)
            out["label"].append(p.label)
            out["clip"].append(f.vector)
            out["style"].append([getattr(f, k) for k in STYLE_KEYS])
            out["palette"].append(json.loads(f.palette_json))
            out["likes"].append(p.likes)
            out["posted_at"].append(p.posted_at)
            out["external_id"].append(p.external_id)
            out["source_page"].append(p.source_page)
    if not out:
        return {"id": np.array([], int), "label": np.array([], object)}
    d = {k: v for k, v in out.items()}
    d["id"] = np.array(d["id"])
    d["label"] = np.array(d["label"], dtype=object)
    d["clip"] = np.stack(d["clip"]).astype(np.float32)
    d["style"] = np.array(d["style"], dtype=np.float32)
    return d


def _X(clip: np.ndarray, style: np.ndarray) -> np.ndarray:
    return np.hstack([clip, style])


def _topk_sim(q: np.ndarray, ref: np.ndarray, k: int = TOP_K, exclude_self: bool = False) -> np.ndarray:
    """Mean cosine similarity of each row of q to its k nearest rows of ref."""
    if len(ref) == 0:
        return np.zeros(len(q))
    sims = q @ ref.T
    if exclude_self:
        np.fill_diagonal(sims, -np.inf)
    k = max(1, min(k, ref.shape[0] - (1 if exclude_self else 0)))
    part = -np.partition(-sims, k - 1, axis=1)[:, :k]
    return part.mean(axis=1)


def _ecdf(sorted_ref: np.ndarray, x) -> np.ndarray:
    x = np.atleast_1d(x)
    if len(sorted_ref) == 0:
        return np.full(len(x), 0.5)
    return np.searchsorted(sorted_ref, x, side="right") / len(sorted_ref)


def _parent_of(ext_id: str) -> int | None:
    # near-miss rows are named aug<k>_<parent post id>
    try:
        return int(ext_id.split("_", 1)[1]) if ext_id.startswith("aug") else None
    except (IndexError, ValueError):
        return None


# ---------------------------------------------------------------------- pieces
class _Scorer:
    """Classifier + similarity reference, enough to compute an image score."""

    def __init__(self, clip, style, is_team, is_other):
        self.team_vecs = clip[is_team]
        self.has_neg = bool((~is_team).sum() >= 5 and is_team.sum() >= 5)
        if self.has_neg:
            self.clf = make_pipeline(StandardScaler(), LogisticRegression(
                C=0.05, class_weight="balanced", max_iter=3000))
            self.clf.fit(_X(clip, style), is_team.astype(int))
        else:
            self.clf = None
        other_vecs = clip[is_other]
        self.other_sims = np.sort(_topk_sim(other_vecs, self.team_vecs)) if len(other_vecs) else np.array([])
        self.team_sims = np.sort(_topk_sim(self.team_vecs, self.team_vecs, exclude_self=True))

    def parts(self, clip: np.ndarray, style: np.ndarray, exclude_self_rows: bool = False) -> dict:
        sims = _topk_sim(clip, self.team_vecs, exclude_self=exclude_self_rows)
        if len(self.other_sims):
            sim_pct = _ecdf(self.other_sims, sims)
        else:  # cold start: no other pages, compare with the team's own posts
            sim_pct = _ecdf(self.team_sims, sims)
        prob = self.clf.predict_proba(_X(clip, style))[:, 1] if self.clf is not None else sim_pct
        return {"classifier": prob, "similarity": sim_pct, "raw_sim": sims}

    @staticmethod
    def combine(prob, sim_pct, weights=(0.5, 0.5)):
        wc, ws = weights
        return 100.0 * (wc * prob + ws * sim_pct)


# Typical poster styles. A description is judged by how much better it matches the team's posts than
# these do, so the text score is a percentile (0..1) with no hand-tuned scale, and it works even
# when no other pages were imported.
REFERENCE_DESCRIPTIONS = [
    "minimal black and white typographic poster", "colourful cartoon illustration poster",
    "corporate blue gradient flyer with stock photo", "vintage newspaper style poster",
    "neon cyberpunk poster with glowing text", "pastel watercolour illustration",
    "photo collage with many small pictures", "bold red and yellow sale banner",
    "dark poster with a portrait photo of a speaker", "hand drawn doodle poster",
    "retro 80s synthwave poster", "flat geometric shapes in bright colours",
    "elegant gold and black luxury invitation", "grunge textured poster with distressed type",
    "clean white tech product advertisement", "festival poster with dancers and lights",
    "sports event poster with an action photo", "infographic with charts and icons",
    "Instagram quote card with large text", "3D rendered abstract shapes poster",
    "nature photo with a thin serif title", "comic book style poster with speech bubbles",
    "pixel art game poster", "Bauhaus style poster with circles and lines",
    "handwritten chalkboard style poster", "glassmorphism user interface style graphic",
    "black poster with a bright green code font", "pink and purple gradient music event poster",
    "traditional Indian festival poster with rangoli", "workshop announcement with a laptop photo",
    "space themed poster with planets and stars", "robot illustration for a technology event",
    "simple countdown poster with one big number", "meme style image with impact font",
    "blueprint style technical drawing poster", "collage of team member photos",
    "brutalist poster with huge black type", "soft beige aesthetic poster with serif font",
    "sponsor announcement with company logos", "hackathon poster with circuit patterns",
]


def _text_margin(text_vecs: np.ndarray, team_vecs: np.ndarray, other_vecs: np.ndarray) -> np.ndarray:
    """How much closer a description is to the team's posts than to other pages' posts
    (or just its closeness to the team's posts when there are no other pages)."""
    s_team = _topk_sim(text_vecs, team_vecs)
    if len(other_vecs):
        return s_team - _topk_sim(text_vecs, other_vecs)
    return s_team


def _text_reference(art: dict) -> np.ndarray:
    vecs = features.embed_texts(REFERENCE_DESCRIPTIONS)
    return np.sort(_text_margin(vecs, art["scorer"].team_vecs, art["other_vecs"]))


def _weights(auc_classifier: float, auc_similarity: float) -> tuple[float, float]:
    """Trust each signal by how much better than guessing (AUC 0.5) it did on held-out posts."""
    c, s = max(auc_classifier - 0.5, 0.02), max(auc_similarity - 0.5, 0.02)
    return c / (c + s), s / (c + s)


def _style_ranges(style: np.ndarray, other_style: np.ndarray) -> dict:
    out = {}
    for i, k in enumerate(STYLE_KEYS):
        col = style[:, i]
        out[k] = {"label": STYLE_LABELS[k],
                  "p10": float(np.percentile(col, 10)), "p50": float(np.percentile(col, 50)),
                  "p90": float(np.percentile(col, 90)),
                  "other_p50": float(np.percentile(other_style[:, i], 50)) if len(other_style) else None}
    return out


def _hex_to_lab(hexes: list[str]) -> np.ndarray:
    import cv2
    rgb = np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in hexes], dtype=np.uint8)
    return cv2.cvtColor(rgb.reshape(-1, 1, 3), cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(float) * [100 / 255, 1, 1] - [0, 128, 128]


def _signature_palette(palettes: list[list[dict]], k: int = 6) -> list[dict]:
    hexes = [c["hex"] for p in palettes for c in p]
    weights = np.array([c["share"] for p in palettes for c in p])
    if not hexes:
        return []
    lab = _hex_to_lab(hexes)
    from sklearn.cluster import KMeans
    k = min(k, len(set(hexes)))
    km = KMeans(n_clusters=k, n_init=4, random_state=0).fit(lab, sample_weight=weights)
    out = []
    for c in range(k):
        m = km.labels_ == c
        # representative = the real colour nearest the centre (keeps it a colour they actually used)
        idx = np.where(m)[0][np.argmin(((lab[m] - km.cluster_centers_[c]) ** 2).sum(1))]
        out.append({"hex": hexes[idx], "share": float(weights[m].sum() / weights.sum())})
    return sorted(out, key=lambda x: -x["share"])


def _palette_distance(plan: list[dict], signature: list[dict]) -> float:
    """Average colour distance (CIE76 delta-E) from each plan colour to the nearest signature colour."""
    if not plan or not signature:
        return 0.0
    a, b = _hex_to_lab([c["hex"] for c in plan]), _hex_to_lab([c["hex"] for c in signature])
    w = np.array([c["share"] for c in plan])
    d = np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).sum(-1)).min(1)
    return float((d * w).sum() / w.sum())


def _engagement(d: dict, team_mask: np.ndarray) -> dict | None:
    idx = [i for i in np.where(team_mask)[0] if d["likes"][i] is not None and d["posted_at"][i] is not None]
    if len(idx) < 30:
        return None
    months = defaultdict(list)
    for i in idx:
        months[d["posted_at"][i].strftime("%Y-%m")].append(d["likes"][i])
    keys = sorted(months)
    def baseline(m):  # mean likes in the month, widened to +/-1 month when the month is thin
        j = keys.index(m)
        vals = months[m] if len(months[m]) >= 3 else sum((months[k] for k in keys[max(0, j - 1):j + 2]), [])
        return max(1.0, float(np.mean(vals)))
    y = np.array([np.log((d["likes"][i] + 1) / baseline(d["posted_at"][i].strftime("%Y-%m"))) for i in idx])
    X = _X(d["clip"][idx], d["style"][idx])
    reg = make_pipeline(StandardScaler(), Ridge(alpha=300.0))
    errs, base = [], []
    for tr, te in KFold(5, shuffle=True, random_state=0).split(X):
        reg.fit(X[tr], y[tr])
        errs.append(np.abs(reg.predict(X[te]) - y[te]).mean())
        base.append(np.abs(y[tr].mean() - y[te]).mean())
    reg.fit(X, y)
    corr = []
    for j, k in enumerate(STYLE_KEYS):
        col = d["style"][idx, j]
        c = float(np.corrcoef(col, y)[0, 1]) if col.std() > 1e-6 else 0.0
        corr.append({"feature": k, "label": STYLE_LABELS[k], "correlation": round(c, 3)})
    return {"model": reg, "n": len(idx), "mae": float(np.mean(errs)), "baseline_mae": float(np.mean(base)),
            "band": 0.2, "what_works": sorted(corr, key=lambda c: -abs(c["correlation"]))}


def _style_map(d: dict, max_other: int = 1500):
    try:
        import umap
    except Exception:
        return None, {}
    rng = np.random.default_rng(0)
    keep = [i for i, l in enumerate(d["label"]) if l in ("team", "rejected")]
    others = [i for i, l in enumerate(d["label"]) if l == "other"]
    if len(others) > max_other:
        others = list(rng.choice(others, max_other, replace=False))
    idx = keep + others
    if len(idx) < 12:
        return None, {}
    reducer = umap.UMAP(n_neighbors=min(15, len(idx) - 1), min_dist=0.15, metric="cosine", random_state=0, compatibility_layout=True)
    xy = reducer.fit_transform(d["clip"][idx])
    return reducer, {int(d["id"][i]): [float(xy[j, 0]), float(xy[j, 1])] for j, i in enumerate(idx)}


# --------------------------------------------------------------------- train
def train(team_id: int) -> dict:
    d = load_team_data(team_id)
    if len(d["id"]) == 0 or (d["label"] == "team").sum() < 3:
        raise NotTrained("Need at least 3 team posts with features to train.")
    lab = d["label"]
    is_team, is_other, is_aug, is_rej = lab == "team", lab == "other", lab == "augmented", lab == "rejected"
    # A near-miss that CLIP sees as practically the same poster as its original is a contradictory
    # label ("this is us" and "this is not us" at once), so it is left out.
    row_of = {int(pid): i for i, pid in enumerate(d["id"])}
    n_aug_all = int(is_aug.sum())
    for i in np.where(is_aug)[0]:
        p = row_of.get(_parent_of(d["external_id"][i]))
        if p is None or float(d["clip"][i] @ d["clip"][p]) > NEAR_MISS_MAX_SIM:
            is_aug[i] = False
    train_rows = is_team | is_other | is_aug

    # ---- hold-out evaluation (20 %), near-misses follow their parent post's split
    rng = np.random.default_rng(0)
    test = np.zeros(len(lab), bool)
    team_idx = np.where(is_team)[0]
    test_team = set(rng.choice(team_idx, max(1, len(team_idx) // 5), replace=False).tolist())
    other_idx = np.where(is_other)[0]
    test_other = set(rng.choice(other_idx, len(other_idx) // 5, replace=False).tolist()) if len(other_idx) else set()
    test_ids = {int(d["id"][i]) for i in test_team}
    for i in range(len(lab)):
        if i in test_team or i in test_other:
            test[i] = True
        elif is_aug[i] and _parent_of(d["external_id"][i]) in test_ids:
            test[i] = True
    tr = train_rows & ~test
    metrics: dict = {"n_team": int(is_team.sum()), "n_other": int(is_other.sum()),
                     "n_near_miss": int(is_aug.sum()), "n_near_miss_dropped": n_aug_all - int(is_aug.sum()),
                     "n_rejected": int(is_rej.sum())}
    thresholds = dict(DEFAULT_THRESHOLDS)
    weights = (0.5, 0.5)
    if (tr & is_team).sum() >= 3:
        sc = _Scorer(d["clip"][tr], d["style"][tr], is_team[tr], is_other[tr])
        te = test & train_rows
        parts = sc.parts(d["clip"][te], d["style"][te])
        y = is_team[te].astype(int)
        metrics["n_test"] = int(te.sum())
        if 0 < y.sum() < len(y):
            auc_c = float(roc_auc_score(y, parts["classifier"]))
            auc_s = float(roc_auc_score(y, parts["similarity"]))
            metrics["auc_classifier"] = round(auc_c, 3)
            metrics["auc_similarity"] = round(auc_s, 3)
            weights = _weights(auc_c, auc_s)
        vibe = _Scorer.combine(parts["classifier"], parts["similarity"], weights)
        if 0 < y.sum() < len(y):
            metrics["auc"] = round(float(roc_auc_score(y, vibe)), 3)
            o = is_other[te] | is_team[te]
            if is_other[te].any():
                metrics["auc_vs_other_pages"] = round(float(roc_auc_score(y[o], vibe[o])), 3)
            a = is_aug[te] | is_team[te]
            if is_aug[te].any():
                metrics["auc_vs_near_misses"] = round(float(roc_auc_score(y[a], vibe[a])), 3)
            fpr, tpr, thr = roc_curve(y, vibe)
            # Youden's J picks the cut-off; put the line halfway into the gap below it so a
            # clean separation does not end up with the line glued to the lowest team score.
            t = float(thr[np.argmax(tpr - fpr)])
            below = vibe[vibe < t]
            best = float(np.clip((t + below.max()) / 2 if len(below) else t, 30, 85))
            thresholds = {"approve": round(best, 1), "borderline": round(max(5.0, best - 20), 1)}
            pred = vibe >= thresholds["approve"]
            metrics["accuracy"] = round(float((pred == y.astype(bool)).mean()), 3)
            metrics["team_posts_passing"] = round(float(pred[y == 1].mean()), 3)
            metrics["roc"] = [[round(float(a), 3), round(float(b), 3)] for a, b in zip(fpr, tpr)][:: max(1, len(fpr) // 60)]
            metrics["test_scores"] = {"team": [round(float(v), 1) for v in vibe[y == 1]],
                                      "other": [round(float(v), 1) for v in vibe[is_other[te]]],
                                      "near_miss": [round(float(v), 1) for v in vibe[is_aug[te]]]}
        if is_rej.any():
            rp = sc.parts(d["clip"][is_rej], d["style"][is_rej])
            rv = _Scorer.combine(rp["classifier"], rp["similarity"], weights)
            metrics["real_rejects"] = {"n": int(is_rej.sum()),
                                       "below_approve": int((rv < thresholds["approve"]).sum()),
                                       "scores": [round(float(v), 1) for v in rv]}
    metrics["thresholds"] = thresholds
    metrics["weights"] = {"classifier": round(weights[0], 3), "similarity": round(weights[1], 3)}

    # ---- final model on everything (minus real rejects)
    final = _Scorer(d["clip"][train_rows], d["style"][train_rows], is_team[train_rows], is_other[train_rows])
    other_rows = is_other
    if other_rows.sum() > 3000:
        keep = rng.choice(np.where(other_rows)[0], 3000, replace=False)
        other_rows = np.zeros(len(lab), bool)
        other_rows[keep] = True
    eng = _engagement(d, is_team)
    if eng:
        metrics["engagement"] = {"n": eng["n"], "mae": round(eng["mae"], 3),
                                 "baseline_mae": round(eng["baseline_mae"], 3)}
    reducer, coords = _style_map(d)
    team_dates = [p for p, t in zip(d["posted_at"], is_team) if t and p]
    artifact = {
        "scorer": final, "thresholds": thresholds, "weights": weights,
        "team_ids": d["id"][is_team], "other_vecs": d["clip"][other_rows],
        "ranges": _style_ranges(d["style"][is_team], d["style"][is_other]),
        "signature_palette": _signature_palette([p for p, t in zip(d["palette"], is_team) if t]),
        "engagement": eng, "umap": reducer, "coords": coords,
        "coord_labels": {int(i): str(l) for i, l in zip(d["id"], lab)},
        "date_range": [min(team_dates).isoformat(), max(team_dates).isoformat()] if team_dates else None,
    }
    artifact["text_ref"] = _text_reference(artifact)
    with SessionLocal() as s:
        version = (s.scalar(select(ModelVersion.id).order_by(ModelVersion.id.desc())) or 0) + 1
        path = config.MODELS_DIR / f"team_{team_id}_v{version}.joblib"
        joblib.dump(artifact, path)
        mv = ModelVersion(team_id=team_id, metrics_json=json.dumps(metrics),
                          file_path=path.relative_to(config.DATA_DIR).as_posix())
        s.add(mv)
        s.commit()
        out = mv.to_dict()
    with _cache_lock:
        _cache.pop(team_id, None)
    return out


def latest(team_id: int) -> tuple[int, dict]:
    with SessionLocal() as s:
        mv = s.scalar(select(ModelVersion).where(ModelVersion.team_id == team_id)
                      .order_by(ModelVersion.id.desc()))
        if mv is None:
            raise NotTrained("This team has no trained model yet. Import posts first.")
        mv_id, path = mv.id, mv.file_path
    with _cache_lock:
        hit = _cache.get(team_id)
        if hit and hit[0] == mv_id:
            return hit
        art = joblib.load(config.DATA_DIR / path)
        _cache[team_id] = (mv_id, art)
        return mv_id, art


# ----------------------------------------------------------------------- score
def _verdict(score: float, th: dict) -> tuple[str, str]:
    if score >= th["approve"]:
        return "approve", "Likely approved"
    if score >= th["borderline"]:
        return "borderline", "Borderline"
    return "reject", "Likely sent back"


def _pct(v: float) -> int:
    return int(round(100 * v))


def score(team_id: int, images: list[Image.Image], description: str = "") -> dict:
    if not images and not description.strip():
        raise ValueError("Send at least one inspiration image or a description.")
    mv_id, art = latest(team_id)
    sc: _Scorer = art["scorer"]
    th = art["thresholds"]
    w = art.get("weights", (0.5, 0.5))
    out: dict = {"model_version": mv_id, "thresholds": th, "components": {},
                 "weights": {"classifier": round(w[0], 3), "similarity": round(w[1], 3)}}

    plan_vec = None
    plan_style = None
    plan_palette: list[dict] = []
    img_score = None
    if images:
        feats = features.extract(images)
        clip = np.stack([f["clip"] for f in feats])
        style = np.array([[f[k] for k in STYLE_KEYS] for f in feats], dtype=np.float32)
        parts = sc.parts(clip, style)
        plan_vec = clip.mean(0)
        plan_vec /= np.linalg.norm(plan_vec) + 1e-8
        mean_parts = sc.parts(plan_vec[None], style.mean(0, keepdims=True))
        prob = float(np.mean(parts["classifier"]))
        sim = float(mean_parts["similarity"][0])
        img_score = float(_Scorer.combine(prob, sim, w))
        plan_style = style.mean(0)
        out["components"].update({"classifier": round(prob, 3), "similarity": round(sim, 3),
                                  "image_score": round(img_score, 1)})
        out["per_image"] = [round(float(v), 1) for v in _Scorer.combine(parts["classifier"], parts["similarity"], w)]
        merged = defaultdict(float)
        for f in feats:
            for c in f["palette"]:
                merged[c["hex"]] += c["share"] / len(feats)
        plan_palette = [{"hex": h, "share": round(w, 3)} for h, w in sorted(merged.items(), key=lambda x: -x[1])][:6]

    text_score = None
    text_vec = None
    if description.strip():
        text_vec = features.embed_texts([description.strip()])[0]
        if art.get("text_ref") is None:  # models trained before this existed
            art["text_ref"] = _text_reference(art)
        margin = _text_margin(text_vec[None], sc.team_vecs, art["other_vecs"])
        text_score = float(_ecdf(art["text_ref"], margin)[0])
        out["components"].update({"text": round(text_score, 3)})

    if img_score is not None and text_score is not None:
        total = IMG_WEIGHT * img_score + TEXT_WEIGHT * 100 * text_score
    elif img_score is not None:
        total = img_score
    else:
        total = 100 * text_score
    total = float(np.clip(total, 0, 100))
    level, label = _verdict(total, th)
    out.update({"score": round(total, 1), "verdict": label, "verdict_level": level})

    # ---- reasons
    reasons = []
    ranges = art["ranges"]
    if plan_style is not None:
        for i, k in enumerate(STYLE_KEYS):
            r = ranges[k]
            v = float(plan_style[i])
            spread = max(0.05, r["p90"] - r["p10"])
            dev = (v - r["p50"]) / spread
            inside = r["p10"] - STYLE_TOLERANCE <= v <= r["p90"] + STYLE_TOLERANCE
            more, less = STYLE_WORDS[k]
            if inside:
                text = f"{STYLE_LABELS[k]} fits: yours {_pct(v)}, this team usually {_pct(r['p10'])}-{_pct(r['p90'])} (out of 100)."
            else:
                strength = "much " if abs(dev) > 1.0 else ""
                word = more if v > r["p50"] else less
                text = (f"{STYLE_LABELS[k]}: your plan is {strength}{word} than this team's usual posts "
                        f"(yours {_pct(v)}, usual {_pct(r['p10'])}-{_pct(r['p90'])} out of 100).")
            reasons.append({"ok": inside, "feature": k, "label": STYLE_LABELS[k], "text": text,
                            "plan": round(v, 3), "usual_low": round(r["p10"], 3),
                            "usual_mid": round(r["p50"], 3), "usual_high": round(r["p90"], 3),
                            "deviation": round(float(dev), 2)})
        pd = _palette_distance(plan_palette, art["signature_palette"])
        ok = pd < 25
        reasons.append({"ok": ok, "feature": "palette", "label": "Colour palette", "deviation": round(pd / 25, 2),
                        "text": ("Colours sit close to this team's signature palette." if ok else
                                 f"Colours are far from this team's signature palette (average colour distance {pd:.0f}; under 25 counts as close).")})
    if text_score is not None:
        ok = text_score >= 0.5
        reasons.append({"ok": ok, "feature": "description", "label": "Your description", "deviation": round(0.5 - text_score, 2),
                        "text": (f"Your description fits this team's posts better than {_pct(text_score)}% of typical poster descriptions."
                                 if ok else f"Your description fits this team's posts worse than most typical poster descriptions "
                                            f"(better than only {_pct(text_score)}%).")})
    reasons.sort(key=lambda r: (r["ok"], -abs(r.get("deviation", 0))))
    out["reasons"] = reasons
    out["plan_style"] = {k: round(float(plan_style[i]), 3) for i, k in enumerate(STYLE_KEYS)} if plan_style is not None else None
    out["plan_palette"] = plan_palette
    out["signature_palette"] = art["signature_palette"]
    out["ranges"] = ranges

    # ---- nearest past posts
    q = plan_vec if plan_vec is not None else text_vec
    sims = sc.team_vecs @ q
    order = np.argsort(-sims)[:3]
    ids = [int(art["team_ids"][i]) for i in order]
    with SessionLocal() as s:
        posts = {p.id: p.to_dict() for p in s.scalars(select(Post).where(Post.id.in_(ids)))}
    out["nearest"] = [{**posts[i], "similarity": round(float(sims[j]), 3)} for i, j in zip(ids, order) if i in posts]

    # ---- engagement + map point
    eng = art.get("engagement")
    if eng and plan_vec is not None:
        pred = float(eng["model"].predict(_X(plan_vec[None], plan_style[None]))[0])
        band = "Above usual" if pred > eng["band"] else "Below usual" if pred < -eng["band"] else "Usual"
        out["engagement"] = {"band": band, "predicted_vs_usual": round(float(np.exp(pred)), 2)}
    else:
        out["engagement"] = None
    if art.get("umap") is not None and plan_vec is not None:
        try:
            xy = art["umap"].transform(plan_vec[None])[0]
            out["map_point"] = [float(xy[0]), float(xy[1])]
        except Exception:
            out["map_point"] = None
    else:
        out["map_point"] = None
    return out


def style_profile(team_id: int) -> dict:
    mv_id, art = latest(team_id)
    with SessionLocal() as s:
        mv = s.get(ModelVersion, mv_id)
        metrics = json.loads(mv.metrics_json)
        trained_at = mv.trained_at.isoformat()
    # style over time: monthly medians of team posts
    d = load_team_data(team_id)
    by_month = defaultdict(list)
    for lab, when, st in zip(d["label"], d["posted_at"], d["style"]):
        if lab == "team" and when:
            by_month[when.strftime("%Y-%m")].append(st)
    trend = [{"month": m, **{k: round(float(np.median(np.array(v)[:, i])), 3) for i, k in enumerate(STYLE_KEYS)},
              "n": len(v)} for m, v in sorted(by_month.items())]
    eng = art.get("engagement")
    return {
        "model_version": mv_id, "trained_at": trained_at, "metrics": metrics,
        "thresholds": art["thresholds"], "ranges": art["ranges"],
        "signature_palette": art["signature_palette"],
        "what_works": eng["what_works"] if eng else None,
        "trend": trend,
        "map": [{"post_id": pid, "x": xy[0], "y": xy[1], "label": art["coord_labels"].get(pid, "other")}
                for pid, xy in art["coords"].items()],
        "date_range": art.get("date_range"),
    }
