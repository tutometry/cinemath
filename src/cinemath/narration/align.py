"""Place board beats on the words marked in a planner speech script.

Speech lives on the plan as plain text with ``[[beat]]`` markers. One marker
fires the next board action in that step (a new line, or a fork). TTS runs
before Manim so the waits in animation.json land on those words.
"""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any

from cinemath.narration.plain_text import narration_to_speech
from cinemath.narration.timeline import action_duration, action_start_map
from cinemath.narration.tts import synthesize_line

BEAT = "[[beat]]"
# Long enough for a new equation line to finish drawing before the next sentence.
BEAT_PAUSE_SECONDS = 1.15
# Breath between one step's last word and the next step.
CUE_GAP_SECONDS = 0.55
_PCM_RATE = 24_000


def problem_cue(problem: str) -> dict[str, Any] | None:
    """Speak the problem while the statement is written."""
    spoken = narration_to_speech(problem)
    if not spoken:
        return None
    return {
        "scene_id": "problem",
        "start_action": 0,
        "speech": f"{BEAT} {spoken}",
        "beat_actions": [0],
    }


def beat_offsets(speech: str, duration: float) -> list[float]:
    """Seconds into the clip where each ``[[beat]]`` is reached."""
    parts = speech.split(BEAT)
    if len(parts) < 2 or duration <= 0:
        return []
    weights = [len(narration_to_speech(part).split()) for part in parts]
    total = sum(weights) or 1
    times: list[float] = []
    acc = 0
    for weight in weights[:-1]:
        acc += weight
        times.append(duration * acc / total)
    return times


def spoken_text(speech: str) -> str:
    return narration_to_speech(speech.replace(BEAT, " ")).strip()


def synthesize_cued_speech(speech: str, dest: Path) -> tuple[float, list[float]]:
    """Speak ``speech``, inserting silence at each ``[[beat]]``.

    The beat time is the start of that silence, which is when the matching
    board action should begin. A beat at the very start of the cue does not
    insert a leading pause.
    """
    parts = speech.split(BEAT)
    pieces: list[bytes] = []
    beat_times: list[float] = []
    clock = 0.0
    spoken_any = False
    rate = _PCM_RATE

    for index, part in enumerate(parts):
        text = narration_to_speech(part).strip()
        if index > 0:
            beat_times.append(clock)
            if spoken_any:
                frames = int(rate * BEAT_PAUSE_SECONDS)
                pieces.append(b"\x00\x00" * frames)
                clock += BEAT_PAUSE_SECONDS
        if not text:
            continue
        part_path = dest.with_name(f"{dest.stem}.part{index}.wav")
        synthesize_line(text, part_path)
        pcm, part_rate = _read_pcm16(part_path)
        part_path.unlink(missing_ok=True)
        rate = part_rate
        pieces.append(pcm)
        clock += (len(pcm) / 2) / part_rate
        spoken_any = True

    dest.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dest), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"".join(pieces) if pieces else b"\x00\x00" * int(rate * 0.2))
    if not pieces:
        clock = 0.2
    return clock, beat_times


def _read_pcm16(path: Path) -> tuple[bytes, int]:
    with wave.open(str(path), "rb") as handle:
        return handle.readframes(handle.getnframes()), handle.getframerate()


