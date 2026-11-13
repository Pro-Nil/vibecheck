"""End-to-end: create team -> import folders -> train -> check -> outcome -> plugins."""
import io
import time

import pytest

from conftest import other_style_image, team_style_image


def png(img) -> bytes:
    b = io.BytesIO()
    img.save(b, format="PNG")
    return b.getvalue()


def wait(client, job_id, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/jobs/{job_id}").json()
        if j["status"] in ("done", "failed"):
            return j
        time.sleep(0.3)
    raise AssertionError("job timed out")


@pytest.fixture(scope="module")
def team(client, dataset):
    t = client.post("/teams", json={"name": "Test team", "other_pages": []}).json()
    body = {"fetch_instagram": False, "folders": [
        {"path": str(dataset["team"]), "label": "team", "source_page": "ourpage"},
        {"path": str(dataset["other"]), "label": "other", "source_page": "otherpage"},
        {"path": str(dataset["rejected"]), "label": "rejected", "source_page": "drafts"}]}
    r = client.post(f"/teams/{t['id']}/import", json=body)
    assert r.status_code == 202
    j = wait(client, r.json()["job_id"])
    assert j["status"] == "done", j["message"]
    return t


def test_import_counts(client, team):
    counts = client.get(f"/teams/{team['id']}").json()["counts"]
    assert counts["team"] == 40 and counts["other"] == 60 and counts["rejected"] == 4
    assert counts["augmented"] == 40  # one near-miss per team post


def test_meta_csv_read(client, team):
    items = client.get(f"/teams/{team['id']}/posts", params={"label": "team", "limit": 100}).json()["items"]
    assert all(p["likes"] is not None and p["posted_at"] for p in items)


def test_reimport_adds_nothing(client, team, dataset):
    from vibe import importers
    assert importers.import_folder(team["id"], dataset["team"], "team", "ourpage") == 0


def test_model_metrics(client, team):
    m = client.get(f"/teams/{team['id']}/model").json()["current"]["metrics"]
    assert m["auc"] >= 0.85
    assert m["real_rejects"]["n"] == 4
    assert m["real_rejects"]["below_approve"] >= 3
    assert m["engagement"]["n"] == 40
    assert set(m["thresholds"]) == {"approve", "borderline"}


def test_check_scores_team_style_higher(client, team):
    def check(img):
        r = client.post(f"/teams/{team['id']}/checks", files=[("images", ("a.png", png(img), "image/png"))],
                        data={"description": "", "user": "tester"})
        assert r.status_code == 201, r.text
        return r.json()
    good, bad = check(team_style_image(900)), check(other_style_image(900))
    assert good["score"] > bad["score"] + 20
    assert good["verdict_level"] in ("approve", "borderline")
    assert bad["verdict_level"] == "reject"
    assert len(good["nearest"]) == 3 and good["nearest"][0]["image_url"].startswith("/media/")
    assert any(not r["ok"] for r in bad["reasons"])
    assert bad["reasons"][0]["ok"] is False  # problems are listed first
    assert good["map_point"] is not None
    assert client.get(f"/checks/{good['id']}").json()["score"] == good["score"]


def test_description_only_and_empty(client, team):
    r = client.post(f"/teams/{team['id']}/checks", data={"description": "warm orange minimal poster"})
    assert r.status_code == 201 and 0 <= r.json()["score"] <= 100
    assert client.post(f"/teams/{team['id']}/checks", data={"description": " "}).status_code == 400


def test_check_rejects_non_image(client, team):
    r = client.post(f"/teams/{team['id']}/checks", files=[("images", ("a.png", b"not an image", "image/png"))])
    assert r.status_code == 400


def test_untrained_team_gives_409(client):
    t = client.post("/teams", json={"name": "Empty"}).json()
    r = client.post(f"/teams/{t['id']}/checks", data={"description": "x"})
    assert r.status_code == 409


def test_outcome_with_final_image(client, team):
    c = client.get(f"/teams/{team['id']}/checks").json()[0]
    before = client.get(f"/teams/{team['id']}").json()["counts"]["rejected"]
    r = client.post(f"/checks/{c['id']}/outcome", data={"result": "rejected"},
                    files={"final_image": ("f.png", png(other_style_image(777)), "image/png")})
    assert r.status_code == 200 and r.json()["outcome"] == "rejected"
    assert client.get(f"/teams/{team['id']}").json()["counts"]["rejected"] == before + 1


def test_style_profile(client, team):
    p = client.get(f"/teams/{team['id']}/style-profile").json()
    assert len(p["signature_palette"]) >= 3
    assert len(p["map"]) > 50
    assert p["trend"] and "brightness" in p["trend"][0]
    assert p["what_works"]


def test_plugins(client, team, monkeypatch):
    import httpx

    class Resp:
        def __init__(self, payload):
            self.payload = payload
        def raise_for_status(self):
            pass
        def json(self):
            return self.payload

    calls = []
    def fake_post(url, json=None, timeout=None):
        calls.append((url, json))
        if "bad" in url:
            return Resp({"no_title": True})
        return Resp({"title": "Hello", "metrics": [{"label": "n", "value": 3}],
                     "chart": {"type": "bar", "points": [{"label": "a", "value": 1}]}})
    monkeypatch.setattr(httpx, "post", fake_post)

    good = client.post("/plugins", json={"name": "Good", "url": "http://good/hook"}).json()
    bad = client.post("/plugins", json={"name": "Bad", "url": "http://bad/hook", "team_id": team["id"]}).json()
    r = client.post(f"/teams/{team['id']}/checks",
                    files=[("images", ("a.png", png(team_style_image(5)), "image/png"))]).json()
    panels = {p["plugin"]: p for p in r["plugins"]}
    assert panels["Good"]["ok"] and panels["Good"]["panel"]["title"] == "Hello"
    assert panels["Bad"]["ok"] is False
    assert calls[0][1]["event"] == "check.completed" and "reasons" in calls[0][1]["check"]
    # stored with the check
    assert len(client.get(f"/checks/{r['id']}").json()["plugins"]) == 2
    # disable + delete
    client.patch(f"/plugins/{bad['id']}", json={"enabled": False})
    r2 = client.post(f"/teams/{team['id']}/checks", data={"description": "poster"}).json()
    assert [p["plugin"] for p in r2["plugins"]] == ["Good"]
    assert client.delete(f"/plugins/{good['id']}").status_code == 204
    assert client.delete(f"/plugins/{bad['id']}").status_code == 204


def test_features_endpoint(client):
    r = client.post("/features", files={"file": ("a.png", png(team_style_image(1)), "image/png")},
                    params={"include_vector": True}).json()
    assert len(r["clip"]) == 512 and len(r["palette"]) == 5


def test_openapi_has_panel_schema(client):
    spec = client.get("/openapi.json").json()
    assert spec["openapi"].startswith("3.")
    assert "Panel" in spec["components"]["schemas"]
    assert "/teams/{team_id}/checks" in spec["paths"]


def test_description_matters_without_other_pages(client, dataset):
    """Regression: with no other pages the text score used to be a constant (~0.65)."""
    t = client.post("/teams", json={"name": "Team only"}).json()
    r = client.post(f"/teams/{t['id']}/import", json={"fetch_instagram": False, "folders": [
        {"path": str(dataset["team"]), "label": "team", "source_page": "ourpage"}]})
    assert wait(client, r.json()["job_id"])["status"] == "done"
    scores = set()
    for d in ["warm orange minimal poster", "neon cyberpunk city at night", "pastel watercolour flowers",
              "black and white newspaper", "robot cartoon with speech bubbles"]:
        res = client.post(f"/teams/{t['id']}/checks", data={"description": d})
        assert res.status_code == 201
        text = res.json()["components"]["text"]
        assert 0.0 <= text <= 1.0
        scores.add(text)
    assert len(scores) >= 3  # different descriptions give different text scores


def test_on_brand_only_mode_ranks_team_style_higher(client, dataset):
    """Without other pages the score is a percentile against the team's own posts."""
    t = next(x for x in client.get("/teams").json() if x["name"] == "Team only")
    m = client.get(f"/teams/{t['id']}/model").json()["current"]["metrics"]
    assert m["mode"].startswith("on-brand only")
    assert m["weights"]["classifier"] == 0
    def check(img):
        r = client.post(f"/teams/{t['id']}/checks", files=[("images", ("a.png", png(img), "image/png"))])
        assert r.status_code == 201, r.text
        return r.json()
    good, bad = check(team_style_image(321)), check(other_style_image(321))
    assert "classifier" not in good["components"]
    # synthetic team posters are near-identical (similarity ~0.99), so after near-twin exclusion a new good
    # poster sits at the bottom of a very narrow range; the ranking is what matters
    assert good["score"] > bad["score"]
    assert good["components"]["on_brand"] > bad["components"]["on_brand"]
    assert bad["verdict"] == "Off-brand"
    assert {"looks_like", "colour_match", "on_brand"} <= set(good["components"])
    assert good["appeal"] is None or 0 <= good["appeal"]["percentile"] <= 1


# ------------------------------------------------------------------ v3: finished designs + approval
def _text_poster(fg, bg, seed=0):
    from PIL import ImageDraw
    im = team_style_image(seed)
    d = ImageDraw.Draw(im)
    d.rectangle([40, 300, 280, 340], fill=bg)
    for x in range(50, 270, 12):  # letter-like strokes
        d.rectangle([x, 308, x + 6, 332], fill=fg)
    return im


def test_box_contrast():
    import numpy as np
    from vibe import finish
    def ratio(fg, bg):
        a = np.full((40, 200, 3), bg, np.uint8)
        a[10:30, 10:190:8] = fg
        return finish.box_contrast(a, [0, 200, 0, 40])
    assert ratio((0, 0, 0), (255, 255, 255)) > 15
    assert ratio((120, 120, 120), (135, 135, 135)) < 1.5


def test_final_check_has_finish_checklist(client, team):
    one = [("images", ("final.png", png(_text_poster((0, 0, 0), (255, 255, 255))), "image/png"))]
    r = client.post(f"/teams/{team['id']}/checks", files=one, data={"kind": "final"})
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["kind"] == "final" and c["finish"] is not None
    feats = {i["feature"] for i in c["finish"]["checks"]}
    assert "resolution" in feats
    res = next(i for i in c["finish"]["checks"] if i["feature"] == "resolution")
    assert res["ok"] is False  # 320 px wide is below Instagram's 1080
    assert c["confidence"]["level"] in ("low", "medium", "high")
    two = one + [("images", ("b.png", png(team_style_image(5)), "image/png"))]
    assert client.post(f"/teams/{team['id']}/checks", files=two, data={"kind": "final"}).status_code == 400


def test_final_links_to_plan_and_outcome_becomes_decision(client, team):
    plan = client.post(f"/teams/{team['id']}/checks", data={"project": "spring-fest"},
                       files=[("images", ("p.png", png(team_style_image(950)), "image/png"))]).json()
    final = client.post(f"/teams/{team['id']}/checks",
                        data={"kind": "final", "plan_check_id": str(plan["id"])},
                        files=[("images", ("f.png", png(team_style_image(951)), "image/png"))]).json()
    pvf = final["plan_vs_final"]
    assert pvf["plan_check_id"] == plan["id"] and pvf["plan_score"] == plan["score"]
    assert 0 <= pvf["similarity_pct"] <= 1
    assert final["project"] == "spring-fest"  # inherited from the plan
    assert client.get(f"/checks/{plan['id']}").json()["finals"][0]["id"] == final["id"]
    # deciding on a final check records its own image as a decided design (no upload needed)
    client.post(f"/checks/{final['id']}/outcome", data={"result": "rejected"})
    rej = client.get(f"/teams/{team['id']}/posts", params={"label": "rejected", "limit": 100}).json()["items"]
    mine = [p for p in rej if p["project"] == "spring-fest"]
    assert len(mine) == 1 and mine[0]["decision"] == "rejected"


def test_approval_model_needs_decisions_then_turns_on(client):
    from conftest import other_style_image as other
    t = client.post("/teams", json={"name": "Approval team", "other_pages": []}).json()
    tid = t["id"]
    files = [("files", (f"t{i}.png", png(team_style_image(2000 + i)), "image/png")) for i in range(30)]
    wait(client, client.post(f"/teams/{tid}/import/upload", files=files, data={"label": "team"}).json()["job_id"])
    ap = client.get(f"/teams/{tid}/model").json()["current"]["metrics"]["approval"]
    assert ap["on"] is False and ap["needs"]["accepted"] == 5
    for k, proj in enumerate(["a", "b", "c"]):  # 3 briefs, accepted = team style, rejected = off style
        acc = [("files", (f"a{k}{i}.png", png(team_style_image(3000 + 10 * k + i)), "image/png")) for i in range(4)]
        rej = [("files", (f"r{k}{i}.png", png(other(3000 + 10 * k + i)), "image/png")) for i in range(4)]
        client.post(f"/teams/{tid}/import/upload", files=acc, data={"label": "accepted", "project": proj, "train": "false"})
        j = client.post(f"/teams/{tid}/import/upload", files=rej, data={"label": "rejected", "project": proj}).json()
        wait(client, j["job_id"])
    ap = client.get(f"/teams/{tid}/model").json()["current"]["metrics"]["approval"]
    assert ap["n_accepted"] == 12 and ap["n_rejected"] == 12 and ap["n_projects"] == 3
    assert ap["on"] is True and ap["auc"] >= 0.8 and 0 < ap["weight"] <= 0.8
    final = client.post(f"/teams/{tid}/checks", data={"kind": "final"},
                        files=[("images", ("f.png", png(team_style_image(4000)), "image/png"))]).json()
    assert "approval" in final["components"] and final["weights"]["approval"] == ap["weight"]


def test_lines_are_calibrated_on_new_posts(client, dataset):
    """v4: verdict lines come from how the team's later posts scored when the model knew only older ones."""
    t = next(x for x in client.get("/teams").json() if x["name"] == "Team only")
    m = client.get(f"/teams/{t['id']}/model").json()["current"]["metrics"]
    cal = m["calibration"]
    assert cal["n"] >= 15 and cal["method"] in ("time-forward", "series held out")
    assert 0.05 <= cal["new_posts_off_brand"] <= 0.2
    assert m["thresholds"]["borderline"] < m["thresholds"]["approve"]
    r = client.post(f"/teams/{t['id']}/checks", files=[("images", ("a.png", png(team_style_image(77)), "image/png"))]).json()
    assert 0 <= r["vs_new_posts"] <= 1


def test_smooth_scores_keep_order_below_every_team_post():
    """A design far below every team post must score lower than one just below (plain percentiles gave both 0)."""
    import numpy as np
    from vibe.model import _bandwidth, _smooth_ecdf
    ref = np.sort(np.random.default_rng(0).normal(0.7, 0.03, 50))
    lo, very_lo = _smooth_ecdf(ref, [ref.min() - 0.01, ref.min() - 0.2], _bandwidth(ref))
    assert 0 < very_lo < lo < 0.05


def test_upload_with_meta_csv_keeps_dates_likes_and_projects(client):
    tid = client.post("/teams", json={"name": "Meta upload", "other_pages": []}).json()["id"]
    imgs = [("files", (f"p{i}.png", png(team_style_image(i + 500)), "image/png")) for i in range(3)]
    imgs.append(("files", ("2026-04-02_18-30-00_UTC.png", png(team_style_image(599)), "image/png")))
    meta = "filename,posted_at,likes,caption,project\np0.png,2026-03-01,120,first,brief-a\np1.png,2026-03-05,80,,brief-b\n"
    r = client.post(f"/teams/{tid}/import/upload", files=imgs + [("meta", ("meta.csv", meta.encode(), "text/csv"))],
                    data={"label": "accepted", "project": "fallback", "train": "false"})
    assert r.status_code == 201, r.text
    assert r.json()["added"] == 4 and r.json()["with_meta"] == 2 and r.json()["job_id"] is None
    items = {p["caption"] or p["id"]: p for p in client.get(f"/teams/{tid}/posts", params={"label": "team", "limit": 10}).json()["items"]}
    got = [(p["likes"], (p["posted_at"] or "")[:10], p.get("project")) for p in items.values()]
    assert (120, "2026-03-01", "brief-a") in got and (80, "2026-03-05", "brief-b") in got
    assert (None, "2026-04-02", "fallback") in got          # date from an Instaloader-style file name
    bad = client.post(f"/teams/{tid}/import/upload", files=imgs[:1] + [("meta", ("m.csv", b"name,likes\nx,1\n", "text/csv"))],
                      data={"label": "team", "train": "false"})
    assert bad.status_code == 400


def test_delete_team_removes_its_data_only(client, team):
    from vibe import config
    from vibe.db import Job, Post, SessionLocal
    tid = client.post("/teams", json={"name": "To delete", "other_pages": []}).json()["id"]
    imgs = [("files", (f"d{i}.png", png(team_style_image(i + 700)), "image/png")) for i in range(3)]
    assert client.post(f"/teams/{tid}/import/upload", files=imgs, data={"label": "team", "train": "false"}).status_code == 201
    folder = config.IMAGES_DIR / f"team_{tid}"
    assert folder.exists()
    with SessionLocal() as s:                      # a running job blocks the delete
        s.add(Job(team_id=tid, kind="refresh", status="running"))
        s.commit()
        job_id = s.query(Job).filter_by(team_id=tid).one().id
    assert client.delete(f"/teams/{tid}").status_code == 409
    with SessionLocal() as s:
        s.get(Job, job_id).status = "done"
        s.commit()
    r = client.delete(f"/teams/{tid}")
    assert r.status_code == 200 and r.json()["posts"] == 3
    assert client.get(f"/teams/{tid}").status_code == 404
    assert not folder.exists()
    with SessionLocal() as s:
        assert s.query(Post).filter_by(team_id=tid).count() == 0
    assert client.get(f"/teams/{team['id']}").status_code == 200          # other teams untouched
    assert client.delete("/teams/99999").status_code == 404


def test_one_training_run_per_team(client, monkeypatch):
    import threading
    from vibe import pipeline
    from vibe.db import Job, SessionLocal
    gate = threading.Event()
    runs = []

    def slow_refresh(job_id, team_id, **kw):            # stands in for the real run, so the test controls timing
        runs.append(job_id)
        gate.wait(10)
        with SessionLocal() as s:
            j = s.get(Job, job_id)
            j.status, j.progress, j.message = "done", 1.0, "ok"
            s.commit()
    monkeypatch.setattr(pipeline, "run_refresh", slow_refresh)
    tid = client.post("/teams", json={"name": "Gate", "other_pages": []}).json()["id"]
    a = client.post(f"/teams/{tid}/retrain").json()
    b = client.post(f"/teams/{tid}/retrain").json()             # second click while the first runs
    assert not a["joined"] and b["joined"] and b["job_id"] == a["job_id"] and not b["queued_follow_up"]
    img = [("files", ("g.png", png(team_style_image(901)), "image/png"))]
    u = client.post(f"/teams/{tid}/import/upload", files=img, data={"label": "team"}).json()
    assert u["joined"] and u["queued_follow_up"]                  # new images: one follow-up run is queued
    u2 = client.post(f"/teams/{tid}/import/upload", files=img, data={"label": "team"}).json()
    assert u2["joined"]                                           # still only one follow-up
    gate.set()
    t0 = time.time()
    while pipeline.active_job(tid) is not None and time.time() - t0 < 10:
        time.sleep(0.05)
    assert pipeline.active_job(tid) is None
    assert len(runs) == 2                                         # the first run plus exactly one follow-up
    with SessionLocal() as s:
        assert {j.status for j in s.query(Job).filter_by(team_id=tid)} == {"done"}
