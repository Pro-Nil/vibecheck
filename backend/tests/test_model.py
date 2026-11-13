import numpy as np

from vibe import finish, model


def _inputs(edge_margin, headline):
    parts = {"looks_like": 0.5, "colour_match": 0.5, "style_match": 0.5}
    style = np.full(len(model.STYLE_KEYS), 0.5, np.float32)
    ranges = {k: {"p10": 0.4, "p50": 0.5, "p90": 0.6} for k in model.STYLE_KEYS}
    typo = {"edge_margin": edge_margin, "headline": headline}
    typo_ranges = {"edge_margin": {"p10": 0.04, "p50": 0.06, "p90": 0.08},
                   "headline": {"p10": 0.05, "p50": 0.06, "p90": 0.07}}
    return parts, style, ranges, typo, typo_ranges, 0.5


def test_v9_inputs_match_their_names():
    x = model._approval_x(*_inputs(edge_margin=0.0, headline=0.5))   # cramped text, a huge headline
    names = model.APPROVAL_INPUTS
    assert len(x) == len(names)
    assert x[names.index("headline_vs_team")] == 2.0                 # signed, clipped at +2 range widths
    assert x[names.index("off_headline")] == 1.0                     # outside, saturated at 1
    assert x[names.index("edge_margin_vs_team")] < 0                 # direction kept: closer to the edge than usual
    assert x[names.index("off_edge_margin")] == 1.0
    assert "looks_like" not in names                                 # look/colour reach the score via the blend


def test_older_models_get_the_inputs_they_were_trained_on():
    args = _inputs(edge_margin=0.0, headline=0.5)
    v8, v7, v6 = (model._approval_x(*args, version=v) for v in (8, 7, 6))
    assert len(v8) == len(model.V8_INPUTS) and v8[3:].max() <= 1.0  # v8: saturated
    assert len(v7) == len(v8) - 1 and v7.max() > 1.0                  # v7: no edge margin, not saturated
    assert len(v6) == len(v7) - len(finish.LAYOUT_KEYS)
    assert {6, 7, 8, 9} <= set(model.COMPATIBLE_VERSIONS) and model.ARTIFACT_VERSION == 9


def test_missing_measurements_are_neutral():
    x = model._approval_x({}, np.full(len(model.STYLE_KEYS), 0.5, np.float32), {}, None, {}, 0.5)
    assert x[0] == 0.5 and not x[1:].any()
