"""Problem-statement intro: format + Write animation helpers."""

from __future__ import annotations

from typing import Any

from manim import VMobject, Write

from cinemath.render_engine.instructions import format_instruction_body, statement_parbox_cm

_FONT_SIZE = 30


def build_statement(
    text: str,
    *,
    color: Any,
    font_size: int = _FONT_SIZE,
) -> VMobject:
    """Wrapped problem statement with inline math; placement owned by StageConductor."""
    from manim import Tex

    body = format_instruction_body(text)
    if not body:
        body = r"\textit{(no problem statement)}"
    width_cm = statement_parbox_cm()
    return Tex(
        rf"\parbox{{{width_cm:.1f}cm}}{{\centering \textbf{{Problem:}} {body}}}",
        font_size=font_size,
        color=color,
    )


def play_write_statement(
    scene,
    mob: VMobject,
    *,
    run_time: float = 1.6,
    place: bool = False,
) -> None:
    """Draw the statement on as if writing it on the board.

    Placement is owned by the builder/layout; ``place`` is ignored.
    """
    del place
    scene.play(Write(mob), run_time=run_time)
