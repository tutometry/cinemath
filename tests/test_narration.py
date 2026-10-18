"""Narration spike unit tests (no Manim / no model weights)."""

from __future__ import annotations

import wave
from pathlib import Path

import pytest

from cinemath.calculus_catalog import (
    plan_definite_integral,
    plan_integration_by_parts,
    plan_partial_derivative,
    plan_partial_fractions,
    plan_trig_substitution,
    plan_triple_integral,
    plan_u_substitution,
)
from cinemath.catalog import (
    plan_double_integral,
    plan_linear,
    plan_linear_system_2d,
    plan_long_add,
    plan_long_multiply,
    plan_percent_off,
    plan_quadratic,
    run_catalog,
)
from cinemath.narration.config import narration_requested
from cinemath.narration.kokoro_assets import DEFAULT_ONNX_NAME, kokoro_onnx_path
from cinemath.narration.mux import mux_narration
from cinemath.narration.plain_text import narration_to_speech
from cinemath.narration.speak_math import speak_latex_math
from cinemath.narration.timeline import SpeechEvent, collect_speech_events
from cinemath.narration.tts import synthesize_line
from cinemath.render_engine.validate import validate_animation
from cinemath.templates import compile_plan


def test_kokoro_defaults_to_int8_onnx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CINEMATH_TTS_MODEL_DIR", "/data/tts")
    assert kokoro_onnx_path().name == DEFAULT_ONNX_NAME
    assert "int8" in kokoro_onnx_path().name


def test_narration_default_off() -> None:
    assert narration_requested(option_flag=False) is False
    assert narration_requested(options_payload={}) is False
    assert narration_requested(options_payload={"enable_narration": True}) is True


def test_plain_text_strips_inline_latex() -> None:
    raw = "Standard form $ax^{2}+bx+c=0$ with $a=1$."
    spoken = narration_to_speech(raw)
    assert "$" not in spoken
    assert "a" in spoken.lower()
    assert "squared" in spoken


def test_quadratic_problem_statement_reads_naturally() -> None:
    raw = "Solve for $x$: $x^2 - 5x + 6 = 0$."
    spoken = narration_to_speech(raw)
    assert spoken == (
        "Solve for x: x squared minus five x plus six equals zero."
    )


def test_beat_offsets_follow_marked_words() -> None:
    from cinemath.narration.align import beat_offsets

    speech = "Subtract five from both sides. [[beat]] That simplifies to two x."
    offsets = beat_offsets(speech, duration=5.0)
    assert len(offsets) == 1
    # The marker sits after the first sentence, not at the end.
    assert 1.0 < offsets[0] < 4.0


def test_cued_speech_pauses_at_each_beat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from cinemath.narration.align import BEAT_PAUSE_SECONDS, synthesize_cued_speech
    from cinemath.narration.tts import synthesize_line, wav_duration

    monkeypatch.setenv("CINEMATH_TTS_MOCK", "1")
    speech = "Subtract five from both sides. [[beat]] That simplifies to two x."
    duration, beats = synthesize_cued_speech(speech, tmp_path / "line.wav")
    first = synthesize_line("Subtract five from both sides.", tmp_path / "a.wav")
    second = synthesize_line("That simplifies to two x.", tmp_path / "b.wav")
    assert len(beats) == 1
    assert abs(beats[0] - wav_duration(first)) < 0.02
    assert duration == pytest.approx(
        wav_duration(first) + BEAT_PAUSE_SECONDS + wav_duration(second),
        abs=0.05,
    )


def test_collect_speech_events_from_quadratic_board() -> None:
    plan = plan_quadratic("Solve", a=1, b=-5, c=6)
    animation = validate_animation(compile_plan(plan))
    events = collect_speech_events(animation)
    assert events
    texts = " ".join(e.text for e in events)
    assert "quadratic" in texts.lower() or "factor" in texts.lower()
    board_starts = [e.start_seconds for e in events if "factor" in e.text.lower()]
    assert board_starts


