"""The adaptive core: learns one team's style and scores a designer's plan against it.

ON-BRAND (0-100) is a percentile against the team's OWN posts: 40 means "more on-brand than 40 % of
this team's posts". It needs no rejected examples. Two signals:

  * looks-like   - mean CLIP similarity to the 10 most similar team posts, ignoring near-twins
                   (posts from the same series; > 0.90 similar) so a new poster is not punished for
                   having no twin.
  * colour-match - Lab colour histogram compared only with the 8 team posts on the most similar topic
                   (by CLIP), so a talk poster is judged against past talk posters, not Diwali wishes.

v4: percentiles are kernel-smoothed (a design far below every team post still ranks below one just
below), and the two signals are combined on the normal z scale, look weighted 2:1. With plain
percentiles every unusual design scored 0, so new one-offs tied with bad drafts. The verdict lines are
set from how the team's real NEW posts scored when the model only knew older posts (time-forward), so
about 10 % of genuinely approved new posts land "Off-brand". scripts/evaluate.py measures all of this:
time-forward AUC new-posts-vs-rejected-drafts 0.76 -> 0.90 on the first team.

When at least MIN_OTHER posts from other pages exist (real "not us" examples), a logistic-regression
classifier (team vs other pages + near-misses) is blended in, weighted by its held-out AUC.

A written description adds a text percentile (vs 40 typical poster descriptions), 25 % of the total.

APPEAL is the LAION aesthetic score as a percentile among team posts. It predicts likes a little
(Spearman 0.25 on the first team) but rated the team's rejected drafts HIGHER than accepted posters,
so it feeds the likes model and is shown separately; it never changes the on-brand verdict.

APPROVAL (v3) is a small supervised model trained only on designs whose outcome is known (the seniors
accepted or rejected that exact design: History outcomes and uploads with a decision). Inputs are a
dozen readable numbers (on-brand parts, distance from the team's usual style and typography, appeal).
It is validated leaving out one whole project (brief) at a time and switched on only when there are at
least MIN_DECIDED accepted and rejected designs from MIN_PROJECTS projects and it beats guessing; it is
then blended into FINAL-design scores by how well it did. Instagram posts alone never train it: they
only show what got posted, and on the first team they taught "routine series post vs one-off".

Rejected drafts without a decision-aware model are never trained on; they only test the model.
"""
from __future__ import annotations

import json
import threading
from collections import defaultdict

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
from . import finish
from .features import STYLE_KEYS, STYLE_LABELS, STYLE_WORDS

TOP_K = 10                # nearest team posts for "looks like" (8-10 tested equal; 5 was worse)
LOOK_WEIGHT = 2.0         # look : colour on the z scale (1.5-3 tested equal)
TOPIC_K = 8               # same-topic team posts for "colour match"
TWIN_SIM = 0.90           # above this CLIP similarity two posts count as the same series
MIN_OTHER = 20            # other-page posts needed before the classifier is used
IMG_WEIGHT, TEXT_WEIGHT = 0.75, 0.25
ONE_CLASS_THRESHOLDS = {"approve": 30.0, "borderline": 12.0}  # fallback when lines can't be calibrated
NEW_POST_OFF_RATE = 0.10  # calibrated lines: share of real new team posts allowed below "borderline"
NEW_POST_ON_RATE = 0.50   # ... and share that reaches "on-brand" (the median new post)
MIN_CALIBRATION = 15      # new-post scores needed to calibrate the lines
NEAR_MISS_MAX_SIM = 0.85  # near-misses closer than this to their original are contradictory, not used
STYLE_TOLERANCE = 0.04    # a feature within 4 points of the team's usual range still counts as fitting
MIN_DECIDED = 8           # accepted AND rejected designs needed before the approval model is used
MIN_PROJECTS = 3          # ...from at least this many different projects (briefs)
MIN_APPROVAL_AUC = 0.60   # leave-one-project-out AUC it must reach to be used
MAX_APPROVAL_WEIGHT = 0.6
ARTIFACT_VERSION = 5          # v5: CLIP sees the whole poster (padded), vectors re-embedded
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
            out["hist"].append(np.frombuffer(f.hist, np.float32) if f.hist else None)
            out["aesthetic"].append(f.aesthetic)
            out["likes"].append(p.likes)
            out["posted_at"].append(p.posted_at)
            out["external_id"].append(p.external_id)
            out["source_page"].append(p.source_page)
            out["decision"].append(p.decision)
            out["project"].append(p.project or "")
            out["typo"].append(json.loads(f.typo_json) if f.typo_json else None)
    if not out:
        return {"id": np.array([], int), "label": np.array([], object)}
    d = {k: v for k, v in out.items()}
    d["id"] = np.array(d["id"])
    d["label"] = np.array(d["label"], dtype=object)
    d["clip"] = np.stack(d["clip"]).astype(np.float32)
    d["style"] = np.array(d["style"], dtype=np.float32)
    nbins = features.HIST_BINS ** 3
    d["hist"] = np.stack([h if h is not None else np.full(nbins, 1 / nbins, np.float32) for h in d["hist"]])
    d["aesthetic"] = np.array([a if a is not None else np.nan for a in d["aesthetic"]], dtype=np.float32)
    return d


