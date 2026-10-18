"""Placement ownership: layout vs builder vs equation board."""

from __future__ import annotations

from cinemath.render_engine.builder import ScriptRunner
from cinemath.render_engine.layout.pass_layout import _apply_next_to
from cinemath.templates.tools import _plot_integral_1d_scene
from layout_helpers import build_scene_mobjects, reset_composition

_INTEGRAL = {
    "expr": "x*exp(x)",
    "x_min": -0.5,
    "x_max": 1.5,
    "shade_min": 0.0,
    "shade_max": 1.0,
    "lower": 0.0,
    "upper": 1.0,
}


def test_integral_scene_label_has_no_next_to_hint() -> None:
    scene = _plot_integral_1d_scene(_INTEGRAL, index=0)
    label = next(o for o in scene["objects"] if o["type"] == "math")
    assert "next_to" not in label
    assert "at" not in label


def test_apply_next_to_skips_labels_when_separate_labels() -> None:
    try:
        scene = _plot_integral_1d_scene(_INTEGRAL, index=0)
        label = next(o for o in scene["objects"] if o["type"] == "math")
        label["next_to"] = next(o["id"] for o in scene["objects"] if o["type"] == "axes")
        label["direction"] = "up"
        _stage, mobjects, _meta = build_scene_mobjects(scene, "mobile")
        lab_id = label["id"]
        before = mobjects[lab_id].get_center().copy()
        _apply_next_to(mobjects, scene, skip_labels=True)
        assert (mobjects[lab_id].get_center() - before).any() < 1e-6
    finally:
        reset_composition()


def _runner() -> ScriptRunner:
    return ScriptRunner(scene=None, script={"scenes": []})  # type: ignore[arg-type]


def test_layout_owns_plot_labels_not_builder() -> None:
    runner = _runner()
    runner._board_scene = False
    runner._separate_labels = True
    assert runner._layout_owns_placement({"type": "math", "id": "x"})
    assert runner._layout_owns_placement({"type": "math", "id": "x", "at": "title"})


def test_board_scene_math_owned_by_equation_board() -> None:
    runner = _runner()
    runner._board_scene = True
    runner._separate_labels = True
    assert runner._layout_owns_placement({"type": "math", "id": "eq1"})


def test_paper_arithmetic_labels_use_builder_place() -> None:
    runner = _runner()
    runner._board_scene = False
    runner._separate_labels = False
    assert not runner._layout_owns_placement({"type": "math", "id": "x", "at": "title"})
