"""Y-range helpers for 2D plots / definite integrals."""

from __future__ import annotations

import math

from cinemath.render_engine.graph_2d import auto_y_range, equal_aspect_axis_lengths, integral_y_range
from cinemath.templates.tools import _plot_integral_1d_scene


def test_integral_y_range_xe_x_peaks_near_80_percent() -> None:
    # ∫₀¹ x eˣ dx — old path sampled padded x up to 2 and ticked to ~17.
    lo, hi, step = integral_y_range("x*exp(x)", 0.0, 1.0, fill_ratio=0.8)
    peak = 1.0 * math.e
    assert lo <= 0.0
    assert hi <= 5.0
    assert (hi - lo) / step <= 6 + 1e-9
    # Peak should sit near 80% of the positive axis (allow snap-to-nice slack).
    assert 0.65 <= peak / hi <= 0.95


def test_integral_y_range_sine_stays_compact() -> None:
    lo, hi, step = integral_y_range("sin(x)", 0.0, math.pi / 2, fill_ratio=0.8)
    assert lo <= 0.0
    assert hi <= 2.0
    assert (hi - lo) / step <= 6 + 1e-9
    assert 0.65 <= 1.0 / hi <= 0.95


def test_plot_integral_scene_uses_shade_window_not_padded_x() -> None:
    scene = _plot_integral_1d_scene(
        {
            "expr": "x*exp(x)",
            "x_min": -0.5,
            "x_max": 1.5,
            "shade_min": 0.0,
            "shade_max": 1.0,
            "lower": 0.0,
            "upper": 1.0,
        },
        index=0,
    )
    assert scene["template"] == "plot_with_labels"
    axes = next(o for o in scene["objects"] if o["type"] == "axes")
    assert "at" not in axes
    y0, y1, y_step = axes["y_range"]
    assert y1 <= 5.0
    assert (y1 - y0) / y_step <= 6 + 1e-9


def test_equal_aspect_axis_lengths_matches_data_spans() -> None:
    x_len, y_len = equal_aspect_axis_lengths([0.0, 5.0, 1.0], [-2.0, 7.0, 1.0], max_extent=5.0)
    assert abs(x_len / 5.0 - y_len / 9.0) < 1e-6
    assert abs(max(x_len, y_len) - 5.0) < 1e-6


def test_auto_y_range_still_works_for_quadratics() -> None:
    lo, hi, step = auto_y_range("x**2 - 5*x + 6", 0.0, 5.0, include=[0.0])
    assert lo < 0 < hi
    assert step > 0