def _X(clip: np.ndarray, style: np.ndarray) -> np.ndarray:
    return np.hstack([clip, style])


def _topk_sim(q: np.ndarray, ref: np.ndarray, k: int = TOP_K) -> np.ndarray:
    """Mean cosine similarity of each row of q to its k nearest rows of ref."""
    if len(ref) == 0:
        return np.zeros(len(q))
    sims = q @ ref.T
    k = max(1, min(k, ref.shape[0]))
    return (-np.partition(-sims, k - 1, axis=1)[:, :k]).mean(axis=1)


def _ecdf(sorted_ref: np.ndarray, x) -> np.ndarray:
    x = np.atleast_1d(x)
    if len(sorted_ref) == 0:
        return np.full(len(x), 0.5)
    return np.searchsorted(sorted_ref, x, side="right") / len(sorted_ref)


def _smooth_ecdf(sorted_ref: np.ndarray, x, h: float) -> np.ndarray:
    """Kernel-smoothed percentile: the ECDF in the middle, but keeps ordering beyond the extremes."""
    from scipy.stats import norm
    x = np.atleast_1d(np.asarray(x, float))
    if len(sorted_ref) == 0:
        return np.full(len(x), 0.5)
    return norm.cdf((x[:, None] - sorted_ref[None]) / h).mean(1)


def _bandwidth(ref: np.ndarray) -> float:
    return float(1.06 * np.std(ref) * max(1, len(ref)) ** -0.2 + 1e-9)   # Silverman


def _probit(p: float) -> float:
    from scipy.stats import norm
    return float(norm.ppf(np.clip(p, 1e-4, 1 - 1e-4)))


def _chi2(h: np.ndarray, H: np.ndarray) -> np.ndarray:
    return np.sum((H - h) ** 2 / (H + h + 1e-9), axis=1)


def _parent_of(ext_id: str) -> int | None:
    # near-miss rows are named aug<k>_<parent post id>
    try:
        return int(ext_id.split("_", 1)[1]) if ext_id.startswith("aug") else None
    except (IndexError, ValueError):
        return None


# ---------------------------------------------------------------------- on-brand
class _OnBrand:
    """One-class 'on-brand' scorer built only from the team's own posts."""

    def __init__(self, team_clip: np.ndarray, team_hist: np.ndarray):
        self.vecs, self.hist = team_clip, team_hist
        raw = [self._raw(team_clip[i], team_hist[i], exclude=i) for i in range(len(team_clip))]
        self.ref_look = np.sort([r[0] for r in raw])
        self.ref_colour = np.sort([r[1] for r in raw])
        self.h_look, self.h_colour = _bandwidth(self.ref_look), _bandwidth(self.ref_colour)
        self.ref_combined = np.sort([self._z(*self._pcts(a, b)) for a, b in raw])
        self.h_combined = _bandwidth(self.ref_combined)

    def _raw(self, v: np.ndarray, h: np.ndarray, exclude: int | None = None) -> tuple[float, float]:
        sims = self.vecs @ v
        ok = sims < TWIN_SIM                       # drop near-twins (and the post itself)
        if exclude is not None:
            ok[exclude] = False
        if ok.sum() < 3:                           # tiny teams: fall back to everything but itself
            ok = np.ones(len(sims), bool)
            if exclude is not None:
                ok[exclude] = False
        cand = np.where(ok)[0]
        look = float(np.sort(sims[cand])[-TOP_K:].mean())
        topic = cand[np.argsort(-sims[cand])[:TOPIC_K]]
        colour = -float(_chi2(h, self.hist[topic]).mean())   # higher = closer
        return look, colour

    def _pcts(self, look: float, colour: float) -> tuple[float, float]:
        return (float(_smooth_ecdf(self.ref_look, look, self.h_look)[0]),
                float(_smooth_ecdf(self.ref_colour, colour, self.h_colour)[0]))

    @staticmethod
    def _z(lp: float, cp: float) -> float:
        return (LOOK_WEIGHT * _probit(lp) + _probit(cp)) / (LOOK_WEIGHT + 1)

    def parts(self, v: np.ndarray, h: np.ndarray, exclude: int | None = None) -> dict:
        lp, cp = self._pcts(*self._raw(v, h, exclude))
        return {"looks_like": lp, "colour_match": cp,
                "on_brand": float(_smooth_ecdf(self.ref_combined, self._z(lp, cp), self.h_combined)[0])}


