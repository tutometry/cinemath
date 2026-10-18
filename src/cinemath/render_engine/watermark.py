"""Persistent bottom-right branding on rendered videos."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from manim import DR, FadeIn, Tex, VMobject, config

from cinemath.render_engine import COLORS
from cinemath.render_engine.composition import scale_font

if TYPE_CHECKING:
    from manim import ThreeDScene

_ENV = "CINEMATH_WATERMARK"
_OPACITY = 0.7
_CORNER_INSET_FRAC = 0.02
_BASE_FONT_SIZE = 15
_FONT_SCALE = 1.5


def watermark_enabled() -> bool:
    raw = os.environ.get(_ENV, "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _corner_inset() -> float:
    """Equal padding from the physical frame edges (not the inner content safe area)."""
    span = min(float(config.frame_width), float(config.frame_height))
    return _CORNER_INSET_FRAC * span


def _place_bottom_right(mob: VMobject) -> None:
    pad = _corner_inset()
    half_w = float(config.frame_width) / 2.0
    half_h = float(config.frame_height) / 2.0
    anchor = (half_w - pad, -half_h + pad, 0.0)
    mob.move_to(anchor, aligned_edge=DR)


def build_watermark() -> VMobject:
    """Single-line mark in the bottom-right corner (Computer Modern via LaTeX)."""
    font_size = scale_font(int(round(_BASE_FONT_SIZE * _FONT_SCALE)))
    mob = Tex(r"\textrm{\copyright{} 2026 Tutometry}", font_size=font_size)
    mob.set_color(COLORS["gray"])
    mob.set_opacity(_OPACITY)
    _place_bottom_right(mob)
    return mob


def attach_watermark(scene: ThreeDScene, mob: VMobject) -> None:
    mob.set_z_index(100)
    scene.add(mob)
    scene.add_fixed_in_frame_mobjects(mob)


def show_watermark(scene: ThreeDScene) -> VMobject | None:
    if not watermark_enabled():
        return None
    mob = build_watermark()
    attach_watermark(scene, mob)
    scene.play(FadeIn(mob, run_time=0.35))
    return mob
