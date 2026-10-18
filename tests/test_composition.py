"""Unit tests for composition presets."""

from __future__ import annotations

import os

import pytest

from cinemath.render_engine.composition import (
    COMPOSITION_PRESETS,
    DEFAULT_BACKGROUND_COLOR,
    get_composition,
    normalize_composition,
    render_background_color,
    scale_font,
    scale_length,
    set_composition_env,
)
from cinemath.render_engine.render import manim_cli_args


def test_normalize_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown composition"):
        normalize_composition("tablet")


def test_web_scales_fonts_and_lengths() -> None:
    set_composition_env("web")
    try:
        assert scale_font(40) == 53
        assert abs(scale_length(6.5) - 6.5 * 1.32) < 1e-9
        assert get_composition().fit_max_scale > 1.0
    finally:
        set_composition_env("board")


def test_mobile_sets_portrait_pixels() -> None:
    mobile = get_composition("mobile")
    assert mobile.pixel_width == 720
    assert mobile.pixel_height == 1280
    assert mobile.frame_width is not None
    assert mobile.frame_height is not None
    assert mobile.frame_height > mobile.frame_width


def test_manim_cli_args_mobile_overrides_quality_resolution() -> None:
    args = manim_cli_args("w", "mobile")
    assert "--resolution" in args
    assert "720,1280" in args
    assert "--frame_rate" in args


def test_manim_cli_args_web_uses_quality_preset() -> None:
    args = manim_cli_args("w", "web")
    assert args == ["-qm", "--frame_rate", "30"]


def test_all_composition_presets_defined() -> None:
    assert set(COMPOSITION_PRESETS) == {"board", "web", "mobile"}


def test_web_plot_axis_lengths_leave_vertical_margin() -> None:
    from cinemath.render_engine.graph_2d import plot_axis_lengths

    set_composition_env("web")
    try:
        x_len, y_len = plot_axis_lengths()
        assert x_len > 10.0
        assert y_len < 5.0
    finally:
        set_composition_env("board")


def test_clamp_bottom_shifts_up_when_below_floor() -> None:
    from manim import Circle, DOWN

    from cinemath.render_engine.stage import StageConductor, frame_geom

    mob = Circle(radius=1.0)
    mob.move_to((frame_geom().bottom - 0.5) * DOWN)
    stage = StageConductor(scene=None)  # type: ignore[arg-type]
    stage.clamp_bottom(mob, buff=0.2)
    assert float(mob.get_bottom()[1]) >= frame_geom().bottom + 0.2 - 1e-6


def test_mobile_half_stage_stacks_top_and_bottom() -> None:
    from cinemath.render_engine.composition import apply_manim_config
    from cinemath.render_engine.stage import left_archive, right_active, stack_halves

    set_composition_env("mobile")
    try:
        apply_manim_config()
        assert stack_halves()
        active = right_active()
        archive = left_archive()
        # Active below archive; both centered horizontally (not left/right cols).
        assert active.center[1] < archive.center[1]
        assert active.top <= archive.bottom + 0.01
        assert abs(active.center[0]) < 0.25
        assert abs(archive.center[0]) < 0.25
    finally:
        set_composition_env("board")
        apply_manim_config()


def test_web_half_stage_stays_side_by_side() -> None:
    from cinemath.render_engine.composition import apply_manim_config
    from cinemath.render_engine.stage import left_archive, right_active, stack_halves

    set_composition_env("web")
    try:
        apply_manim_config()
        assert not stack_halves()
        active = right_active()
        archive = left_archive()
        assert active.center[0] > archive.center[0]
    finally:
        set_composition_env("board")
        apply_manim_config()


def test_render_background_matches_tutometry_default() -> None:
    assert render_background_color() == DEFAULT_BACKGROUND_COLOR
    assert DEFAULT_BACKGROUND_COLOR == "#0a0a0a"


def test_apply_manim_config_sets_background_color(monkeypatch: pytest.MonkeyPatch) -> None:
    from cinemath.render_engine.composition import apply_manim_config

    class _Cfg:
        frame_width = 0.0
        frame_height = 0.0
        background_color = "#000000"

    cfg = _Cfg()
    monkeypatch.setenv("CINEMATH_BACKGROUND_COLOR", "#0a0a0a")
    apply_manim_config(cfg)
    assert cfg.background_color == "#0a0a0a"


def test_env_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CINEMATH_COMPOSITION", "web")
    assert get_composition().name == "web"
    monkeypatch.delenv("CINEMATH_COMPOSITION", raising=False)
    # default after clear — may still be set by prior tests; force board
    os.environ["CINEMATH_COMPOSITION"] = "board"
    assert get_composition().name == "board"
