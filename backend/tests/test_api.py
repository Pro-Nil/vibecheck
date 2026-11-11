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
