"""Build + layout scene mobjects without a Manim video render."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from manim import MathTex, NumberLine, ThreeDAxes, VMobject

from cinemath.render_engine.composition import apply_manim_config, set_composition_env
from cinemath.render_engine import graph_2d, graph_3d
from cinemath.render_engine.layout import layout_scene
from cinemath.render_engine.sanitize import to_math_tex
from cinemath.render_engine.stage import StageConductor
from cinemath.render_engine.texutil import plain_tex
from cinemath.render_engine.validate import validate_animation


def build_scene_mobjects(
    scene_data: dict[str, Any],
    composition: str,
    *,
    use_right_stage: bool = False,
) -> tuple[StageConductor, dict[str, VMobject], dict[str, dict[str, Any]]]:
    """Build objects for one scene, run ``layout_scene``, return stage + mobjects + meta."""
    set_composition_env(composition)
    apply_manim_config()
    stage = StageConductor(scene=None)  # type: ignore[arg-type]
    stage.use_right_stage = use_right_stage
    has_caption = bool(str(scene_data.get("caption") or "").strip())
    stage._pin_caption_top = has_caption
    mobjects: dict[str, VMobject] = {}
    meta = {o["id"]: o for o in scene_data.get("objects") or []}

    for obj in scene_data["objects"]:
        mobjects[obj["id"]] = _build_object(
            obj, mobjects, right_stage=use_right_stage
        )

    layout_scene(stage, mobjects, meta, scene_data)
    return stage, mobjects, meta


def build_scene_mobjects_from_animation(
    animation_path: Path | str,
    scene_id: str,
    composition: str,
    *,
    use_right_stage: bool = False,
) -> tuple[StageConductor, dict[str, VMobject], dict[str, dict[str, Any]], dict[str, Any]]:
    """Load validated animation JSON, build + layout the named scene."""
    raw = json.loads(Path(animation_path).read_text(encoding="utf-8"))
    script = validate_animation(raw)
    scene = next(s for s in script["scenes"] if s["id"] == scene_id)
    stage, mobjects, meta = build_scene_mobjects(
        scene, composition, use_right_stage=use_right_stage
    )
    return stage, mobjects, meta, scene


def reset_composition() -> None:
    set_composition_env("board")
    apply_manim_config()


def _build_object(
    obj: dict[str, Any],
    mobjects: dict[str, VMobject],
    *,
    right_stage: bool = False,
) -> VMobject:
    otype = obj["type"]
    color = obj.get("color", "#FFFFFF")
    if otype == "axes":
        return graph_2d.build_axes(obj, color=color)
    if otype == "plot":
        axes = mobjects[obj["axes"]]
        return graph_2d.build_plot(obj, axes, color=color)
    if otype == "dot":
        axes = mobjects[obj["axes"]]
        if isinstance(axes, ThreeDAxes):
            return graph_3d.build_axes3d_dot(obj, axes, color=color)
        return graph_2d.build_axes_dot(obj, axes, color=color)
    if otype == "math":
        from cinemath.render_engine.board_typography import board_tree_font_size

        fs = board_tree_font_size(
            int(obj.get("font_size", 36)),
            right_stage=right_stage,
        )
        return MathTex(to_math_tex(obj["tex"]), font_size=fs)
    if otype == "text":
        return plain_tex(obj["content"], font_size=int(obj.get("font_size", 32)), color=color)
    if otype == "prose":
        from cinemath.render_engine import instructions as instr
        from cinemath.render_engine.board_typography import (
            board_tree_font_size,
            parbox_cm_for_region,
        )
        from cinemath.render_engine.stage import board_band

        region = board_band(right_stage=right_stage)
        fs = board_tree_font_size(int(obj.get("font_size", 36)), right_stage=right_stage)
        return instr.build_instruction(
            obj["content"],
            color=color,
            font_size=fs,
            max_width_cm=parbox_cm_for_region(region),
            apply_composition_scale=False,
        )
    if otype == "number_line":
        return NumberLine(
            x_range=obj["x_range"],
            length=float(obj["length"]),
            include_numbers=True,
            color=color,
        )
    if otype == "polygon":
        axes = mobjects[obj["axes"]]
        return graph_2d.build_polygon(obj, axes, color=color)
    if otype == "flow_field":
        axes = mobjects[obj["axes"]]
        return graph_2d.build_flow_field(obj, axes, color=color)
    if otype == "line":
        from manim import Line

        axes = mobjects[obj["axes"]]
        start, end = axes.c2p(*obj["start"][:2]), axes.c2p(*obj["end"][:2])
        return Line(start, end, color=color)
    raise AssertionError(f"layout helper does not build type {otype!r}")
