"""Characterization tests: layout bounds per template × composition."""

from __future__ import annotations

import pytest
from manim import VGroup

from cinemath.catalog import plan_quadratic
from cinemath.planners.calculus.integration_by_parts import plan_integration_by_parts
from cinemath.planners.calculus.partial_fractions import plan_partial_fractions
from cinemath.render_engine.composition import apply_manim_config, set_composition_env
from cinemath.render_engine.layout import constraints_for_composition, resolve_template
from cinemath.render_engine.layout.overlap import any_overlap, mobjects_overlap, mobjects_overlap
from cinemath.render_engine.stage import StageConductor, left_archive, right_active, stack_halves
from cinemath.render_engine.validate import AnimValidationError, validate_animation
from cinemath.templates import compile_plan
from cinemath.templates.tools import _plot_integral_1d_scene
from layout_helpers import build_scene_mobjects, reset_composition

_INTEGRAL_VISUAL = {
    "expr": "x*exp(x)",
    "x_min": -0.5,
    "x_max": 1.5,
    "shade_min": 0.0,
    "shade_max": 1.0,
    "lower": 0.0,
    "upper": 1.0,
}

_CHROME = frozenset({"axes", "plot", "dot", "line", "polygon", "flow_field"})
_LABELS = frozenset({"math", "text", "prose"})


def _chrome_group(mobjects, meta):
    return VGroup(
        *[mobjects[oid] for oid, obj in meta.items() if obj["type"] in _CHROME]
    )


def _label_group(mobjects, meta):
    labs = [mobjects[oid] for oid, obj in meta.items() if obj["type"] in _LABELS]
    return VGroup(*labs) if labs else None


# --- plot_with_labels × compositions ---------------------------------------


@pytest.mark.parametrize("composition", ["board", "web", "mobile"])
def test_plot_with_labels_chrome_above_floor(composition: str) -> None:
    try:
        scene = _plot_integral_1d_scene(_INTEGRAL_VISUAL, index=0)
        stage, mobjects, meta = build_scene_mobjects(scene, composition)
        constraints = constraints_for_composition()
        chrome = _chrome_group(mobjects, meta)
        assert float(chrome.get_bottom()[1]) >= constraints.floor - 1e-6
        labels = _label_group(mobjects, meta)
        assert labels is not None
        assert float(labels.get_top()[1]) <= constraints.ceiling + 1e-6
        assert stage.caption_mob is not None
        assert not any_overlap(stage.caption_mob, [chrome, labels])
    finally:
        reset_composition()


@pytest.mark.parametrize("composition", ["board", "web", "mobile"])
def test_integral_label_not_overlapping_chrome(composition: str) -> None:
    try:
        scene = _plot_integral_1d_scene(_INTEGRAL_VISUAL, index=0)
        _stage, mobjects, meta = build_scene_mobjects(scene, composition)
        chrome = _chrome_group(mobjects, meta)
        labels = _label_group(mobjects, meta)
        assert labels is not None
        assert not mobjects_overlap(labels, chrome, pad=0.1)
        axes = next(mobjects[oid] for oid, obj in meta.items() if obj["type"] == "axes")
        tip_y = float(axes.y_axis.get_end()[1])
        spine_x = float(axes.y_axis.get_end()[0])
        assert float(labels.get_bottom()[1]) > tip_y + 0.12
        assert float(labels.get_left()[0]) > spine_x + 0.05
    finally:
        reset_composition()


@pytest.mark.parametrize("composition", ["board", "web", "mobile"])
def test_plot_with_labels_caption_clear_of_content(composition: str) -> None:
    try:
        scene = _plot_integral_1d_scene(_INTEGRAL_VISUAL, index=0)
        stage, mobjects, meta = build_scene_mobjects(scene, composition)
        caption = stage.caption_mob
        assert caption is not None
        content = list(mobjects.values())
        assert content
        assert not any_overlap(caption, content)
        for mob in content:
            assert not mobjects_overlap(caption, mob)
    finally:
        reset_composition()


