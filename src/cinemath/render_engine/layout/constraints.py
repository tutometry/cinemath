"""Floor/ceiling constraints derived from composition presets."""

from __future__ import annotations

from dataclasses import dataclass

from manim import VMobject

from cinemath.render_engine.composition import get_composition
from cinemath.render_engine.layout.overlap import ceiling_below_caption, region_below_caption
from cinemath.render_engine.stage import Region, frame_geom, full_frame

# Composition-specific floor buffs (scene units). Keep tick labels / axis tips
# inside the frame — never drop chrome through the floor.
FLOOR_BUFFS: dict[str, float] = {
    "board": 0.22,
    "web": 0.42,
    "mobile": 0.34,
}

# Vertical gap between a pinned opening caption and content below it.
CAPTION_CONTENT_GAP = 0.35

# Vertical gap between plot label (∫, y=…) and the y-axis arrow tip.
CHROME_LABEL_BUFF: dict[str, float] = {
    "board": 0.24,
    "web": 0.28,
    "mobile": 0.32,
}


@dataclass(frozen=True)
class LayoutConstraints:
    region: Region
    floor: float  # min y for chrome (tick labels, axis tips)
    ceiling: float  # max y for labels / caption band


def reserve_constraints_below_caption(
    constraints: LayoutConstraints,
    caption: VMobject,
    *,
    gap: float = CAPTION_CONTENT_GAP,
) -> LayoutConstraints:
    """Shrink the content band so chrome/labels sit below the opening caption."""
    ceiling = min(constraints.ceiling, ceiling_below_caption(caption, gap=gap))
    region = region_below_caption(constraints.region, caption, gap=gap)
    return LayoutConstraints(region=region, floor=constraints.floor, ceiling=ceiling)


def chrome_label_buff(name: str | None = None) -> float:
    preset = get_composition(name)
    return CHROME_LABEL_BUFF[preset.name]


def floor_buff_for_composition(name: str | None = None) -> float:
    preset = get_composition(name)
    return FLOOR_BUFFS[preset.name]


def constraints_for_composition(
    *,
    region: Region | None = None,
    name: str | None = None,
) -> LayoutConstraints:
    """Resolve floor/ceiling for the active (or named) composition."""
    g = frame_geom()
    buff = floor_buff_for_composition(name)
    floor = g.bottom + buff
    # Prefer the true Manim clip edge when FRAME_* is looser than the camera.
    try:
        from manim import config

        floor = max(floor, -float(config.frame_height) / 2.0 + buff)
    except Exception:
        pass
    return LayoutConstraints(
        region=region if region is not None else full_frame(),
        floor=floor,
        ceiling=g.caption_ceiling,
    )
