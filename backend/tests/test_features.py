import numpy as np

from conftest import other_style_image, team_style_image
from vibe import augment, features


def test_style_features_are_in_range():
    f = features.extract([team_style_image(1)])[0]
    assert f["clip"].shape == (features.CLIP_DIM,)
    assert abs(np.linalg.norm(f["clip"]) - 1) < 1e-4
    for k in features.STYLE_KEYS:
        assert 0.0 <= f[k] <= 1.0, k
    assert len(f["palette"]) == 5
    assert abs(sum(c["share"] for c in f["palette"]) - 1) < 0.01


def test_features_tell_styles_apart():
    t = features.extract([team_style_image(2)])[0]
    o = features.extract([other_style_image(2)])[0]
    assert t["warmth"] > o["warmth"]          # orange vs blue
    assert t["busyness"] < o["busyness"]      # one block vs forty shapes
    assert t["whitespace"] > o["whitespace"]


def test_palette_finds_main_colour():
    pal = features.palette(team_style_image(3))
    r, g, b = (int(pal[0]["hex"][i:i + 2], 16) for i in (1, 3, 5))
    assert r > 200 and b < 90  # the orange background is the biggest colour


def test_near_miss_changes_image():
    img = team_style_image(4)
    for seed in range(8):
        out, how = augment.near_miss(img, seed)
        assert how in augment.TRANSFORMS
        assert out.size[0] > 0
        assert np.abs(np.asarray(out.resize(img.size), float) - np.asarray(img, float)).mean() > 1


def test_pad_square_keeps_the_whole_poster():
    """v5: a 4:5 poster is padded (not cropped) before CLIP, so its top and bottom stay visible."""
    import numpy as np
    from PIL import Image
    from vibe.features import pad_square
    im = Image.new("RGB", (400, 500), (250, 240, 230))
    im.paste((10, 10, 10), (0, 0, 400, 40))       # a dark title band at the very top
    sq = pad_square(im)
    assert sq.size == (500, 500)
    a = np.asarray(sq)
    assert (a[:40, 50:450] < 20).all()             # the title band survives
    assert tuple(a[250, 10]) == (250, 240, 230)    # padding uses the poster's own edge colour
