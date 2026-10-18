"""Estimate when narration lines occur in a rendered lesson."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SpeechEvent:
    text: str
    start_seconds: float


def opening_offset() -> float:
    """Seconds before the first scene. Matches the watermark fade when it is on."""
    raw = os.environ.get("CINEMATH_WATERMARK", "1").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return 0.0
    return 0.35


def collect_speech_events(animation: dict[str, Any]) -> list[SpeechEvent]:
    """
    Walk animation.json like the Manim builder and record caption / set_caption times.

    Durations are heuristic (same defaults as render_engine.builder) — good enough
    for spike mux; refine with measured partial-movie timings later.
    """
    events: list[SpeechEvent] = []
    clock = opening_offset()
    for scene_data in animation.get("scenes") or []:
        caption = str(scene_data.get("caption") or "").strip()
        prose_by_id = {
            str(o["id"]): str(o.get("content") or "").strip()
            for o in scene_data.get("objects") or []
            if o.get("type") == "prose" and o.get("content")
        }
        if caption:
            events.append(SpeechEvent(caption, clock))
        if caption:
            clock += 0.35  # show_caption FadeIn

        for action in scene_data.get("actions") or []:
            op = action.get("op")
            if op == "set_caption":
                text = str(action.get("text") or "").strip()
                if text:
                    events.append(SpeechEvent(text, clock))
            elif op in {"note", "write"}:
                target = action.get("to") if op == "note" else (action.get("targets") or [None])[0]
                if isinstance(target, str):
                    text = prose_by_id.get(target, "")
                    if text:
                        events.append(SpeechEvent(text, clock))
            board = scene_data.get("template") == "board_only"
            clock += action_duration(
                action,
                board_scene=board,
                template=str(scene_data.get("template") or ""),
            )

        clock += scene_epilogue(scene_data)

    # Final wait in ScriptedScene.run()
    clock += 0.5
    _ = clock
    return _dedupe_events(events)


def _dedupe_events(events: list[SpeechEvent]) -> list[SpeechEvent]:
    seen: set[tuple[float, str]] = set()
    out: list[SpeechEvent] = []
    for ev in events:
        key = (round(ev.start_seconds, 3), ev.text)
        if key in seen:
            continue
        seen.add(key)
        out.append(ev)
    return out


def action_duration(
    action: dict[str, Any],
    *,
    board_scene: bool,
    template: str = "",
) -> float:
    """Seconds this action takes in Manim. Kept in step with the builder."""
    op = action.get("op")
    if op == "wait":
        return float(action.get("seconds") or 0.0)
    if op == "set_caption":
        # Caption crossfade. The first caption is a hair shorter (0.35).
        return 0.4
    if op == "note":
        return 0.45
    if op == "derive":
        # TransformMatchingTex on the equation board.
        return 1.05 if board_scene else 0.55
    if op == "advance":
        return 0.7
    if op == "fork":
        return 0.9
    if op == "merge":
        return 0.7
    if op == "write":
        if template == "full_frame":
            return 1.6
        return 0.65 if board_scene else 0.65
    if op == "create":
        return 0.85
    if op == "fade_in":
        return 0.5
    if op == "fade_out":
        return 0.45
    if op == "indicate":
        return 0.6
    if op == "clear":
        return 0.45
    if op == "transform":
        return 0.7
    if op == "move_camera":
        return float(action.get("run_time") or 1.0)
    if op == "box":
        return 0.85 + 0.45
    return 0.4


def scene_epilogue(scene: dict[str, Any]) -> float:
    """Time after the last action: archive, clear, or hold the boxed answer."""
    ops = [a.get("op") for a in scene.get("actions") or []]
    if "box" in ops:
        return 0.0
    if scene.get("pin", True):
        return 0.87
    return 0.45


def action_start_map(animation: dict[str, Any]) -> dict[tuple[str, int], float]:
    """Global start time of every action, using the same clock as narration mux."""
    starts: dict[tuple[str, int], float] = {}
    clock = opening_offset()
    for scene in animation.get("scenes") or []:
        sid = str(scene.get("id") or "")
        board = scene.get("template") == "board_only"
        template = str(scene.get("template") or "")
        if str(scene.get("caption") or "").strip():
            clock += 0.35
        for index, action in enumerate(scene.get("actions") or []):
            starts[(sid, index)] = clock
            clock += action_duration(action, board_scene=board, template=template)
        clock += scene_epilogue(scene)
    starts[("__end__", 0)] = clock
    return starts
