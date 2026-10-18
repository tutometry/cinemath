"""Content-band computation for layout (orchestrator).

Components receive a Region; they do not compute peer-aware gaps themselves.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from manim import VMobject

from cinemath.render_engine.layout.overlap import region_below_caption
from cinemath.render_engine.stage import (
    CAPTION_GAP,
    Region,
    StageConductor,
    board_band,
    stack_halves,
)

if TYPE_CHECKING:
    from cinemath.render_engine.equation_chain import EquationBoard

# Extra clearance inside the board band after layout assigns it.
BOARD_BAND_INNER_MARGIN = 0.22


def caption_board_gap(caption: VMobject, *, stacked: bool) -> float:
    """Vertical gap between caption hitbox and board content band."""
    gap = CAPTION_GAP
    if stacked:
        gap = max(gap, 0.32 + float(caption.height) * 0.42)
    return gap


def compute_board_content_band(
    conductor: StageConductor,
    *,
    caption: VMobject | None = None,
) -> Region:
    """Resolve the equation-board scroll band from stage + caption hitbox.

    Pass ``caption`` to preview a not-yet-committed instruction (orchestrator
    measures before swapping text).
    """
    right = conductor.use_right_stage and conductor.mode != "3d"
    base = board_band(right_stage=right)
    cap = caption
    if cap is None and conductor._pin_caption_top:
        cap = conductor.caption_mob
    if cap is None:
        return base
    stacked = right and stack_halves()
    gap = caption_board_gap(cap, stacked=stacked)
    return region_below_caption(base, cap, gap=gap)


def sync_board_band(
    conductor: StageConductor,
    board: EquationBoard | None = None,
) -> Region:
    """Store the live board band on the conductor (and board, if given)."""
    band = compute_board_content_band(conductor)
    conductor._board_band = band
    if board is not None:
        board.set_band(band)
    return band
