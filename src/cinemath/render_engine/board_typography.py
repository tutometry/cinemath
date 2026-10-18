"""Fixed typography for equation-board trees (math + inline prose)."""

from __future__ import annotations

from cinemath.render_engine.composition import COMPOSITION_PRESETS, get_composition, scale_font
from cinemath.render_engine.instructions import _FULL_PARBOX_CM
from cinemath.render_engine.stage import Region, frame_geom, stack_halves

# Authored JSON font_size for catalog boards (before composition scaling).
BOARD_TREE_FONT_RAW = 36
# Half-column board (plot pinned left): smaller fixed size, no web content_scale bump.
BOARD_TREE_SPLIT_FONT_RAW = 30


def board_tree_uses_split_column(*, right_stage: bool, mode: str = "2d") -> bool:
    return bool(right_stage and mode != "3d" and not stack_halves())


def board_tree_font_size(
    raw: int | float,
    *,
    right_stage: bool,
    mode: str = "2d",
) -> int:
    """Final Manim font size for math and prose on the board."""
    base = int(raw)
    if board_tree_uses_split_column(right_stage=right_stage, mode=mode):
        base = min(base, BOARD_TREE_SPLIT_FONT_RAW)
        return scale_font(base, composition=COMPOSITION_PRESETS["board"])
    return scale_font(base)


def parbox_cm_for_region(region: Region) -> float:
    """TeX parbox width matching the live board band (wrap only, no scaling)."""
    g = frame_geom()
    inner = max(float(region.width) - 0.65, 1.0)
    cm_per_unit = _FULL_PARBOX_CM / max(g.full_max_w, 1e-3)
    return max(3.2, inner * cm_per_unit)
