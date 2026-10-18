"""Optional layout hitboxes for visual QA (overlap / band / split-stage)."""

from __future__ import annotations

import os
from typing import Any

from manim import (
    BLUE,
    GRAY,
    GREEN,
    ORANGE,
    PURPLE,
    RED,
    RIGHT,
    TEAL,
    UP,
    WHITE,
    YELLOW,
    DashedVMobject,
    Rectangle,
    SurroundingRectangle,
    Text,
    VMobject,
)

from cinemath.render_engine.stage import Region, StageConductor, left_archive, right_active

_ENV = "CINEMATH_LAYOUT_DEBUG"
_ENV_LABELS = "CINEMATH_LAYOUT_DEBUG_LABELS"

_TYPE_COLORS: dict[str, Any] = {
    "math": RED,
    "prose": BLUE,
    "text": BLUE,
    "statement": PURPLE,
    "axes": GREEN,
    "axes3d": GREEN,
    "plot": TEAL,
    "surface": TEAL,
    "polygon": TEAL,
    "dot": YELLOW,
    "line": YELLOW,
    "arrow": YELLOW,
    "number_line": GREEN,
    "flow_field": TEAL,
    "feynman": WHITE,
    "caption": PURPLE,
    "archive": GRAY,
    "band": ORANGE,
    "active": GRAY,
}


def layout_debug_enabled() -> bool:
    return os.environ.get(_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def layout_debug_labels() -> bool:
    return os.environ.get(_ENV_LABELS, "").strip().lower() in {"1", "true", "yes", "on"}


def clear_overlay(scene: Any, overlay: list[VMobject]) -> None:
    for mob in overlay:
        try:
            mob.clear_updaters()
        except Exception:
            pass
        if mob in scene.mobjects:
            scene.remove(mob)
    overlay.clear()


def build_overlay(
    scene: Any,
    *,
    stage: StageConductor,
    mobjects: dict[str, VMobject],
    obj_types: dict[str, str],
    on_screen: set[str],
    board_scene: bool,
) -> list[VMobject]:
    """Rebuild debug shapes; call after layout and after each board action."""
    overlay: list[VMobject] = []

    if stage.use_right_stage and stage.mode != "3d":
        overlay.append(_region_outline(left_archive(), _TYPE_COLORS["archive"], dashed=True))
        overlay.append(_region_outline(right_active(), _TYPE_COLORS["active"], dashed=True))

    if board_scene:
        band = stage.board_region()
        overlay.append(_region_outline(band, _TYPE_COLORS["band"], dashed=False))

    if stage.caption_mob is not None:
        overlay.extend(_track_mob(scene, stage.caption_mob, _TYPE_COLORS["caption"], label="caption"))

    if stage.left_panel is not None:
        overlay.extend(_track_mob(scene, stage.left_panel, _TYPE_COLORS["archive"], label="archive"))

    for oid in sorted(on_screen):
        mob = mobjects.get(oid)
        if mob is None:
            continue
        color = _TYPE_COLORS.get(obj_types.get(oid, ""), WHITE)
        label = oid if layout_debug_labels() else None
        overlay.extend(_track_mob(scene, mob, color, label=label))

    for mob in overlay:
        mob.set_z_index(100)
        scene.add(mob)
    return overlay


def _region_outline(region: Region, color: Any, *, dashed: bool) -> VMobject:
    rect = Rectangle(
        width=max(float(region.width), 0.1),
        height=max(float(region.height), 0.1),
        stroke_color=color,
        stroke_width=2,
    )
    rect.set_fill(color, opacity=0.06)
    rect.move_to(float(region.center[0]) * RIGHT + float(region.center[1]) * UP)
    if dashed:
        return DashedVMobject(rect, num_dashes=24, dashed_ratio=0.45)
    return rect


def _track_mob(
    scene: Any,
    mob: VMobject,
    color: Any,
    *,
    label: str | None,
    buff: float = 0.06,
) -> list[VMobject]:
    hit = SurroundingRectangle(mob, color=color, buff=buff, stroke_width=2)
    hit.set_fill(color, opacity=0.14)

    def _sync(rect: SurroundingRectangle) -> None:
        rect.become(SurroundingRectangle(mob, color=color, buff=buff, stroke_width=2))
        rect.set_fill(color, opacity=0.14)

    hit.add_updater(_sync)
    scene.add(hit)
    out: list[VMobject] = [hit]

    if label:
        tag = Text(label, font_size=14, color=color)
        tag.add_updater(lambda t: t.next_to(hit, UP, buff=0.04))
        scene.add(tag)
        out.append(tag)
    return out
