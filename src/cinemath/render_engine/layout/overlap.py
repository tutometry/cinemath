"""Axis-aligned overlap detection and resolution for layout."""

from __future__ import annotations

from collections.abc import Sequence

from manim import DOWN, UP, VGroup, VMobject

from cinemath.render_engine.stage import Region

Box = tuple[float, float, float, float]  # left, right, bottom, top

_DEFAULT_PAD = 0.14


def mob_box(mob: VMobject, *, pad: float = 0.0) -> Box:
    return (
        float(mob.get_left()[0]) - pad,
        float(mob.get_right()[0]) + pad,
        float(mob.get_bottom()[1]) - pad,
        float(mob.get_top()[1]) + pad,
    )


def boxes_overlap(a: Box, b: Box) -> bool:
    al, ar, ab, at = a
    bl, br, bb, bt = b
    return not (ar < bl or br < al or at < bb or bt < ab)


def mobjects_overlap(a: VMobject, b: VMobject, *, pad: float = _DEFAULT_PAD) -> bool:
    return boxes_overlap(mob_box(a, pad=pad), mob_box(b, pad=pad))


def any_overlap(fixed: VMobject, others: Sequence[VMobject], *, pad: float = _DEFAULT_PAD) -> bool:
    return any(mobjects_overlap(fixed, other, pad=pad) for other in others)


def ceiling_below_caption(caption: VMobject, *, gap: float) -> float:
    return float(caption.get_bottom()[1]) - gap


def region_below_caption(region: Region, caption: VMobject, *, gap: float) -> Region:
    top = min(region.top, ceiling_below_caption(caption, gap=gap))
    if top <= region.bottom + 0.25:
        top = region.bottom + 0.25
    return Region(
        center=(region.center[0], (region.bottom + top) / 2),
        max_w=region.max_w,
        max_h=max(0.25, top - region.bottom),
        left=region.left,
        right=region.right,
        bottom=region.bottom,
        top=top,
    )


def resolve_fixed_vs_content(
    fixed: VMobject,
    content: Sequence[VMobject],
    *,
    region: Region,
    pad: float = _DEFAULT_PAD,
) -> None:
    """Keep *fixed* (caption) put; shift/scale *content* until there is no overlap."""
    if not content:
        return
    movers = [m for m in content if m is not fixed]
    if not movers:
        return

    group = VGroup(*movers)
    for _ in range(8):
        if not any_overlap(fixed, movers, pad=pad):
            return
        overlap_pad = any_overlap(fixed, movers, pad=pad)
        if overlap_pad:
            bottom = float(fixed.get_bottom()[1])
            shift = bottom - pad - float(group.get_top()[1])
            if shift < 0:
                group.shift(DOWN * shift)
        if not any_overlap(fixed, movers, pad=pad):
            return
        if float(group.get_bottom()[1]) < region.bottom:
            group.shift(UP * (region.bottom - float(group.get_bottom()[1])))
        if any_overlap(fixed, movers, pad=pad):
            _scale_to_clear(fixed, group, region=region, pad=pad)
        if not any_overlap(fixed, movers, pad=pad):
            return

    _fit_group_in_region(group, region)


def _scale_to_clear(
    fixed: VMobject,
    group: VGroup,
    *,
    region: Region,
    pad: float,
) -> None:
    for factor in (0.94, 0.88, 0.82, 0.76):
        group.scale(factor)
        if float(group.get_bottom()[1]) < region.bottom:
            group.shift(UP * (region.bottom - float(group.get_bottom()[1])))
        if not any_overlap(fixed, list(group), pad=pad):
            return
    _fit_group_in_region(group, region)


def _fit_group_in_region(group: VGroup, region: Region) -> None:
    if not group.submobjects:
        return
    w = max(float(group.width), 1e-3)
    h = max(float(group.height), 1e-3)
    w_lim = min(region.max_w, max(0.5, region.right - region.left))
    h_lim = min(region.max_h, max(0.25, region.top - region.bottom))
    scale = min(w_lim / w, h_lim / h, 1.0)
    if scale < 0.999:
        group.scale(scale)
    cy = (region.bottom + region.top) / 2
    group.move_to([float(region.center[0]), cy, 0.0])
    if float(group.get_bottom()[1]) < region.bottom:
        group.shift(UP * (region.bottom - float(group.get_bottom()[1])))
    if float(group.get_top()[1]) > region.top:
        group.shift(DOWN * (float(group.get_top()[1]) - region.top))
