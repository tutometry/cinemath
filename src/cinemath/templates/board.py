"""Equation-board scenes: DSL for algebra chains and simple forks.

Playback (scroll, morph, fork, advance, merge) lives in ``render_engine.equation_chain``.
The history is an equation tree: ``derive`` commits below, ``fork`` splits,
``advance`` replaces a tip in place, ``merge`` joins tips.
Step ``explanation`` is a caption pinned at the top of the board. The equation
tree underneath is math only, so instructions and derivations do not interleave.

After a ``fork``, ``branch_tips`` tracks the last equation id on each branch so
later steps can continue leaves independently instead of re-deriving from the stem.

Steps may include ``side_math`` for scratch work in a right-hand column (partial
fractions, etc.). Use ``side_begin`` + ``side_hold`` on the first side step,
then ``close_side`` + ``break_spine`` when returning to the main integral chain.
"""

from __future__ import annotations

from typing import Any

from cinemath.narration.align import BEAT
from cinemath.templates import dsl
from cinemath.templates.narration import read_wait, step_narration


def equation_board_scene(
    sid: str,
    steps: list[dict[str, Any]],
    *,
    caption: str | None = None,
    font_size: int = 36,
    pin: bool = True,
) -> dict[str, Any] | None:
    """Build one continuous board scene from teacher steps."""
    if not steps:
        return None

    objects: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    spine_id: str | None = None
    branch_tips: list[str] | None = None
    side_tip: str | None = None
    side_ids: list[str] = []
    eq_i = 0
    narration_cues: list[dict[str, Any]] = []

    def next_id() -> str:
        nonlocal eq_i
        oid = f"{sid}_eq{eq_i}"
        eq_i += 1
        return oid

    def append_chain(prev: str | None, tex: str, *, how: str = "commit") -> str:
        oid = next_id()
        objects.append(dsl.math(oid, tex.strip(), at="center", font_size=font_size))
        if prev is None:
            actions.append(dsl.write(oid))
        elif how == "advance":
            actions.append(dsl.advance(prev, oid))
        else:
            actions.append(dsl.derive(prev, oid))
        actions.append(dsl.wait(0.4))
        return oid

    def append_side(tex: str, prev: str) -> str:
        oid = next_id()
        objects.append(dsl.math(oid, tex.strip(), at="center", font_size=font_size))
        actions.append(dsl.derive(prev, oid))
        actions.append(dsl.wait(0.4))
        side_ids.append(oid)
        return oid

    def begin_side_column(anchor_id: str, hold_tex: str, first_tex: str) -> str:
        hold_id = next_id()
        first_id = next_id()
        objects.append(dsl.math(hold_id, hold_tex.strip(), at="center", font_size=font_size))
        objects.append(dsl.math(first_id, first_tex.strip(), at="center", font_size=font_size))
        actions.append(dsl.fork(anchor_id, hold_id, first_id))
        actions.append(dsl.wait(0.4))
        side_ids.extend([hold_id, first_id])
        return first_id

    def close_side_column() -> None:
        nonlocal side_tip
        if side_ids:
            actions.append(dsl.fade_out(*side_ids))
            actions.append(dsl.wait(0.35))
        side_ids.clear()
        side_tip = None

    def show_instruction(text: str) -> None:
        actions.append(dsl.set_caption(text.strip()))
        actions.append(dsl.wait(read_wait(text)))

    for step in steps:
        narr = step_narration(step)
        speech = str(step.get("speech") or "")
        markers = speech.count(BEAT)
        maths = [m for m in (step.get("math") or []) if str(m).strip()]
        side_lines = [m for m in (step.get("side_math") or []) if str(m).strip()]
        cases = [case for case in (step.get("cases") or []) if case.get("math")]
        use_speech = bool(speech.strip()) and bool(narr)
        speech_start = len(actions) if use_speech else None
        beat_actions: list[int] = []

        def close_speech(
            speech_start: int | None = speech_start,
            markers: int = markers,
            speech: str = speech,
            beat_actions: list[int] = beat_actions,
        ) -> None:
            if speech_start is None:
                return
            if markers and len(beat_actions) != markers:
                return
            narration_cues.append(
                {
                    "scene_id": sid,
                    "start_action": speech_start,
                    "speech": speech,
                    "beat_actions": list(beat_actions),
                }
            )

        if narr:
            show_instruction(narr)

        if side_lines:
            if step.get("side_begin") and side_tip is None:
                anchor_id = spine_id
                if anchor_id is None:
                    raise ValueError("side_begin requires prior spine math")
                hold_tex = str(step.get("side_hold") or "").strip()
                if not hold_tex:
                    raise ValueError("side_begin requires side_hold")
                side_tip = begin_side_column(anchor_id, hold_tex, side_lines[0])
                for tex in side_lines[1:]:
                    assert side_tip is not None
                    side_tip = append_side(tex, side_tip)
            elif side_tip is not None:
                for tex in side_lines:
                    side_tip = append_side(tex, side_tip)
            else:
                raise ValueError("side_math requires side_begin or an active side column")

        if step.get("close_side"):
            close_side_column()

        local_prev = spine_id
        if maths:
            if branch_tips is not None:
                # Parallel branches are active: spine math starts a fresh chain.
                branch_tips = None
                local_prev = None
            if step.get("break_spine"):
                local_prev = None
            for tex in maths:
                if markers:
                    beat_actions.append(len(actions))
                local_prev = append_chain(local_prev, tex)
            spine_id = local_prev

        if cases:
            if branch_tips is not None and len(branch_tips) == len(cases):
                new_tips: list[str] = []
                for tip, case in zip(branch_tips, cases, strict=True):
                    lines = [m for m in case["math"] if str(m).strip()]
                    prev = tip
                    for tex in lines:
                        prev = append_chain(prev, tex)
                    new_tips.append(prev)
                branch_tips = new_tips
                spine_id = None
                close_speech()
                continue

            # Fork from the last equation. The step instruction stays in the caption.
            anchor_id = local_prev if local_prev is not None else spine_id
            if anchor_id is None:
                raise ValueError("equation_board cases require prior math")

            first_ids: list[str] = []
            tails: list[tuple[str, list[str]]] = []
            for case in cases:
                lines = [m for m in case["math"] if str(m).strip()]
                first_id = next_id()
                objects.append(
                    dsl.math(first_id, lines[0].strip(), at="center", font_size=font_size)
                )
                first_ids.append(first_id)
                tails.append((first_id, lines[1:]))

            if markers == 1 and not maths:
                beat_actions.append(len(actions))
            actions.append(dsl.fork(anchor_id, *first_ids))
            actions.append(dsl.wait(0.4))

            new_tips = []
            for branch_id, lines in tails:
                prev = branch_id
                for tex in lines:
                    prev = append_chain(prev, tex)
                new_tips.append(prev)
            branch_tips = new_tips
            spine_id = anchor_id

        close_speech()

    if not objects:
        return None

    actions.append(dsl.wait(0.35))
    scene_caption = str(caption or "").strip()
    scene = dsl.scene(
        sid,
        caption=scene_caption,
        objects=objects,
        actions=actions,
        pin=pin,
        template="board_only",
    )
    if narration_cues:
        scene["narration_cues"] = narration_cues
    return scene
