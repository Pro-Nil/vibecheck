"""Held-out test for the synthetic Demo Studio team: does learning from the seniors' decisions help?

Generates NEW briefs (a different seed from the ones the model was trained on), lets the simulated seniors
decide, then scores every version as a finished design with the trained model. Compares:
  * on-brand score alone (needs no decisions)
  * the final score (on-brand blended with the approval model learned from decisions)
on AUC accepted-vs-rejected and on "picked the version the seniors liked best" within each brief.

    .venv/Scripts/python scripts/eval_demo_team.py [n_briefs]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("VIBE_DATA_DIR", str(ROOT / "data_demo"))
os.environ.setdefault("VIBE_SCHEDULER", "0")
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))
import make_demo_team as M  # noqa: E402
from vibe import model  # noqa: E402
from vibe.db import SessionLocal, Team  # noqa: E402
from sqlalchemy import select  # noqa: E402


def auc(pos, neg):
    pos, neg = np.asarray(pos), np.asarray(neg)
    return float(((pos[:, None] > neg[None]) + 0.5 * (pos[:, None] == neg[None])).mean())


def main(n_briefs: int = 20, seed: int = 999):
    with SessionLocal() as s:
        tid = s.scalar(select(Team.id).where(Team.name == M.TEAM_NAME))
    _, art = model.latest(tid)
    ap = art.get("approval")
    print(f"team {tid}: approval model {'ON (weight %.2f)' % ap['weight'] if ap else 'OFF'}")
    rng = np.random.default_rng(seed)
    rows = []
    for b in range(n_briefs):
        for v in M.make_brief(rng, M.TOPICS[(b * 7) % len(M.TOPICS)]):
            r = model.score(tid, [M.render(v["spec"])], kind="final")
            rows.append({"brief": b, "acc": v["decision"] == "accepted", "true_penalty": v["penalty"],
                         "on_brand": r["components"]["on_brand"] * 100, "final": r["score"],
                         "approval": r["components"].get("approval"), "breaks": v["breaks"]})
    y = np.array([r["acc"] for r in rows])
    print(f"{n_briefs} new briefs, {len(rows)} versions ({y.sum()} accepted, {(~y).sum()} rejected)\n")
    pen = -np.array([r["true_penalty"] for r in rows])
    print(f"ceiling    AUC {auc(pen[y], pen[~y]):.2f}  (the simulated seniors' own hidden score; below 1 because 10 % "
          f"of their decisions are flipped)")
    for key in ("on_brand", "final") + (("approval",) if ap else ()):
        sc = np.array([r[key] if r[key] is not None else np.nan for r in rows], float)
        best_right = []
        for b in range(n_briefs):
            m = [i for i, r in enumerate(rows) if r["brief"] == b]
            pick = m[int(np.nanargmax(sc[m]))]
            best_right.append(rows[pick]["acc"])
        print(f"{key:9s} AUC accepted vs rejected {auc(sc[y], sc[~y]):.2f} | top-scored version was accepted in "
              f"{np.mean(best_right):.0%} of briefs")
    by_rule = {}
    for r in rows:
        for b in r["breaks"]:
            by_rule.setdefault(b, []).append(r["final"])
    clean = [r["final"] for r in rows if not r["breaks"]]
    print(f"\nmedian final score: no rule broken {np.median(clean):.0f}; " +
          ", ".join(f"{k} {np.median(v):.0f}" for k, v in sorted(by_rule.items(), key=lambda kv: np.median(kv[1]))))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