@pytest.mark.parametrize("composition", ["board", "web", "mobile"])
def test_compiled_ibp_problem_scene_text_bounds(composition: str) -> None:
    """Problem statement + captions stay inside the mobile/web frame."""
    from cinemath.render_engine.problem_statement import build_statement

    try:
        set_composition_env(composition)
        apply_manim_config()
        plan = plan_integration_by_parts(
            r"Evaluate the definite integral $\int_0^1 x e^{x}\,dx$.",
            expression="x*exp(x)",
            variable="x",
            lower=0,
            upper=1,
        )
        animation = validate_animation(compile_plan(plan))
        scene = next(s for s in animation["scenes"] if s["id"] == "problem")
        stmt_obj = next(o for o in scene["objects"] if o["type"] == "statement")
        from cinemath.render_engine.stage import full_frame

        stage = StageConductor(scene=None)  # type: ignore[arg-type]
        region = full_frame()
        stmt = build_statement(stmt_obj["content"], color="white", font_size=30)
        stage.fit(stmt, region, max_scale=1.0)
        assert float(stmt.get_left()[0]) >= region.left - 1e-3
        assert float(stmt.get_right()[0]) <= region.right + 1e-3
        assert float(stmt.get_bottom()[1]) >= region.bottom - 1e-3
        assert float(stmt.get_top()[1]) <= region.top + 1e-3
        assert "caption" not in scene or not str(scene.get("caption") or "").strip()
    finally:
        reset_composition()


@pytest.mark.parametrize("composition", ["board", "web", "mobile"])
def test_compiled_ibp_integral_scene_bounds(composition: str) -> None:
    """integration-by-parts catalog → plot_integral_1d_* × composition."""
    try:
        plan = plan_integration_by_parts(
            r"Evaluate $\int_0^1 x e^{x}\,dx$.",
            expression="x*exp(x)",
            variable="x",
            lower=0,
            upper=1,
        )
        animation = validate_animation(compile_plan(plan))
        scene = next(s for s in animation["scenes"] if s["id"].startswith("plot_integral_1d_"))
        assert scene["template"] == "plot_with_labels"
        stage, mobjects, meta = build_scene_mobjects(scene, composition)
        constraints = constraints_for_composition()
        chrome = _chrome_group(mobjects, meta)
        assert float(chrome.get_bottom()[1]) >= constraints.floor - 1e-6
        labels = _label_group(mobjects, meta)
        assert labels is not None
        assert float(labels.get_top()[1]) <= constraints.ceiling + 1e-6
        assert stage.caption_mob is not None
        assert not any_overlap(stage.caption_mob, list(mobjects.values()))
    finally:
        reset_composition()


@pytest.mark.parametrize("composition", ["mobile"])
def test_mobile_split_caption_stays_in_active_band(composition: str) -> None:
    try:
        set_composition_env(composition)
        apply_manim_config()
        stage = StageConductor(scene=None)  # type: ignore[arg-type]
        stage.use_right_stage = True
        stage._pin_caption_top = True
        band = stage.caption_band()
        active = right_active()
        archive = left_archive()
        assert band.bottom >= active.bottom - 1e-3
        assert band.top <= active.top + 1e-3
        assert band.top <= archive.bottom + 0.08
    finally:
        reset_composition()


@pytest.mark.parametrize("composition", ["mobile"])
def test_mobile_split_board_instructions_are_captions(composition: str) -> None:
    try:
        plan = plan_integration_by_parts(
            r"Evaluate $\int_0^1 x e^{x}\,dx$.",
            expression="x*exp(x)",
            variable="x",
            lower=0,
            upper=1,
        )
        animation = validate_animation(compile_plan(plan))
        board_scene = next(s for s in animation["scenes"] if s["id"] == "board_1")
        assert not str(board_scene.get("caption") or "").strip()
        assert any(a.get("op") == "set_caption" for a in board_scene["actions"])
        assert not any(o["type"] == "prose" for o in board_scene["objects"])
    finally:
        reset_composition()