def _new_post_scores(d: dict, is_team: np.ndarray) -> tuple[np.ndarray, str]:
    """On-brand scores (0-1) the team's own posts got when the model knew only OLDER posts (each month vs
    everything before it). If too few posts are dated, each series is scored against all other series."""
    team = np.where(is_team)[0]
    months = np.array([d["posted_at"][i].strftime("%Y-%m") if d["posted_at"][i] else "9999-99" for i in team], object)
    out = []
    for m in sorted(set(months))[1:]:
        ref, test = team[months < m], team[months == m]
        if len(ref) < 10:
            continue
        ob = _OnBrand(d["clip"][ref], d["hist"][ref])
        out += [ob.parts(d["clip"][i], d["hist"][i])["on_brand"] for i in test]
    if len(out) >= MIN_CALIBRATION:
        return np.array(out), "time-forward"
    # series held out: connected groups of posts more than TWIN_SIM similar
    S = d["clip"][team] @ d["clip"][team].T
    group = np.arange(len(team))
    for i in range(len(team)):
        for j in np.where(S[i] > TWIN_SIM)[0]:
            group[group == group[j]] = group[i]
    out = []
    for g in set(group):
        ref = team[group != g]
        if len(ref) < 10:
            continue
        ob = _OnBrand(d["clip"][ref], d["hist"][ref])
        out += [ob.parts(d["clip"][i], d["hist"][i])["on_brand"] for i in team[group == g]]
    return np.array(out), "series held out"


def _calibrated_thresholds(d: dict, is_team: np.ndarray) -> tuple[dict, dict, np.ndarray]:
    scores, how = _new_post_scores(d, is_team)
    if len(scores) < MIN_CALIBRATION:
        return (dict(ONE_CLASS_THRESHOLDS), {"method": "fixed (too few posts to calibrate)", "n": int(len(scores))},
                np.array([]))
    border = float(np.percentile(100 * scores, 100 * NEW_POST_OFF_RATE))
    approve = float(np.percentile(100 * scores, 100 * (1 - NEW_POST_ON_RATE)))
    th = {"approve": round(max(approve, border + 3, 5.0), 1), "borderline": round(max(border, 0.5), 1)}
    return th, {"method": how, "n": int(len(scores)), "new_post_median": round(float(np.median(100 * scores)), 1),
                "new_posts_off_brand": round(float((100 * scores < th["borderline"]).mean()), 3),
                "new_posts_on_brand": round(float((100 * scores >= th["approve"]).mean()), 3)}, np.sort(100 * scores)


def _classifier(clip, style, is_pos):
    clf = make_pipeline(StandardScaler(), LogisticRegression(C=0.05, class_weight="balanced", max_iter=3000))
    clf.fit(_X(clip, style), is_pos.astype(int))
    return clf


def _blend_weight(auc_clf: float, auc_onbrand: float) -> float:
    """Classifier's share of the score, by how much better than guessing each did on held-out posts."""
    c, o = max(auc_clf - 0.5, 0.02), max(auc_onbrand - 0.5, 0.02)
    return c / (c + o)


# ---------------------------------------------------------------------- text
# Typical poster styles. A description is judged by how much better it matches the team's posts than
# these do, so the text score is a percentile (0..1) with no hand-tuned scale.
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
    s_team = _topk_sim(text_vecs, team_vecs)
    if len(other_vecs):
        return s_team - _topk_sim(text_vecs, other_vecs)
    return s_team


def _text_reference(team_vecs: np.ndarray, other_vecs: np.ndarray) -> np.ndarray:
    return np.sort(_text_margin(features.embed_texts(REFERENCE_DESCRIPTIONS), team_vecs, other_vecs))


# ---------------------------------------------------------------------- style summary
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
        idx = np.where(m)[0][np.argmin(((lab[m] - km.cluster_centers_[c]) ** 2).sum(1))]
        out.append({"hex": hexes[idx], "share": float(weights[m].sum() / weights.sum())})
    return sorted(out, key=lambda x: -x["share"])


def _palette_distance(plan: list[dict], signature: list[dict]) -> float:
    if not plan or not signature:
        return 0.0
    a, b = _hex_to_lab([c["hex"] for c in plan]), _hex_to_lab([c["hex"] for c in signature])
    w = np.array([c["share"] for c in plan])
    d = np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).sum(-1)).min(1)
    return float((d * w).sum() / w.sum())


# ---------------------------------------------------------------------- engagement
def _eng_inputs(clip, style, aes, kind):
    if kind == "style+appeal":
        return np.hstack([style, np.nan_to_num(aes, nan=float(np.nanmean(aes)) if np.isfinite(aes).any() else 4.0)[:, None]])
    return _X(clip, style)


