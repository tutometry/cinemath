"""Watermark placement and env toggle."""

from __future__ import annotations

from manim import config

from cinemath.render_engine.composition import apply_manim_config, set_composition_env
from cinemath.render_engine.watermark import build_watermark, watermark_enabled


def test_watermark_sits_in_bottom_right_safe_area() -> None:
    set_composition_env("board")
    apply_manim_config()
    try:
        mob = build_watermark()
        half_w = float(config.frame_width) / 2.0
        half_h = float(config.frame_height) / 2.0
        pad = 0.02 * min(float(config.frame_width), float(config.frame_height))
        inset_right = half_w - float(mob.get_right()[0])
        inset_bottom = float(mob.get_bottom()[1]) + half_h
        assert abs(inset_right - pad) < 0.08
        assert abs(inset_bottom - pad) < 0.08
        assert abs(inset_right - inset_bottom) < 0.05
    finally:
        set_composition_env("board")
        apply_manim_config()


def test_watermark_env_disable(monkeypatch) -> None:
    monkeypatch.setenv("CINEMATH_WATERMARK", "0")
    assert watermark_enabled() is False
    monkeypatch.setenv("CINEMATH_WATERMARK", "1")
    assert watermark_enabled() is True