@pytest.mark.parametrize("composition", ["mobile"])
def test_mobile_board_reflown_after_taller_set_caption(composition: str) -> None:
    from manim import DOWN, MathTex

    from cinemath.render_engine import instructions as instr
    from cinemath.render_engine.equation_chain import EquationBoard, _LINE_BUFF
    from cinemath.render_engine.layout import layout_scene
    from cinemath.render_engine.layout.overlap import mobjects_overlap
    from cinemath.render_engine.sanitize import to_math_tex

    try:
        set_composition_env(composition)
        apply_manim_config()
        plan = plan_integration_by_parts(
            r"Evaluate $\int_0^1 x e^{x}\,dx$.",
            expression="x*exp(x)",
            variable="x",
            lower=0,
            upper=1,
        )
        animation = validate_animation(compile_plan(plan))
        board_scene = next(s for s in animation["scenes"] if s["id"] == "board_1")
        objs = [o for o in board_scene["objects"][:8] if o["type"] == "math"][:6]

        stage = StageConductor(scene=None)  # type: ignore[arg-type]
        stage.use_right_stage = True
        stage._pin_caption_top = True
        mobjects = {o["id"]: MathTex(to_math_tex(o["tex"])) for o in objs}
        meta = {o["id"]: o for o in objs}
        board_scene = {**board_scene, "caption": "Short step."}
        layout_scene(stage, mobjects, meta, board_scene, caption_color="white")

        board = EquationBoard(
            scene=None,  # type: ignore[arg-type]
            mobjects=mobjects,
            on_screen=set(),
            content_region=stage.board_region,
            accent_color=lambda: "yellow",
        )
        ids = [o["id"] for o in objs]
        for i, eid in enumerate(ids):
            mob = mobjects[eid]
            if not board.stack:
                board._anchor_line(mob)
            else:
                mob.next_to(mobjects[ids[i - 1]], DOWN, buff=_LINE_BUFF)
            board.stack.append(eid)
            board.on_screen.add(eid)

        tall = instr.build_instruction(
            "Substitute into the integration-by-parts formula.",
            color="white",
            max_width_cm=instr.instruction_parbox_cm(),
        )
        instr.place_instruction(tall, region=stage.caption_band(), pin_top=True)
        stage.caption_mob = tall
        from cinemath.render_engine.layout import reflow_after_caption_change

        reflow_after_caption_change(stage, board)

        for eid in ids:
            assert not mobjects_overlap(tall, mobjects[eid])
            assert float(mobjects[eid].get_top()[1]) <= stage.board_region().top + 1e-3

        # Deriving a new line must not scroll the stack into the caption.
        last_id = ids[-1]
        new_id = "board_1_eq_new"
        mobjects[new_id] = MathTex(to_math_tex(r"du = 1\,dx"))
        board.on_screen.add(last_id)
        board._prepare_room_below(mobjects[last_id], mobjects[new_id], buff=_LINE_BUFF)
        assert not mobjects_overlap(tall, mobjects[new_id])
        for eid in ids:
            assert not mobjects_overlap(tall, mobjects[eid])
    finally:
        reset_composition()


# --- board_only ------------------------------------------------------------


@pytest.mark.parametrize("composition", ["board", "web"])
def test_quadratic_board_pins_instructions_above_math(composition: str) -> None:
    """Step instructions are captions. The equation tree is math only."""
    try:
        plan = plan_quadratic("Solve for $x$: $x^2 - 5x + 6 = 0$.", a=1, b=-5, c=6)
        animation = validate_animation(compile_plan(plan))
        board_scene = next(s for s in animation["scenes"] if s["id"] == "board_1")
        assert not str(board_scene.get("caption") or "").strip()
        assert not any(o["type"] == "prose" for o in board_scene["objects"])
        assert not any(a.get("op") == "note" for a in board_scene["actions"])
        assert any(a.get("op") == "set_caption" for a in board_scene["actions"])
    finally:
        reset_composition()