def align_animation(animation: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    """Synthesize each cue and rewrite waits so beats match the audio."""
    cues = [cue for cue in (animation.get("narration") or []) if isinstance(cue, dict)]
    if not cues:
        return animation

    work_dir.mkdir(parents=True, exist_ok=True)
    for index, cue in enumerate(cues):
        spoken = spoken_text(str(cue.get("speech") or ""))
        cue["spoken"] = spoken
        wav_name = f"line_{index:03d}.wav"
        dest = work_dir / wav_name
        duration, beat_times = synthesize_cued_speech(str(cue.get("speech") or ""), dest)
        cue["wav"] = wav_name
        cue["duration"] = duration
        cue["beat_times"] = beat_times

    scenes = {str(scene.get("id")): scene for scene in animation.get("scenes") or []}
    for scene in animation.get("scenes") or []:
        sid = str(scene.get("id"))
        mine = [cue for cue in cues if cue.get("scene_id") == sid]
        if mine:
            _align_scene_beats(scene, mine)

    _pad_until_audio_finishes(animation, cues)
    starts = action_start_map(animation)
    for cue in cues:
        cue["start_seconds"] = float(
            starts.get((str(cue.get("scene_id")), int(cue.get("start_action") or 0)), 0.0)
        )
    animation["narration"] = cues
    _ = scenes
    return animation


def _align_scene_beats(scene: dict[str, Any], cues: list[dict[str, Any]]) -> None:
    actions = scene.get("actions") or []
    board = scene.get("template") == "board_only"
    template = str(scene.get("template") or "")
    beat_waits: dict[int, tuple[int, float]] = {}
    for cue in cues:
        offsets = list(cue.get("beat_times") or [])
        beat_actions = [int(i) for i in cue.get("beat_actions") or []]
        for action_index, offset in zip(beat_actions, offsets, strict=False):
            wait_index = action_index - 1
            if wait_index >= 0:
                beat_waits[wait_index] = (int(cue["start_action"]), float(offset))

    clock = 0.0
    speech_at: dict[int, float] = {}
    for index, action in enumerate(actions):
        for cue in cues:
            if int(cue["start_action"]) == index:
                speech_at[index] = clock
        if action.get("op") == "wait" and index in beat_waits:
            start_index, offset = beat_waits[index]
            target = speech_at.get(start_index, clock) + offset
            # Manim rejects wait(0). A tiny hold is used when the beat is already due.
            action["seconds"] = max(0.05, target - clock)
        clock += action_duration(action, board_scene=board, template=template)


def _pad_until_audio_finishes(animation: dict[str, Any], cues: list[dict[str, Any]]) -> None:
    """Hold the board if a line is still speaking when the next cue would start."""
    ordered = sorted(
        cues,
        key=lambda cue: (
            _scene_index(animation, str(cue.get("scene_id"))),
            int(cue.get("start_action") or 0),
        ),
    )
    for _ in range(3):
        starts = action_start_map(animation)
        end = float(starts.get(("__end__", 0), 0.0))
        changed = False
        for index, cue in enumerate(ordered):
            begin = float(
                starts.get((str(cue.get("scene_id")), int(cue.get("start_action") or 0)), 0.0)
            )
            finish = begin + float(cue.get("duration") or 0.0)
            if index + 1 < len(ordered):
                finish += CUE_GAP_SECONDS
                nxt = ordered[index + 1]
                boundary = float(
                    starts.get((str(nxt.get("scene_id")), int(nxt.get("start_action") or 0)), end)
                )
                wait_at = (str(nxt.get("scene_id")), int(nxt.get("start_action") or 0))
            else:
                boundary = end
                wait_at = None
            deficit = finish - boundary
            if deficit > 0.05 and _extend_wait_before(animation, wait_at, deficit):
                changed = True
        if not changed:
            break


def _scene_index(animation: dict[str, Any], scene_id: str) -> int:
    for index, scene in enumerate(animation.get("scenes") or []):
        if str(scene.get("id")) == scene_id:
            return index
    return 0


def _extend_wait_before(
    animation: dict[str, Any],
    boundary: tuple[str, int] | None,
    deficit: float,
) -> bool:
    scenes = list(animation.get("scenes") or [])
    if boundary is None:
        for scene in reversed(scenes):
            if _bump_last_wait(scene, deficit):
                return True
        return False

    scene_id, action_index = boundary
    scene_pos = _scene_index(animation, scene_id)
    scene = scenes[scene_pos]
    actions = scene.get("actions") or []
    for index in range(action_index - 1, -1, -1):
        if actions[index].get("op") == "wait":
            actions[index]["seconds"] = float(actions[index].get("seconds") or 0.0) + deficit
            return True
    for earlier in reversed(scenes[:scene_pos]):
        if _bump_last_wait(earlier, deficit):
            return True
    return False


def _bump_last_wait(scene: dict[str, Any], deficit: float) -> bool:
    for action in reversed(scene.get("actions") or []):
        if action.get("op") == "wait":
            action["seconds"] = float(action.get("seconds") or 0.0) + deficit
            return True
    return False
