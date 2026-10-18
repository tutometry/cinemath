"""Composition presets — how densely content fills the frame.

Quality (``l``/``w``/``m``/``h``) controls pixels and FPS.
Composition controls scene aspect, content scale, and fit behavior.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

CompositionName = Literal["board", "web", "mobile"]

_COMPOSITION_ENV = "CINEMATH_COMPOSITION"
_BACKGROUND_ENV = "CINEMATH_BACKGROUND_COLOR"

# Tutometry app `--background` (app/globals.css). Keeps MP4 letterboxing invisible in-session.
DEFAULT_BACKGROUND_COLOR = "#0a0a0a"

# Manim's default landscape frame (16:9).
_LANDSCAPE_FRAME_W = 14.222222222222221
_LANDSCAPE_FRAME_H = 8.0


@dataclass(frozen=True)
class CompositionPreset:
    """Layout + pixel overrides for a composition name."""

    name: CompositionName
    # Multiplies default font sizes and plot axis lengths at build time.
    content_scale: float
    # Allow StageConductor.fit() to grow content up to this factor.
    fit_max_scale: float
    # Expand usable stage max_w/max_h relative to board (1.0 = current).
    stage_fill: float
    # Optional Manim frame / pixel overrides (None → keep quality defaults).
    frame_width: float | None = None
    frame_height: float | None = None
    pixel_width: int | None = None
    pixel_height: int | None = None
    # Prefer a specific FPS when this composition sets its own resolution.
    frame_rate: int | None = None


COMPOSITION_PRESETS: dict[str, CompositionPreset] = {
    # Classroom / default lesson layout — current constants.
    "board": CompositionPreset(
        name="board",
        content_scale=1.0,
        fit_max_scale=1.0,
        stage_fill=1.0,
    ),
    # Landing pages, embeds, social — denser landscape fill.
    "web": CompositionPreset(
        name="web",
        content_scale=1.32,
        fit_max_scale=1.4,
        stage_fill=1.12,
    ),
    # Phone-first portrait (9:16). Half-stage pins archive on top, active below.
    "mobile": CompositionPreset(
        name="mobile",
        content_scale=1.28,
        fit_max_scale=1.5,
        stage_fill=1.18,
        frame_width=8.0,
        frame_height=_LANDSCAPE_FRAME_W,  # swap → portrait
        pixel_width=720,
        pixel_height=1280,
        frame_rate=30,
    ),
}


def normalize_composition(name: str | None) -> CompositionName:
    key = (name or "board").strip().lower()
    if key not in COMPOSITION_PRESETS:
        raise ValueError(
            f"Unknown composition '{name}'. Expected one of: "
            f"{', '.join(sorted(COMPOSITION_PRESETS))}."
        )
    return key  # type: ignore[return-value]


def get_composition(name: str | None = None) -> CompositionPreset:
    """Resolve composition from explicit name or ``CINEMATH_COMPOSITION``."""
    if name is None:
        name = os.environ.get(_COMPOSITION_ENV, "board")
    return COMPOSITION_PRESETS[normalize_composition(name)]


def set_composition_env(name: str) -> CompositionPreset:
    """Set process env so the Manim scene process inherits the preset."""
    preset = get_composition(name)
    os.environ[_COMPOSITION_ENV] = preset.name
    return preset


def render_background_color() -> str:
    """Scene fill color for Manim renders (overridable via ``CINEMATH_BACKGROUND_COLOR``)."""
    raw = os.environ.get(_BACKGROUND_ENV, DEFAULT_BACKGROUND_COLOR).strip()
    return raw or DEFAULT_BACKGROUND_COLOR


def apply_manim_config(config: Any | None = None) -> CompositionPreset:
    """Apply frame/pixel overrides to Manim's global config (call at scene import).

    Presets without frame overrides restore the default landscape frame so a prior
    mobile/web process env cannot leave portrait geometry stuck on ``config``.
    """
    preset = get_composition()
    if config is None:
        from manim import config as manim_config

        config = manim_config
    config.frame_width = float(
        preset.frame_width if preset.frame_width is not None else _LANDSCAPE_FRAME_W
    )
    config.frame_height = float(
        preset.frame_height if preset.frame_height is not None else _LANDSCAPE_FRAME_H
    )
    if preset.pixel_width is not None:
        config.pixel_width = int(preset.pixel_width)
    if preset.pixel_height is not None:
        config.pixel_height = int(preset.pixel_height)
    if preset.frame_rate is not None:
        config.frame_rate = int(preset.frame_rate)
    config.background_color = render_background_color()
    return preset


def scale_font(size: float | int, *, composition: CompositionPreset | None = None) -> int:
    preset = composition or get_composition()
    return max(12, int(round(float(size) * preset.content_scale)))


def scale_length(length: float, *, composition: CompositionPreset | None = None) -> float:
    preset = composition or get_composition()
    return float(length) * preset.content_scale


def quality_fps(quality: str) -> int:
    if quality == "l":
        return 15
    if quality == "w":
        return 30
    return 60
