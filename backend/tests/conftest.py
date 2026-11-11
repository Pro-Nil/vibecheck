"""Tests run on a throw-away data folder with the fake CLIP (no downloads, a few seconds)."""
import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="vibe_test_")
os.environ["VIBE_DATA_DIR"] = _tmp
os.environ["VIBE_FAKE_CLIP"] = "1"
os.environ["VIBE_SCHEDULER"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402


def team_style_image(seed: int) -> Image.Image:
    """'Our' style: warm orange background, one dark block, lots of empty space."""
    rng = np.random.default_rng(seed)
    im = Image.new("RGB", (320, 400), (int(rng.integers(230, 255)), int(rng.integers(120, 150)), 40))
    d = ImageDraw.Draw(im)
    y = int(rng.integers(40, 260))
    d.rectangle([30, y, 290, y + int(rng.integers(40, 90))], fill=(30, 20, 20))
    return im


def other_style_image(seed: int) -> Image.Image:
    """'Other pages': cool, busy, many coloured shapes."""
    rng = np.random.default_rng(10_000 + seed)
    im = Image.new("RGB", (320, 400), (20, int(rng.integers(60, 120)), int(rng.integers(150, 230))))
    d = ImageDraw.Draw(im)
    for _ in range(40):
        x, y = int(rng.integers(0, 300)), int(rng.integers(0, 380))
        d.rectangle([x, y, x + int(rng.integers(5, 40)), y + int(rng.integers(5, 40))],
                    fill=tuple(int(c) for c in rng.integers(0, 256, 3)))
    return im


@pytest.fixture(scope="session")
def dataset(tmp_path_factory):
    root = tmp_path_factory.mktemp("imgs")
    team, other, rej = root / "team", root / "other", root / "rejected"
    for d in (team, other, rej):
        d.mkdir()
    lines = ["filename,caption,posted_at,likes,comments"]
    for i in range(40):
        team_style_image(i).save(team / f"t{i}.png")
        lines.append(f"t{i}.png,post {i},2025-{1 + i % 12:02d}-{1 + i % 27:02d},{100 + 3 * i},{i % 7}")
    (team / "meta.csv").write_text("\n".join(lines))
    for i in range(60):
        other_style_image(i).save(other / f"o{i}.png")
    for i in range(4):
        other_style_image(500 + i).save(rej / f"r{i}.png")
    return {"team": team, "other": other, "rejected": rej}


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from vibe.main import app
    with TestClient(app) as c:
        yield c
