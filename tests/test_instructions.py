"""Unit tests for instruction build / pinned placement."""

from __future__ import annotations

from cinemath.render_engine.composition import apply_manim_config, set_composition_env
from cinemath.render_engine.instructions import (
    build_instruction,
    format_instruction_body,
    instruction_parbox_cm,
    place_instruction,
    statement_parbox_cm,
)
from cinemath.render_engine.problem_statement import build_statement
from cinemath.render_engine.stage import StageConductor, frame_geom, full_frame


def test_format_instruction_body_mathifies_algebra() -> None:
    body = format_instruction_body("Find two numbers that multiply to 6 and add to -5.")
    assert "multiply" in body
    assert "$" in body or "6" in body


def test_mobile_parbox_widths_are_narrow() -> None:
    set_composition_env("mobile")
    apply_manim_config()
    try:
        assert instruction_parbox_cm() == 5.6
        assert statement_parbox_cm() == 5.6
    finally:
        set_composition_env("board")
        apply_manim_config()


def test_mobile_problem_statement_and_caption_fit_regions() -> None:
    set_composition_env("mobile")
    apply_manim_config()
    try:
        stage = StageConductor(scene=None)  # type: ignore[arg-type]
        region = full_frame()
        problem = r"Evaluate the definite integral $\int_0^1 x e^x\, dx$"
        stmt = build_statement(problem, color="white", font_size=30)
        stage.fit(stmt, region, max_scale=1.0)

        assert float(stmt.get_left()[0]) >= region.left - 1e-3
        assert float(stmt.get_right()[0]) <= region.right + 1e-3
        assert float(stmt.get_bottom()[1]) >= region.bottom - 1e-3
        assert float(stmt.get_top()[1]) <= region.top + 1e-3

        caption = build_instruction(
            "Use LIATE as a guide: pick $u$ so that $du$ simplifies, "
            "and $dv$ so that $v=\\int dv$ is easy.",
            color="gray",
        )
        band = stage.caption_band()
        place_instruction(caption, region=band, pin_top=True)
        g = frame_geom()
        assert float(caption.get_left()[0]) >= band.left - 1e-3
        assert float(caption.get_right()[0]) <= band.right + 1e-3
        assert float(caption.get_top()[1]) <= g.top + 1e-3
        assert float(caption.get_bottom()[1]) >= band.bottom - 1e-3
    finally:
        set_composition_env("board")
        apply_manim_config()