@pytest.mark.parametrize("composition", ["web"])
def test_quadratic_plot_axes_fit_content_band(composition: str) -> None:
    """Plot chrome scales down when equal-aspect axes exceed the frame."""
    try:
        plan = plan_quadratic("Solve for $x$: $x^2 - 5x + 6 = 0$.", a=1, b=-5, c=6)
        animation = validate_animation(compile_plan(plan))
        plot_scene = next(s for s in animation["scenes"] if str(s["id"]).startswith("plot_2d_"))
        stage, mobjects, meta = build_scene_mobjects(plot_scene, composition)
        constraints = constraints_for_composition()
        chrome = _chrome_group(mobjects, meta)
        assert float(chrome.get_left()[0]) >= constraints.region.left - 1e-3
        assert float(chrome.get_right()[0]) <= constraints.region.right + 1e-3
        assert float(chrome.get_top()[1]) <= constraints.ceiling + 1e-3
        assert float(chrome.get_bottom()[1]) >= constraints.floor - 1e-3
    finally:
        reset_composition()


def test_quadratic_split_board_uniform_tree_font() -> None:
    """Board math stays one fixed size in the half-column."""
    try:
        plan = plan_quadratic("Solve for $x$: $x^2 - 5x + 6 = 0$.", a=1, b=-5, c=6)
        animation = validate_animation(compile_plan(plan))
        board_scene = next(s for s in animation["scenes"] if s["id"] == "board_1")
        _stage, mobjects, meta = build_scene_mobjects(board_scene, "web", use_right_stage=True)
        math_sizes = {int(mobjects[o["id"]].font_size) for o in meta.values() if o["type"] == "math"}
        assert len(math_sizes) == 1
        assert not any(o["type"] == "prose" for o in meta.values())
    finally:
        reset_composition()


@pytest.mark.parametrize("composition", ["board", "web"])
def test_quadratic_board_fit_does_not_scale_math(composition: str) -> None:
    """Board overflow uses scroll/fade, not shrinking equation font size."""
    from manim import DOWN

    from cinemath.render_engine.equation_chain import EquationBoard, _LINE_BUFF

    try:
        plan = plan_quadratic("Solve for $x$: $x^2 - 5x + 6 = 0$.", a=1, b=-5, c=6)
        animation = validate_animation(compile_plan(plan))
        board_scene = next(s for s in animation["scenes"] if s["id"] == "board_1")
        stage, mobjects, meta = build_scene_mobjects(board_scene, composition)
        region = stage.board_region()

        board = EquationBoard(
            scene=None,  # type: ignore[arg-type]
            mobjects=mobjects,
            on_screen=set(),
            content_region=stage.board_region,
            accent_color=lambda: "yellow",
        )
        board.set_band(region)
        math_ids = [oid for oid, o in meta.items() if o["type"] == "math"]
        widths_before = {oid: float(mobjects[oid].width) for oid in math_ids}
        for oid in math_ids:
            mob = mobjects[oid]
            if not board.stack:
                board._anchor_line(mob)
            else:
                mob.next_to(mobjects[board.stack[-1]], DOWN, buff=_LINE_BUFF)
            board.stack.append(oid)
            board.on_screen.add(oid)
        board._fit_after_write()
        for oid, w0 in widths_before.items():
            assert abs(float(mobjects[oid].width) - w0) < 1e-5
    finally:
        reset_composition()


@pytest.mark.parametrize("composition", ["board", "web"])
def test_board_only_layout_is_noop(composition: str) -> None:
    try:
        plan = plan_partial_fractions(
            r"Evaluate $\int \frac{4}{x^2+5x-14}\,dx$.",
            expression="4/(x**2+5*x-14)",
            variable="x",
        )
        animation = validate_animation(compile_plan(plan))
        scene = next(s for s in animation["scenes"] if s["id"].startswith("board_"))
        assert scene["template"] == "board_only"
        assert resolve_template(scene).name == "board_only"
        # layout_scene returns immediately; objects stay at build positions
        _stage, mobjects, meta = build_scene_mobjects(scene, composition)
        assert mobjects
        assert all(oid in mobjects for oid in meta)
    finally:
        reset_composition()