def _engagement(d: dict, team_mask: np.ndarray) -> dict | None:
    """Predict likes relative to the page's usual likes that month. Two candidate models are compared
    by 5-fold cross-validation and the better one is kept."""
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
    cands = {"clip+style": (300.0,), "style+appeal": (10.0,)}
    results = {}
    for kind, (alpha,) in cands.items():
        X = _eng_inputs(d["clip"][idx], d["style"][idx], d["aesthetic"][idx], kind)
        errs, base = [], []
        for tr, te in KFold(5, shuffle=True, random_state=0).split(X):
            reg = make_pipeline(StandardScaler(), Ridge(alpha=alpha)).fit(X[tr], y[tr])
            errs.append(np.abs(reg.predict(X[te]) - y[te]).mean())
            base.append(np.abs(y[tr].mean() - y[te]).mean())
        results[kind] = (float(np.mean(errs)), float(np.mean(base)), alpha)
    kind = min(results, key=lambda k: results[k][0])
    mae, base_mae, alpha = results[kind]
    X = _eng_inputs(d["clip"][idx], d["style"][idx], d["aesthetic"][idx], kind)
    reg = make_pipeline(StandardScaler(), Ridge(alpha=alpha)).fit(X, y)
    corr = []
    cols = [(k, STYLE_LABELS[k], d["style"][idx, j]) for j, k in enumerate(STYLE_KEYS)]
    if np.isfinite(d["aesthetic"][idx]).all():
        cols.append(("appeal", "Audience appeal (LAION)", d["aesthetic"][idx]))
    for k, label, col in cols:
        c = float(np.corrcoef(col, y)[0, 1]) if col.std() > 1e-6 else 0.0
        corr.append({"feature": k, "label": label, "correlation": round(c, 3)})
    return {"model": reg, "kind": kind, "n": len(idx), "mae": mae, "baseline_mae": base_mae,
            "candidates": {k: round(v[0], 3) for k, v in results.items()},
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
    reducer = umap.UMAP(n_neighbors=min(15, len(idx) - 1), min_dist=0.15, metric="cosine", random_state=0,
                        compatibility_layout=True)
    xy = reducer.fit_transform(d["clip"][idx])
    return reducer, {int(d["id"][i]): [float(xy[j, 0]), float(xy[j, 1])] for j, i in enumerate(idx)}


# --------------------------------------------------------------------- approval
APPROVAL_INPUTS = (["looks_like", "colour_match"] + [f"off_{k}" for k in STYLE_KEYS]
                   + ["off_text_area", "off_headline", "off_low_contrast_share", "weak_headline", "appeal"])


def _off(v: float | None, r: dict | None) -> float:
    """How far outside the team's usual (p10-p90) range a value is, in range widths (0 = inside)."""
    if v is None or r is None:
        return 0.0
    width = max(1e-3, r["p90"] - r["p10"])
    return float(max(0.0, r["p10"] - v, v - r["p90"]) / width)


def _approval_x(parts: dict, style: np.ndarray, ranges: dict, typo: dict | None, typo_ranges: dict,
                appeal_pct: float) -> np.ndarray:
    t = typo or {}
    x = [parts["looks_like"], parts["colour_match"]]
    x += [_off(float(style[i]), ranges[k]) for i, k in enumerate(STYLE_KEYS)]
    x += [_off(t.get("text_area"), typo_ranges.get("text_area")), _off(t.get("headline"), typo_ranges.get("headline")),
          _off(finish._weak_share(t), typo_ranges.get("weak_share")),
          float((finish._headline_contrast(t) or 21.0) < finish.MIN_CONTRAST),
          appeal_pct]
    return np.array(x, np.float32)


def _approval(d: dict, ob: "_OnBrand", team_rows: np.ndarray, ranges: dict, typo_ranges: dict,
              team_aes: np.ndarray) -> tuple[dict | None, dict]:
    """Train the approval model on designs with a known decision, if there are enough of them.
    Returns (model or None, status metrics). Also reports how the plain on-brand score ranks them."""
    from sklearn.model_selection import LeaveOneGroupOut
    dec = np.array([x or "" for x in d["decision"]], object)
    idx = np.where(np.isin(dec, ["accepted", "rejected"]))[0]
    pos_in_team = {int(r): j for j, r in enumerate(team_rows)}
    y = (dec[idx] == "accepted").astype(int)
    groups = np.array([d["project"][i] or f"design-{d['id'][i]}" for i in idx], object)
    named = {g for g in groups if not g.startswith("design-")}
    status = {"n_accepted": int(y.sum()), "n_rejected": int((1 - y).sum()), "n_projects": len(named),
              "needs": {"accepted": max(0, MIN_DECIDED - int(y.sum())),
                        "rejected": max(0, MIN_DECIDED - int((1 - y).sum())),
                        "projects": max(0, MIN_PROJECTS - len(named))},
              "on": False}
    if len(idx) == 0:
        return None, status
    X, ob_score = [], []
    for i in idx:
        parts = ob.parts(d["clip"][i], d["hist"][i], exclude=pos_in_team.get(int(i)))  # leave itself out
        a = d["aesthetic"][i]
        ap = float(_ecdf(team_aes, a)[0]) if np.isfinite(a) and len(team_aes) else 0.5
        X.append(_approval_x(parts, d["style"][i], ranges, d["typo"][i], typo_ranges, ap))
        ob_score.append(parts["on_brand"])
    X, ob_score = np.array(X), np.array(ob_score)

    def pair_rate(score):  # share of (accepted, rejected) pairs from the SAME project ranked right
        right = total = 0
        for g in set(groups):
            m = groups == g
            a, r = score[m & (y == 1)], score[m & (y == 0)]
            for v in a:
                right += float((v > r).sum() + 0.5 * (v == r).sum())
                total += len(r)
        return (round(right / total, 3), total) if total else (None, 0)

    if y.min() != y.max():
        status["on_brand_auc"] = round(float(roc_auc_score(y, ob_score)), 3)
    status["on_brand_pairs_right"], status["n_pairs"] = pair_rate(ob_score)
    if any(status["needs"].values()):
        return None, status
    pred = np.zeros(len(y))
    for tr, te in LeaveOneGroupOut().split(X, y, groups):
        if y[tr].min() == y[tr].max():
            pred[te] = 0.5
            continue
        m = make_pipeline(StandardScaler(), LogisticRegression(C=0.3, class_weight="balanced", max_iter=2000))
        pred[te] = m.fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
    auc = float(roc_auc_score(y, pred))
    status.update({"auc": round(auc, 3), "pairs_right": pair_rate(pred)[0]})
    if auc < MIN_APPROVAL_AUC:
        status["why_off"] = f"leave-one-project-out AUC {auc:.2f} is below {MIN_APPROVAL_AUC}"
        return None, status
    model = make_pipeline(StandardScaler(), LogisticRegression(C=0.3, class_weight="balanced", max_iter=2000)).fit(X, y)
    w = float(min(MAX_APPROVAL_WEIGHT, 2 * (auc - 0.5)))
    coefs = model[-1].coef_[0]
    status.update({"on": True, "weight": round(w, 3),
                   "top_inputs": [{"input": APPROVAL_INPUTS[j], "coef": round(float(coefs[j]), 3)}
                                  for j in np.argsort(-np.abs(coefs))[:5]]})
    return {"model": model, "weight": w}, status


# --------------------------------------------------------------------- train
def _usable_near_misses(d, is_aug):
    row_of = {int(pid): i for i, pid in enumerate(d["id"])}
    keep = is_aug.copy()
    for i in np.where(is_aug)[0]:
        p = row_of.get(_parent_of(d["external_id"][i]))
        if p is None or float(d["clip"][i] @ d["clip"][p]) > NEAR_MISS_MAX_SIM:
            keep[i] = False
    return keep


def _onbrand_scores(ob: _OnBrand, clip, hist) -> np.ndarray:
    return np.array([ob.parts(clip[i], hist[i])["on_brand"] for i in range(len(clip))])


def train(team_id: int) -> dict:
    d = load_team_data(team_id)
    if len(d["id"]) == 0 or (d["label"] == "team").sum() < 3:
        raise NotTrained("Need at least 3 team posts with features to train.")
    lab = d["label"]
    is_team, is_other, is_rej = lab == "team", lab == "other", lab == "rejected"
    is_aug_all = lab == "augmented"
    is_aug = _usable_near_misses(d, is_aug_all)
    use_clf = int(is_other.sum()) >= MIN_OTHER
    metrics: dict = {"mode": "classifier + on-brand" if use_clf else "on-brand only (no other pages yet)",
                     "n_team": int(is_team.sum()), "n_other": int(is_other.sum()),
                     "n_near_miss": int(is_aug.sum()), "n_near_miss_dropped": int(is_aug_all.sum() - is_aug.sum()),
                     "n_rejected": int(is_rej.sum())}
    rng = np.random.default_rng(0)
    thresholds, metrics["calibration"], new_post_scores = _calibrated_thresholds(d, is_team)
    w_clf = 0.0

    # ---- hold-out test (20 % of team posts + 20 % of other pages; near-misses follow their parent)
    if use_clf:
        team_idx, other_idx = np.where(is_team)[0], np.where(is_other)[0]
        test = np.zeros(len(lab), bool)
        test[rng.choice(team_idx, max(1, len(team_idx) // 5), replace=False)] = True
        test[rng.choice(other_idx, max(1, len(other_idx) // 5), replace=False)] = True
        test_ids = {int(d["id"][i]) for i in np.where(test & is_team)[0]}
        for i in np.where(is_aug)[0]:
            if _parent_of(d["external_id"][i]) in test_ids:
                test[i] = True
        neg = is_other | is_aug
        tr = (is_team | neg) & ~test
        clf = _classifier(d["clip"][tr], d["style"][tr], is_team[tr])
        ob = _OnBrand(d["clip"][tr & is_team], d["hist"][tr & is_team])
        te = test & (is_team | is_other)
        y = is_team[te].astype(int)
        p_clf = clf.predict_proba(_X(d["clip"][te], d["style"][te]))[:, 1]
        p_ob = _onbrand_scores(ob, d["clip"][te], d["hist"][te])
        auc_c, auc_o = float(roc_auc_score(y, p_clf)), float(roc_auc_score(y, p_ob))
        w_clf = _blend_weight(auc_c, auc_o)
        vibe = 100 * (w_clf * p_clf + (1 - w_clf) * p_ob)
        fpr, tpr, thr = roc_curve(y, vibe)
        t = float(thr[np.argmax(tpr - fpr)])
        below = vibe[vibe < t]
        best = float(np.clip((t + below.max()) / 2 if len(below) else t, 30, 85))
        thresholds = {"approve": round(best, 1), "borderline": round(max(5.0, best - 20), 1)}
        pred = vibe >= thresholds["approve"]
        metrics.update({"n_test": int(te.sum()), "auc_classifier": round(auc_c, 3), "auc_on_brand": round(auc_o, 3),
                        "auc": round(float(roc_auc_score(y, vibe)), 3),
                        "accuracy": round(float((pred == y.astype(bool)).mean()), 3),
                        "team_posts_passing": round(float(pred[y == 1].mean()), 3),
                        "test_scores": {"team": [round(float(v), 1) for v in vibe[y == 1]],
                                        "other": [round(float(v), 1) for v in vibe[y == 0]]}})

    # ---- final model on everything (real rejects excluded)
    ob = _OnBrand(d["clip"][is_team], d["hist"][is_team])
    clf = _classifier(d["clip"][is_team | is_other | is_aug], d["style"][is_team | is_other | is_aug],
                      is_team[is_team | is_other | is_aug]) if use_clf else None

    def total(clip, style, hist):
        o = _onbrand_scores(ob, clip, hist)
        if clf is None:
            return 100 * o
        return 100 * (w_clf * clf.predict_proba(_X(clip, style))[:, 1] + (1 - w_clf) * o)

    if is_rej.any():
        rv = total(d["clip"][is_rej], d["style"][is_rej], d["hist"][is_rej])
        metrics["real_rejects"] = {"n": int(is_rej.sum()),
                                   "below_approve": int((rv < thresholds["approve"]).sum()),
                                   "below_borderline": int((rv < thresholds["borderline"]).sum()),
                                   "scores": [round(float(v), 1) for v in rv]}
    if is_aug.any():
        av = total(d["clip"][is_aug], d["style"][is_aug], d["hist"][is_aug])
        metrics["near_misses_below_approve"] = round(float((av < thresholds["approve"]).mean()), 3)
    metrics["thresholds"] = thresholds
    metrics["weights"] = {"classifier": round(w_clf, 3), "on_brand": round(1 - w_clf, 3)}

    other_rows = is_other
    if other_rows.sum() > 3000:
        keep = rng.choice(np.where(other_rows)[0], 3000, replace=False)
        other_rows = np.zeros(len(lab), bool)
        other_rows[keep] = True
    eng = _engagement(d, is_team)
    if eng:
        metrics["engagement"] = {"n": eng["n"], "model": eng["kind"], "mae": round(eng["mae"], 3),
                                 "baseline_mae": round(eng["baseline_mae"], 3), "candidates": eng["candidates"]}
    team_aes = d["aesthetic"][is_team]
    team_aes = np.sort(team_aes[np.isfinite(team_aes)])
    ranges = _style_ranges(d["style"][is_team], d["style"][is_other])
    typo_ranges = finish.team_ranges([t for t, m in zip(d["typo"], is_team) if m])
    approval, metrics["approval"] = _approval(d, ob, np.where(is_team)[0], ranges, typo_ranges, team_aes)
    reducer, coords = _style_map(d)
    team_dates = [p for p, t in zip(d["posted_at"], is_team) if t and p]
    artifact = {
        "version": ARTIFACT_VERSION, "onbrand": ob, "new_post_scores": new_post_scores, "approval": approval, "typo_ranges": typo_ranges, "clf": clf, "w_clf": w_clf, "thresholds": thresholds,
        "team_vecs": d["clip"][is_team], "team_ids": d["id"][is_team], "other_vecs": d["clip"][other_rows],
        "team_aesthetic": team_aes,
        "ranges": ranges,
        "signature_palette": _signature_palette([p for p, t in zip(d["palette"], is_team) if t]),
        "engagement": eng, "umap": reducer, "coords": coords,
        "coord_labels": {int(i): str(l) for i, l in zip(d["id"], lab)},
        "date_range": [min(team_dates).isoformat(), max(team_dates).isoformat()] if team_dates else None,
    }
    artifact["text_ref"] = _text_reference(artifact["team_vecs"], artifact["other_vecs"])
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
        if art.get("version") != ARTIFACT_VERSION:
            raise NotTrained("This team's model was trained by an older version. Retrain it from Team setup.")
        _cache[team_id] = (mv_id, art)
        return mv_id, art


# ----------------------------------------------------------------------- score
def _verdict(score: float, th: dict) -> tuple[str, str]:
    if score >= th["approve"]:
        return "approve", "On-brand"
    if score >= th["borderline"]:
        return "borderline", "Borderline"
    return "reject", "Off-brand"


def _pct(v: float) -> int:
    return int(round(100 * v))


def score(team_id: int, images: list[Image.Image], description: str = "", kind: str = "plan",
          plan_images: list[Image.Image] | None = None, plan_result: dict | None = None) -> dict:
    """kind="plan": inspiration images and/or a description, before designing.
    kind="final": exactly one finished design; adds finish checks, the learned approval model (when it
    has enough decided designs) and, with plan_images/plan_result, how the final compares with its plan."""
    if kind not in ("plan", "final"):
        raise ValueError("kind must be 'plan' or 'final'")
    if kind == "final":
        if len(images) != 1:
            raise ValueError("Send exactly one image: your finished design.")
        description = ""
    if not images and not description.strip():
        raise ValueError("Send at least one inspiration image or a description.")
    mv_id, art = latest(team_id)
    ob: _OnBrand = art["onbrand"]
    clf, w_clf, th = art["clf"], art["w_clf"], art["thresholds"]
    out: dict = {"model_version": mv_id, "thresholds": th, "components": {}, "kind": kind,
                 "weights": {"classifier": round(w_clf, 3), "on_brand": round(1 - w_clf, 3)}}

    def image_score(clip, style, hist):
        p = ob.parts(clip, hist)
        s = p["on_brand"] if clf is None else (w_clf * float(clf.predict_proba(_X(clip[None], style[None]))[0, 1])
                                               + (1 - w_clf) * p["on_brand"])
        return 100 * s, p

    plan_vec = plan_style = plan_hist = None
    plan_palette: list[dict] = []
    img_score = None
    appeal = None
    if images:
        feats = features.extract(images)
        clip = np.stack([f["clip"] for f in feats])
        style = np.array([[f[k] for k in STYLE_KEYS] for f in feats], dtype=np.float32)
        hists = np.stack([f["hist"] for f in feats])
        plan_vec = clip.mean(0)
        plan_vec /= np.linalg.norm(plan_vec) + 1e-8
        plan_style, plan_hist = style.mean(0), hists.mean(0)
        img_score, parts = image_score(plan_vec, plan_style, plan_hist)
        out["components"].update({"looks_like": round(parts["looks_like"], 3),
                                  "colour_match": round(parts["colour_match"], 3),
                                  "on_brand": round(parts["on_brand"], 3), "image_score": round(img_score, 1)})
        if clf is not None:
            out["components"]["classifier"] = round(float(np.mean(clf.predict_proba(_X(clip, style))[:, 1])), 3)
        out["per_image"] = [round(image_score(clip[i], style[i], hists[i])[0], 1) for i in range(len(feats))]
        merged = defaultdict(float)
        for f in feats:
            for c in f["palette"]:
                merged[c["hex"]] += c["share"] / len(feats)
        plan_palette = [{"hex": h, "share": round(v, 3)} for h, v in sorted(merged.items(), key=lambda x: -x[1])][:6]
        aes = features.aesthetic(plan_vec)
        if aes is not None and len(art["team_aesthetic"]):
            appeal = {"score": round(aes, 2), "percentile": round(float(_ecdf(art["team_aesthetic"], aes)[0]), 3)}

    text_score = text_vec = None
    if description.strip():
        text_vec = features.embed_texts([description.strip()])[0]
        margin = _text_margin(text_vec[None], art["team_vecs"], art["other_vecs"])
        text_score = float(_ecdf(art["text_ref"], margin)[0])
        out["components"]["text"] = round(text_score, 3)

    if img_score is not None and text_score is not None:
        total = IMG_WEIGHT * img_score + TEXT_WEIGHT * 100 * text_score
    elif img_score is not None:
        total = img_score
    else:
        total = 100 * text_score

    # ---- finished design: finish checks, learned approval, plan vs final
    out["finish"] = None
    if kind == "final":
        typo = finish.typography(images[0])
        items = finish.checks(typo, art.get("typo_ranges", {}))
        out["finish"] = {"checks": items, "must_fix": sum(i["severity"] == "fail" for i in items),
                         "warnings": sum(i["severity"] == "warn" for i in items),
                         "boxes": typo["boxes"]}
        appr = art.get("approval")
        if appr is not None:
            x = _approval_x(parts, plan_style, art["ranges"], typo, art.get("typo_ranges", {}),
                            appeal["percentile"] if appeal else 0.5)
            p_ok = float(appr["model"].predict_proba(x[None])[0, 1])
            out["components"]["approval"] = round(p_ok, 3)
            out["weights"]["approval"] = round(appr["weight"], 3)
            total = (1 - appr["weight"]) * total + appr["weight"] * 100 * p_ok
        if plan_images:
            pv = features.embed_images(plan_images).mean(0)
            pv /= np.linalg.norm(pv) + 1e-8
            out["plan_vs_final"] = {
                "plan_check_id": (plan_result or {}).get("id"),
                "plan_score": (plan_result or {}).get("score"),
                "similarity": round(float(pv @ plan_vec), 3),
                "similarity_pct": round(float(_ecdf(np.sort(ob.ref_look), float(pv @ plan_vec))[0]), 3)}
    total = float(np.clip(total, 0, 100))

    # ---- how much to trust this score
    notes = []
    if img_score is not None and out["components"]["looks_like"] < 0.10:
        notes.append("the team has posted little like this, so there is not much to compare with")
    if len(ob.vecs) < 30:
        notes.append(f"the model knows only {len(ob.vecs)} team posts")
    if kind == "final" and art.get("approval") is None:
        notes.append("not enough accepted/rejected designs yet to learn what the seniors approve")
    sparse = img_score is not None and out["components"]["looks_like"] < 0.10
    out["confidence"] = {"level": "low" if sparse or len(notes) >= 2 else "medium" if notes else "high",
                         "notes": notes}
    level, label = _verdict(total, th)
    nps = art.get("new_post_scores")
    out["vs_new_posts"] = (round(float(_ecdf(nps, total)[0]), 3) if nps is not None and len(nps) else None)
    out.update({"score": round(total, 1), "verdict": label, "verdict_level": level, "appeal": appeal})

    # ---- reasons
    reasons = []
    ranges = art["ranges"]
    if plan_style is not None:
        lp, cp = out["components"]["looks_like"], out["components"]["colour_match"]
        reasons.append({"ok": cp >= 0.15, "feature": "colour_match", "label": "Colours vs similar past posts",
                        "deviation": round((0.5 - cp) * 2, 2),
                        "text": (f"Colours match this team's past posts on similar topics better than {_pct(cp)}% of its own posts do."
                                 if cp >= 0.15 else
                                 f"Colours differ from this team's past posts on similar topics (closer than only {_pct(cp)}% of its own posts).")})
        reasons.append({"ok": lp >= 0.15, "feature": "looks_like", "label": "Overall look",
                        "deviation": round((0.5 - lp) * 2, 2),
                        "text": (f"Overall look is close to this team's past posts (closer than {_pct(lp)}% of its own posts)."
                                 if lp >= 0.15 else
                                 f"Overall look is unlike this team's past posts (closer than only {_pct(lp)}% of its own posts). "
                                 "Normal for a new kind of poster, so check the closest posts below.")})
        for i, k in enumerate(STYLE_KEYS):
            r = ranges[k]
            v = float(plan_style[i])
            dev = (v - r["p50"]) / max(0.05, r["p90"] - r["p10"])
            inside = r["p10"] - STYLE_TOLERANCE <= v <= r["p90"] + STYLE_TOLERANCE
            more, less = STYLE_WORDS[k]
            if inside:
                text = f"{STYLE_LABELS[k]} fits: yours {_pct(v)}, this team usually {_pct(r['p10'])}-{_pct(r['p90'])} (out of 100)."
            else:
                text = (f"{STYLE_LABELS[k]}: your {'design' if kind == 'final' else 'plan'} is {'much ' if abs(dev) > 1.0 else ''}"
                        f"{more if v > r['p50'] else less} than this team's usual posts "
                        f"(yours {_pct(v)}, usual {_pct(r['p10'])}-{_pct(r['p90'])} out of 100).")
            reasons.append({"ok": inside, "feature": k, "label": STYLE_LABELS[k], "text": text,
                            "plan": round(v, 3), "usual_low": round(r["p10"], 3), "usual_mid": round(r["p50"], 3),
                            "usual_high": round(r["p90"], 3), "deviation": round(float(dev), 2)})
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
    sims = art["team_vecs"] @ q
    order = np.argsort(-sims)[:3]
    ids = [int(art["team_ids"][i]) for i in order]
    with SessionLocal() as s:
        posts = {p.id: p.to_dict() for p in s.scalars(select(Post).where(Post.id.in_(ids)))}
    out["nearest"] = [{**posts[i], "similarity": round(float(sims[j]), 3)} for i, j in zip(ids, order) if i in posts]

    # ---- engagement + map point
    eng = art.get("engagement")
    if eng and plan_vec is not None:
        aes_in = np.array([appeal["score"] if appeal else np.nan], np.float32)
        x = _eng_inputs(plan_vec[None], plan_style[None], aes_in, eng["kind"])
        pred = float(eng["model"].predict(x)[0])
        band = "Above usual" if pred > eng["band"] else "Below usual" if pred < -eng["band"] else "Usual"
        out["engagement"] = {"band": band, "predicted_vs_usual": round(float(np.exp(pred)), 2)}
    else:
        out["engagement"] = None
    out["map_point"] = None
    if art.get("umap") is not None and plan_vec is not None:
        try:
            xy = art["umap"].transform(plan_vec[None])[0]
            out["map_point"] = [float(xy[0]), float(xy[1])]
        except Exception:
            pass
    return out


def style_profile(team_id: int) -> dict:
    mv_id, art = latest(team_id)
    with SessionLocal() as s:
        mv = s.get(ModelVersion, mv_id)
        metrics = json.loads(mv.metrics_json)
        trained_at = mv.trained_at.isoformat()
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