def test_mock_tts_and_mux(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CINEMATH_TTS_MOCK", "1")
    clip = synthesize_line("Hello quadratic roots.", tmp_path / "a.wav")
    assert clip.exists()

    events = [SpeechEvent("Hello quadratic roots.", 0.5)]
    # Minimal silent video stub — mux only needs ffmpeg + a valid video container.
    video = tmp_path / "silent.mp4"
    import shutil
    import subprocess

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg not available")
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x240:d=3",
            "-pix_fmt",
            "yuv420p",
            str(video),
        ],
        check=True,
        capture_output=True,
    )
    out = mux_narration(video, events, [clip], work_dir=tmp_path / "work")
    assert out.exists()
    assert out.stat().st_size > 0


def test_synthesize_line_empty_is_silent(tmp_path: Path) -> None:
    path = synthesize_line("   ", tmp_path / "empty.wav")
    with wave.open(str(path), "rb") as handle:
        assert handle.getnframes() > 0


def test_speak_latex_integral_and_derivative() -> None:
    integral = speak_latex_math(r"\int x^{2} e^{x}\,dx")
    assert "integral" in integral.lower()
    assert "squared" in integral.lower()
    deriv = speak_latex_math(r"f'(x) = 3 x^{2}")
    assert "prime" in deriv.lower()
    assert "squared" in deriv.lower()


def _assert_plan_narration(plan: dict) -> None:
    speeches = [str(s.get("speech") or "").strip() for s in plan["steps"]]
    assert all(speeches), "every step should have speech"
    assert sum(1 for s in speeches if "[[beat]]" in s) >= 1
    animation = validate_animation(compile_plan(plan))
    events = collect_speech_events(animation)
    assert len(events) >= 2, "problem cue plus at least one board/paper cue"


@pytest.mark.parametrize(
    "plan_factory",
    [
        lambda: plan_quadratic("Solve", a=1, b=-5, c=6),
        lambda: plan_linear("Solve", left="2*x+5", right="17"),
        lambda: plan_linear_system_2d("Solve", a1=1, b1=1, c1=5, a2=1, b2=-1, c2=1),
        lambda: plan_percent_off("Sale", original_price=80, percent_off=25),
        lambda: run_catalog(
            "plan_derivative",
            {"problem_statement": "Differentiate.", "expression": "3*x**2 - x"},
        ),
        lambda: plan_double_integral(
            "Evaluate",
            integrand="6*x*y**2",
            x_min=2,
            x_max=4,
            y_min=1,
            y_max=2,
        ),
        lambda: plan_integration_by_parts(
            r"Find $\int x^2 e^x\,dx$.",
            expression="x**2*exp(x)",
            variable="x",
        ),
        lambda: plan_definite_integral(
            r"Evaluate $\int_0^{\pi/2} \sin(x)\,dx$.",
            expression="sin(x)",
            variable="x",
            lower=0,
            upper="pi/2",
        ),
        lambda: plan_partial_fractions(
            r"Evaluate $\int \frac{4}{x^2+5x-14}\,dx$.",
            expression="4/(x**2+5*x-14)",
            variable="x",
        ),
        lambda: plan_u_substitution(
            r"Integrate $2x e^{x^2}\,dx$.",
            expression="2*x*exp(x**2)",
            variable="x",
        ),
        lambda: plan_trig_substitution(
            r"Evaluate $\int \sqrt{49t^{2} - 5} \, dt$.",
            expression="sqrt(49*t**2-5)",
            variable="t",
        ),
        lambda: plan_partial_derivative(
            "Partial",
            expression="x*y**2 + y",
            variable="y",
        ),
        lambda: plan_triple_integral(
            "Volume",
            integrand="x*y*z",
            x_min=0,
            x_max=1,
            y_min=0,
            y_max=2,
            z_min=0,
            z_max=3,
        ),
        lambda: plan_long_multiply("Multiply", multiplicand="12", multiplier="34"),
        lambda: plan_long_add("Add", addends=["12", "34", "5"]),
    ],
    ids=[
        "quadratic",
        "linear",
        "linear_system_2d",
        "percent_off",
        "derivative",
        "double_integral",
        "integration_by_parts",
        "definite_integral",
        "partial_fractions",
        "u_substitution",
        "trig_substitution",
        "partial_derivative",
        "triple_integral",
        "long_multiply",
        "long_add",
    ],
)
def test_catalog_planners_emit_narration(plan_factory) -> None:
    _assert_plan_narration(plan_factory())
