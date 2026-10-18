"""Manim renderer for template-produced animation scripts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from manim import (
    DEGREES,
    LEFT,
    RIGHT,
    UP,
    Arrow,
    Axes,
    Create,
    DashedLine,
    Dot,
    FadeIn,
    FadeOut,
    Indicate,
    Line,
    MathTex,
    NumberLine,
    ReplacementTransform,
    SurroundingRectangle,
    ThreeDAxes,
    ThreeDScene,
    VGroup,
    VMobject,
    Write,
)

from cinemath.render_engine import COLORS
from cinemath.render_engine import feynman as feynman_mod
from cinemath.render_engine import graph_2d, graph_3d
from cinemath.render_engine import instructions as instr
from cinemath.render_engine import problem_statement as stmt
from cinemath.render_engine.equation_chain import EquationBoard
from cinemath.render_engine.sanitize import to_math_tex
from cinemath.render_engine.board_typography import (
    board_tree_font_size,
    parbox_cm_for_region,
)
from cinemath.render_engine.layout_debug import (
    build_overlay,
    clear_overlay,
    layout_debug_enabled,
)
from cinemath.render_engine.stage import StageConductor, frame_geom, full_frame, stack_halves
from cinemath.render_engine.texutil import plain_tex
from cinemath.render_engine.validate import validate_animation
from cinemath.render_engine.watermark import show_watermark

_ANIMATION_JSON_ENV = "CINEMATH_ANIMATION_JSON"


class ScriptedScene(ThreeDScene):
    def construct(self) -> None:
        import os

        animation_json = os.environ.get(_ANIMATION_JSON_ENV)
        if not animation_json:
            raise RuntimeError(f"{_ANIMATION_JSON_ENV} is not set")
        animation_path = Path(animation_json).resolve()
        script = validate_animation(json.loads(animation_path.read_text(encoding="utf-8")))
        ScriptRunner(self, script).run()


class ScriptRunner:
    def __init__(self, scene: ThreeDScene, script: dict[str, Any]) -> None:
        self.scene = scene
        self.script = script
        self.mobjects: dict[str, VMobject] = {}
        self._obj_type: dict[str, str] = {}
        self.on_screen: set[str] = set()
        self.stage = StageConductor(scene)
        self._board_scene = False
        self._separate_labels = True
        self._decorations: list[VMobject] = []
        self._hold_finale = False
        self._layout_debug: list[Any] = []
        self.board = EquationBoard(
            scene,
            mobjects=self.mobjects,
            on_screen=self.on_screen,
            content_region=self.stage.board_region,
            accent_color=lambda: self._color("yellow"),
        )

    @property
    def caption_mob(self) -> VMobject | None:
        return self.stage.caption_mob

    @property
    def left_panel(self) -> VMobject | None:
        return self.stage.left_panel

    def run(self) -> None:
        self._set_flat_camera(animate=False)
        self._watermark = show_watermark(self.scene)
        for scene_data in self.script["scenes"]:
            self._run_scene(scene_data)
        self.scene.wait(0.5)

    def _clear_decorations(self) -> None:
        if not self._decorations:
            return
        self.scene.play(*[FadeOut(m) for m in self._decorations], run_time=0.25)
        self._decorations.clear()

    def _refresh_layout_debug(self) -> None:
        if not layout_debug_enabled():
            return
        clear_overlay(self.scene, self._layout_debug)
        self._layout_debug = build_overlay(
            self.scene,
            stage=self.stage,
            mobjects=self.mobjects,
            obj_types=self._obj_type,
            on_screen=self.on_screen,
            board_scene=self._board_scene,
        )

    def _run_scene(self, scene_data: dict[str, Any]) -> None:
        self.mobjects.clear()
        self._obj_type.clear()
        self.on_screen.clear()
        self._decorations.clear()
        self._hold_finale = False
        self.board.clear()
        self._board_scene = scene_data.get("template") == "board_only"
        self._separate_labels = scene_data.get("separate_labels", True)
        has_caption = bool(str(scene_data.get("caption") or "").strip()) or any(
            action.get("op") == "set_caption" for action in scene_data.get("actions") or []
        )
        self.stage.begin_scene(pin_caption_top=has_caption)
        self._ensure_mode(scene_data.get("mode", "2d"))

        for obj in scene_data["objects"]:
            self._obj_type[obj["id"]] = obj["type"]
            self.mobjects[obj["id"]] = self._build_object(obj)

        is_3d = scene_data.get("mode") == "3d"
        if is_3d and self.stage.left_panel is not None:
            self.stage.release_left_for_3d()

        from cinemath.render_engine.layout import layout_scene, sync_board_band

        meta = {o["id"]: o for o in scene_data.get("objects") or []}
        layout_scene(
            self.stage,
            self.mobjects,
            meta,
            scene_data,
            caption_color=self._color("white"),
        )
        if self._board_scene:
            sync_board_band(self.stage, self.board)

        if scene_data.get("caption"):
            self.stage.show_caption(
                scene_data["caption"],
                color=self._color("white"),
            )
            if is_3d:
                graph_3d.fix_caption_in_frame(self.scene, self.stage.caption_mob)

        self._refresh_layout_debug()

        for action in scene_data["actions"]:
            self._run_action(action)
            self._refresh_layout_debug()

        if is_3d:
            graph_3d.unfix_caption(self.scene, self.stage.caption_mob)

        if self._hold_finale:
            return

        if layout_debug_enabled():
            clear_overlay(self.scene, self._layout_debug)

        if scene_data.get("pin", True):
            self._clear_decorations()
            pieces = [self.mobjects[i] for i in list(self.on_screen) if i in self.mobjects]
            self.stage.pin_active_to_left(pieces)
            self.on_screen.clear()
            self.mobjects.clear()
            self.board.clear()
        else:
            self._clear_decorations()
            pieces = [self.mobjects[i] for i in list(self.on_screen) if i in self.mobjects]
            self.stage.clear_active(pieces)
            self.on_screen.clear()
            self.mobjects.clear()
            self.board.clear()
            if is_3d and self.stage.mode == "3d":
                graph_3d.exit_3d(self.scene)
                self.stage.mode = "2d"

    def _ensure_mode(self, mode: str) -> None:
        if mode == self.stage.mode:
            return
        if mode == "3d":
            graph_3d.enter_3d(self.scene, phi=70, theta=-45, run_time=0.55)
        else:
            graph_3d.exit_3d(self.scene, run_time=0.45)
        self.stage.mode = mode

    def _set_flat_camera(self, *, animate: bool) -> None:
        if animate:
            graph_3d.exit_3d(self.scene, run_time=0.45)
        else:
            self.scene.set_camera_orientation(phi=0, theta=-90 * DEGREES)

    def _run_action(self, action: dict[str, Any]) -> None:
        op = action["op"]
        if op == "wait":
            self.scene.wait(float(action["seconds"]))
            return
        if op == "set_caption":
            from cinemath.render_engine.board_typography import (
                board_tree_font_size,
                parbox_cm_for_region,
            )
            from cinemath.render_engine.layout import apply_caption_change

            half = self.stage.use_right_stage and self.stage.mode != "3d"
            caption_font = None
            caption_width = None
            scale_caption = True
            if self._board_scene:
                caption_font = board_tree_font_size(
                    36,
                    right_stage=half,
                    mode=self.stage.mode,
                )
                region = self.stage.caption_band() if self.stage._pin_caption_top else self.stage.content()
                caption_width = parbox_cm_for_region(region)
                scale_caption = False
            apply_caption_change(
                self.stage,
                self.board if self._board_scene else None,
                action["text"],
                color=self._color("white"),
                font_size=caption_font,
                max_width_cm=caption_width,
                apply_composition_scale=scale_caption,
            )
            return
        if op == "note":
            self.board.note(
                action["from"],
                action["to"],
                buff=float(action.get("buff", 0.42)),
            )
            return
        if op == "derive":
            self.board.derive(action["from"], action["to"], buff=float(action.get("buff", 0.55)))
            return
        if op == "advance":
            self.board.advance(action["from"], action["to"])
            return
        if op == "fork":
            self.board.fork(action["from"], list(action["to"]), buff=float(action.get("buff", 0.75)))
            return
        if op == "merge":
            self.board.merge(list(action["from"]), action["to"], buff=float(action.get("buff", 0.7)))
            return
        if op == "clear":
            fade = [self.mobjects[i] for i in list(self.on_screen) if i in self.mobjects]
            self.stage.clear_active(fade)
            self.on_screen.clear()
            self.board.clear()
            return
        if op == "move_camera":
            graph_3d.enter_3d(
                self.scene,
                phi=float(action["phi"]),
                theta=float(action["theta"]),
                run_time=float(action.get("run_time", 1)),
            )
            self.stage.mode = "3d"
            return
        if op == "transform":
            src, dst = action["from"], action["to"]
            self.scene.play(ReplacementTransform(self.mobjects[src], self.mobjects[dst]))
            self.mobjects[src] = self.mobjects[dst]
            self.on_screen.discard(src)
            self.on_screen.add(dst)
            return
        targets = action["targets"]
        mobs = [self.mobjects[t] for t in targets]
        if op == "create":
            surf_ids = [t for t in targets if self._obj_type.get(t) == "surface"]
            axes_ids = [t for t in targets if self._obj_type.get(t) == "axes3d"]
            if (
                len(axes_ids) == 1
                and len(surf_ids) == 1
                and set(targets) == {axes_ids[0], surf_ids[0]}
            ):
                graph_3d.reveal_surface(
                    self.scene, self.mobjects[axes_ids[0]], self.mobjects[surf_ids[0]]
                )
                self.on_screen.update(targets)
            else:
                plot_ids = [t for t in targets if self._obj_type.get(t) == "plot"]
                other_ids = [t for t in targets if t not in plot_ids]
                anims = []
                if other_ids:
                    anims.extend(Create(self.mobjects[t]) for t in other_ids)
                if plot_ids:
                    anims.extend(FadeIn(self.mobjects[t]) for t in plot_ids)
                self.scene.play(*anims)
                self.on_screen.update(targets)
        elif op == "write":
            stmt_ids = [t for t in targets if self._obj_type.get(t) == "statement"]
            if stmt_ids and set(stmt_ids) == set(targets):
                for tid in stmt_ids:
                    stmt.play_write_statement(self.scene, self.mobjects[tid], place=False)
                self.on_screen.update(targets)
            elif self._board_scene:
                self.board.write(targets)
            else:
                mobs = [self.mobjects[t] for t in targets]
                self.scene.play(*[Write(m) for m in mobs], run_time=0.65)
                self.on_screen.update(targets)
        elif op == "fade_in":
            self.scene.play(*[FadeIn(m) for m in mobs])
            self.on_screen.update(targets)
        elif op == "fade_out":
            self.scene.play(*[FadeOut(m) for m in mobs])
            self.on_screen.difference_update(targets)
            self.board.discard(targets)
        elif op == "indicate":
            self.scene.play(*[Indicate(m) for m in mobs])
        elif op == "box":
            self._spotlight_box(targets)

    def _spotlight_box(self, targets: list[str]) -> None:
        """Fade everything except the answer, center it, and draw a highlight box."""
        target_set = set(targets)
        fade_ids = [i for i in self.on_screen if i not in target_set]
        fade_mobs = [self.mobjects[i] for i in fade_ids if i in self.mobjects]
        self.board.discard(fade_ids)

        focus_mobs = [self.mobjects[t] for t in targets]
        group = VGroup(*focus_mobs)

        anims: list[Any] = []
        anims.extend(self.stage.fade_caption())
        if fade_mobs:
            anims.extend(FadeOut(m) for m in fade_mobs)
        if self.stage.left_panel is not None:
            out_shift = UP * 0.6 if stack_halves() else LEFT * 0.6
            anims.append(FadeOut(self.stage.left_panel, shift=out_shift))
            self.stage.left_panel = None
        self.stage.use_right_stage = False

        region = full_frame()
        g = frame_geom()
        w = max(float(group.width), 1e-3)
        h = max(float(group.height), 1e-3)
        scale = min(region.max_w / w, region.max_h / h, g.fit_max_scale)
        center = float(region.center[0]) * RIGHT + float(region.center[1]) * UP
        if abs(scale - 1.0) > 0.001:
            anims.append(group.animate.scale(scale).move_to(center))
        else:
            anims.append(group.animate.move_to(center))

        self.scene.play(*anims, run_time=0.85)

        rects = [
            SurroundingRectangle(m, color=self._color("yellow"), buff=0.12)
            for m in focus_mobs
        ]
        self.scene.play(*[Create(r) for r in rects], run_time=0.45)
        self._decorations.extend(rects)

        self.on_screen = set(targets)
        self._hold_finale = True

    def _build_object(self, obj: dict[str, Any]) -> VMobject:
        otype = obj["type"]
        color = self._color(obj.get("color", "white"))
        from cinemath.render_engine.composition import scale_font

        raw_font = int(obj.get("font_size", 36))
        right_stage = self.stage.use_right_stage and self.stage.mode != "3d"
        if self._board_scene:
            font_size = board_tree_font_size(
                raw_font, right_stage=right_stage, mode=self.stage.mode
            )
        else:
            font_size = scale_font(raw_font)
        if otype == "text":
            mob: VMobject = plain_tex(obj["content"], font_size=font_size, color=color)
        elif otype == "math":
            mob = MathTex(to_math_tex(obj["tex"]), font_size=font_size, color=color)
        elif otype == "prose":
            if self._board_scene:
                region = self.stage.board_region()
                mob = instr.build_instruction(
                    obj["content"],
                    color=color,
                    font_size=font_size,
                    max_width_cm=parbox_cm_for_region(region),
                    apply_composition_scale=False,
                )
                return mob
            mob = instr.build_instruction(
                obj["content"],
                color=color,
                font_size=raw_font,
                right_stage=right_stage,
            )
            region = (
                self.stage.text_body_region()
                if not self.stage.use_right_stage
                else self.stage.content()
            )
            instr._fit_in_region(mob, region)
            self._place(mob, obj)
            return mob
        elif otype == "axes":
            mob = graph_2d.build_axes(obj, color=color)
        elif otype == "axes3d":
            mob = graph_3d.build_axes3d(obj)
        elif otype == "number_line":
            from cinemath.render_engine.composition import scale_length

            mob = NumberLine(
                x_range=obj["x_range"],
                length=scale_length(float(obj["length"])),
                include_numbers=True,
                font_size=scale_font(24),
                color=color,
            )
        elif otype == "plot":
            axes = self.mobjects[obj["axes"]]
            assert isinstance(axes, Axes)
            mob = graph_2d.build_plot(obj, axes, color=color)
        elif otype == "surface":
            axes = self.mobjects[obj["axes"]]
            assert isinstance(axes, ThreeDAxes)
            mob = graph_3d.build_surface(obj, axes, color=color)
        elif otype == "plane":
            axes = self.mobjects[obj["axes"]]
            assert isinstance(axes, ThreeDAxes)
            mob = graph_3d.build_plane(obj, axes, color=color)
        elif otype == "polygon":
            axes = self.mobjects[obj["axes"]]
            assert isinstance(axes, Axes)
            mob = graph_2d.build_polygon(obj, axes, color=color)
        elif otype == "dot":
            if "axes" in obj:
                axes = self.mobjects[obj["axes"]]
                if isinstance(axes, ThreeDAxes):
                    mob = graph_3d.build_axes3d_dot(obj, axes, color=color)
                else:
                    assert isinstance(axes, Axes)
                    mob = graph_2d.build_axes_dot(obj, axes, color=color)
            elif "number_line" in obj:
                nl = self.mobjects[obj["number_line"]]
                assert isinstance(nl, NumberLine)
                mob = Dot(nl.n2p(obj["value"]), color=color)
            else:
                mob = Dot(color=color)
        elif otype == "line":
            start, end = self._endpoints(obj)
            stroke = float(obj.get("stroke_width", 2))
            if obj.get("dashed"):
                mob = DashedLine(start, end, color=color, stroke_width=stroke)
            else:
                mob = Line(start, end, color=color, stroke_width=stroke)
        elif otype == "arrow":
            start, end = self._endpoints(obj)
            stroke = float(obj.get("stroke_width", 2))
            tip = float(obj.get("tip_length", 0.18))
            mob = Arrow(
                start,
                end,
                color=color,
                buff=0,
                stroke_width=stroke,
                tip_length=tip,
                max_tip_length_to_length_ratio=0.35,
            )
        elif otype == "feynman":
            mob = feynman_mod.build_feynman(
                obj, color=color, accent=self._color("yellow")
            )
        elif otype == "flow_field":
            axes = self.mobjects[obj["axes"]]
            assert isinstance(axes, Axes)
            mob = graph_2d.build_flow_field(obj, axes, color=color)
        elif otype == "statement":
            mob = stmt.build_statement(
                obj["content"],
                color=color,
                font_size=scale_font(int(obj.get("font_size", 30))),
            )
            from cinemath.render_engine.stage import full_frame

            self.stage.fit(mob, full_frame(), max_scale=1.0)
            return mob
        else:
            raise RuntimeError(otype)

        if "next_to" not in obj and not self._layout_owns_placement(obj):
            self._place(mob, obj)
        return mob

    def _layout_owns_placement(self, obj: dict[str, Any]) -> bool:
        """True when ``layout_scene`` (or board playback) owns absolute position."""
        otype = obj["type"]
        if self._board_scene and otype in {"math", "prose"}:
            return True
        if otype == "statement":
            return True
        if otype in {"axes", "axes3d", "plot", "surface", "plane", "polygon", "flow_field"}:
            return True
        if otype in {"dot", "line", "arrow"} and ("axes" in obj or "number_line" in obj):
            return True
        if otype in {"math", "text", "prose"} and self._separate_labels:
            return True
        return False

    def _endpoints(self, obj: dict[str, Any]):
        if "axes" in obj:
            axes = self.mobjects[obj["axes"]]
            start = list(obj["start"])
            end = list(obj["end"])
            if isinstance(axes, ThreeDAxes):
                while len(start) < 3:
                    start.append(0.0)
                while len(end) < 3:
                    end.append(0.0)
                return axes.c2p(*start[:3]), axes.c2p(*end[:3])
            assert isinstance(axes, Axes)
            return axes.c2p(*start[:2]), axes.c2p(*end[:2])
        return (
            float(obj["start"][0]) * RIGHT + float(obj["start"][1]) * UP,
            float(obj["end"][0]) * RIGHT + float(obj["end"][1]) * UP,
        )

    def _place(self, mob: VMobject, obj: dict[str, Any]) -> None:
        if self._layout_owns_placement(obj):
            return
        at = obj.get("at", "center")
        self.stage.place(mob, at=at if isinstance(at, (str, list, tuple)) else "center")

    def _color(self, name: str):
        if isinstance(name, str) and name.startswith("#"):
            return name
        return COLORS.get(str(name).lower(), COLORS["white"])
