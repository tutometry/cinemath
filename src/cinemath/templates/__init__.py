"""Map teacher plans → animation scripts via local visual tools."""

from __future__ import annotations

from typing import Any

from cinemath.narration.align import problem_cue

from . import dsl
from .problem_statement import problem_statement_scene
from .tools import compile_visuals


def compile_plan(plan: dict[str, Any]) -> dict[str, Any]:
    scenes = compile_visuals(plan)
    cues: list[dict[str, Any]] = []
    for scene in scenes:
        cues.extend(scene.pop("narration_cues", []))
    scenes = [problem_statement_scene(plan["problem"]), *scenes]
    opening = problem_cue(str(plan.get("problem") or ""))
    if opening:
        cues.insert(0, opening)
    script = dsl.script(
        plan["problem"],
        plan["answer"],
        [step["title"] for step in plan["steps"]],
        scenes,
    )
    if cues:
        script["narration"] = cues
    return script