# --- split stage geometry (half-stage regions) -----------------------------


@pytest.mark.parametrize(
    ("composition", "axis", "expect"),
    [
        ("mobile", "y", "archive_above"),
        ("web", "x", "archive_left"),
        ("board", "x", "archive_left"),
    ],
)
def test_split_archive_region_orientation(
    composition: str, axis: str, expect: str
) -> None:
    try:
        set_composition_env(composition)
        apply_manim_config()
        active = right_active()
        archive = left_archive()
        if expect == "archive_above":
            assert stack_halves()
            assert archive.center[1] > active.center[1]
        else:
            assert not stack_halves()
            assert archive.center[0] < active.center[0]
    finally:
        reset_composition()


# --- template / validate contracts (no legacy paths) -----------------------


def test_integral_scene_emits_template_without_baked_at() -> None:
    scene = _plot_integral_1d_scene(_INTEGRAL_VISUAL, index=0)
    assert scene["template"] == "plot_with_labels"
    axes = next(o for o in scene["objects"] if o["type"] == "axes")
    assert "at" not in axes
    assert resolve_template(scene).name == "plot_with_labels"


def test_resolve_template_requires_explicit_field() -> None:
    with pytest.raises(ValueError, match="missing required 'template'"):
        resolve_template({"id": "s", "objects": [], "actions": []})


def test_validate_requires_template() -> None:
    with pytest.raises(AnimValidationError, match="missing required 'template'"):
        validate_animation(
            {
                "problem": "p",
                "answer": "a",
                "steps": [],
                "scenes": [
                    {
                        "id": "s",
                        "objects": [{"id": "m", "type": "math", "tex": "x"}],
                        "actions": [{"op": "wait", "seconds": 0.1}],
                    }
                ],
            }
        )


def test_validate_rejects_plot_with_labels_axes_with_at() -> None:
    with pytest.raises(AnimValidationError, match="omit 'at'"):
        validate_animation(
            {
                "problem": "p",
                "answer": "a",
                "steps": [],
                "scenes": [
                    {
                        "id": "s",
                        "template": "plot_with_labels",
                        "objects": [
                            {
                                "id": "ax",
                                "type": "axes",
                                "x_range": [-1, 1, 1],
                                "y_range": [-1, 1, 1],
                                "at": [0, -0.45],
                            },
                            {"id": "lab", "type": "math", "tex": "x", "next_to": "ax"},
                        ],
                        "actions": [{"op": "wait", "seconds": 0.1}],
                    }
                ],
            }
        )


def test_validate_requires_at_for_full_frame_axes() -> None:
    with pytest.raises(AnimValidationError, match="require 'at'"):
        validate_animation(
            {
                "problem": "p",
                "answer": "a",
                "steps": [],
                "scenes": [
                    {
                        "id": "s",
                        "template": "full_frame",
                        "objects": [
                            {
                                "id": "ax",
                                "type": "axes",
                                "x_range": [-1, 1, 1],
                                "y_range": [-1, 1, 1],
                            }
                        ],
                        "actions": [{"op": "wait", "seconds": 0.1}],
                    }
                ],
            }
        )


def test_constraints_floor_respects_composition_buffs() -> None:
    from cinemath.render_engine.layout.constraints import FLOOR_BUFFS
    from cinemath.render_engine.stage import frame_geom

    for name, buff in FLOOR_BUFFS.items():
        set_composition_env(name)
        try:
            apply_manim_config()
            c = constraints_for_composition()
            assert c.floor >= frame_geom().bottom + buff - 1e-6
            assert c.ceiling == frame_geom().caption_ceiling
        finally:
            reset_composition()
