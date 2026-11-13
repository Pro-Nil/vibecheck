import numpy as np

from vibe import finish, model


def _inputs(edge_margin, headline):
    parts = {"looks_like": 0.5, "colour_match": 0.5, "style_match": 0.5}
    style = np.full(len(model.STYLE_KEYS), 0.5, np.float32)
    ranges = {k: {"p10": 0.4, "p90": 0.6} for k in model.STYLE_KEYS}
    typo = {"edge_margin": edge_margin, "headline": headline}
    typo_ranges = {"edge_margin": {"p10": 0.04, "p90": 0.08}, "headline": {"p10": 0.05, "p90": 0.07}}
    return parts, style, ranges, typo, typo_ranges, 0.5


def test_v8_inputs_match_their_names_and_saturate():
    x = model._approval_x(*_inputs(edge_margin=0.0, headline=0.5))   # cramped text, a huge headline
    names = model.APPROVAL_INPUTS[:len(x)]
    assert len(x) == len(names) and names[-1] == "off_edge_margin"
    assert x[names.index("off_edge_margin")] == 1.0                   # far outside, counted as clearly outside
    assert x[names.index("off_headline")] == 1.0                      # (would be ~22 range widths unsaturated)
    assert x[3:].max() <= 1.0


def test_older_models_get_the_inputs_they_were_trained_on():
    args = _inputs(edge_margin=0.0, headline=0.5)
    v7 = model._approval_x(*args, layout=True, v8=False)
    v6 = model._approval_x(*args, layout=False, v8=False)
    assert len(v7) == len(model._approval_x(*args)) - 1
    assert len(v6) == len(v7) - len(finish.LAYOUT_KEYS)
    assert v7.max() > 1.0                                             # no saturation for v7 models
    assert 8 == model.ARTIFACT_VERSION and {6, 7, 8} <= set(model.COMPATIBLE_VERSIONS)
