"""Stage geometry and StageConductor — the one place that owns absolute layout."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from manim import LEFT, RIGHT, UP, FadeIn, FadeOut, ThreeDScene, VGroup, VMobject

from cinemath.render_engine.composition import get_composition

# ---------------------------------------------------------------------------
# Board-default frame geometry (landscape 16:9). Live values come from
# ``frame_geom()`` so mobile/web compositions can rescale.
# ---------------------------------------------------------------------------

FRAME_LEFT = -6.95
FRAME_RIGHT = 6.95
FRAME_BOTTOM = -3.55
FRAME_TOP = 3.85

HALF_CENTER_X = 3.35
HALF_SPLIT_X = 0.25
HALF_MAX_W = 5.7
HALF_MAX_H = 6.2
FULL_MAX_W = 12.8
FULL_MAX_H = 6.2

CAPTION_CEILING = 2.7
CAPTION_GAP = 0.78
CAPTION_TOP_BUFF = 0.12
CAPTION_TOP_BUFF = 0.2
LEFT_PANEL_OPACITY = 0.55

# Equation-board scroll bands (content region, before caption clamp).
BOARD_FULL_BOTTOM = -2.35
BOARD_FULL_TOP = 1.35
BOARD_RIGHT_BOTTOM = -2.2
BOARD_RIGHT_TOP = 1.15

SLOT_COORDS: dict[str, tuple[float, float]] = {
    "title": (0.0, 2.15),
    "center": (0.0, -0.15),
    "upper": (0.0, 1.15),
    "lower": (0.0, -2.15),
    "left": (-3.2, -0.1),
    "right": (3.2, -0.1),
    "ul": (-3.4, 1.6),
    "ur": (3.4, 1.6),
    "ll": (-3.4, -2.3),
    "lr": (3.4, -2.3),
}

# Fractions of half-frame used by the board defaults (for live remapping).
_REF_HALF_W = 7.111111111111111
_REF_HALF_H = 4.0

PlacePolicy = Literal["center", "slot", "keep"]


@dataclass(frozen=True)
class Region:
    """Axis-aligned stage rectangle in Manim scene units."""

    center: tuple[float, float]
    max_w: float
    max_h: float
    left: float
    right: float
    bottom: float
    top: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.top - self.bottom


@dataclass(frozen=True)
class FrameGeom:
    left: float
    right: float
    bottom: float
    top: float
    half_center_x: float
    half_split_x: float
    half_max_w: float
    half_max_h: float
    full_max_w: float
    full_max_h: float
    caption_ceiling: float
    board_full_bottom: float
    board_full_top: float
    board_right_bottom: float
    board_right_top: float
    slots: dict[str, tuple[float, float]]
    fit_max_scale: float


def _manim_half_extents() -> tuple[float, float]:
    try:
        from manim import config

        return float(config.frame_width) / 2.0, float(config.frame_height) / 2.0
    except Exception:
        return _REF_HALF_W, _REF_HALF_H


def frame_geom() -> FrameGeom:
    """Composition-aware stage geometry derived from the active Manim frame."""
    half_w, half_h = _manim_half_extents()
    sx = half_w / _REF_HALF_W
    sy = half_h / _REF_HALF_H
    fill = get_composition().stage_fill
    fit_max = get_composition().fit_max_scale

    def x(v: float) -> float:
        return v * sx

    def y(v: float) -> float:
        return v * sy

    slots = {name: (x(px), y(py)) for name, (px, py) in SLOT_COORDS.items()}
    return FrameGeom(
        left=x(FRAME_LEFT),
        right=x(FRAME_RIGHT),
        bottom=y(FRAME_BOTTOM),
        top=y(FRAME_TOP),
        half_center_x=x(HALF_CENTER_X),
        half_split_x=x(HALF_SPLIT_X),
        half_max_w=HALF_MAX_W * sx * fill,
        half_max_h=HALF_MAX_H * sy * fill,
        full_max_w=FULL_MAX_W * sx * fill,
        full_max_h=FULL_MAX_H * sy * fill,
        caption_ceiling=y(CAPTION_CEILING),
        board_full_bottom=y(BOARD_FULL_BOTTOM),
        board_full_top=y(BOARD_FULL_TOP),
        board_right_bottom=y(BOARD_RIGHT_BOTTOM),
        board_right_top=y(BOARD_RIGHT_TOP),
        slots=slots,
        fit_max_scale=fit_max,
    )


def stack_halves() -> bool:
    """Mobile portrait: pin archive above, active content below (not left/right)."""
    return get_composition().name == "mobile"


def full_frame() -> Region:
    g = frame_geom()
    return Region(
        center=(0.0, 0.0),
        max_w=g.full_max_w,
        max_h=g.full_max_h,
        left=g.left,
        right=g.right,
        bottom=g.bottom,
        top=g.top,
    )


def _stacked_split_y(g: FrameGeom) -> float:
    """Y where archive (above) meets active (below). Favor active for plots."""
    return g.bottom + 0.55 * (g.top - g.bottom)


def right_active() -> Region:
    """Active half-stage: right column (landscape) or bottom half (mobile)."""
    g = frame_geom()
    if stack_halves():
        gap = 0.22
        split = _stacked_split_y(g)
        top = split - gap / 2
        bottom = g.bottom
        height = max(top - bottom, 0.5)
        return Region(
            center=(0.0, (bottom + top) / 2),
            max_w=g.full_max_w,
            max_h=height * 0.92,
            left=g.left,
            right=g.right,
            bottom=bottom,
            top=top,
        )
    return Region(
        center=(g.half_center_x, 0.0),
        max_w=g.half_max_w,
        max_h=g.half_max_h,
        left=g.half_split_x,
        right=g.right,
        bottom=g.bottom,
        top=g.top,
    )


def left_archive() -> Region:
    """Archived half-stage: left column (landscape) or top half (mobile)."""
    g = frame_geom()
    if stack_halves():
        gap = 0.22
        split = _stacked_split_y(g)
        bottom = split + gap / 2
        top = g.top
        height = max(top - bottom, 0.5)
        return Region(
            center=(0.0, (bottom + top) / 2),
            max_w=g.full_max_w,
            max_h=height * 0.88,
            left=g.left,
            right=g.right,
            bottom=bottom,
            top=top,
        )
    return Region(
        center=(-g.half_center_x, 0.0),
        max_w=g.half_max_w,
        max_h=g.half_max_h,
        left=g.left,
        right=-g.half_split_x,
        bottom=g.bottom,
        top=g.top,
    )


def board_band(*, right_stage: bool) -> Region:
    """Vertical band used by the equation board for scroll clamps."""
    g = frame_geom()
    if right_stage and stack_halves():
        active = right_active()
        caption_reserve = min(1.35, active.max_h * 0.2) + CAPTION_GAP
        band_top = active.top - caption_reserve
        band_bottom = active.bottom + 0.10 * active.height
        if band_top <= band_bottom + 0.35:
            band_top = active.bottom + 0.82 * active.height
            band_bottom = active.bottom + 0.10 * active.height
        return Region(
            center=(0.0, (band_bottom + band_top) / 2),
            max_w=active.max_w,
            max_h=max(band_top - band_bottom, 0.5),
            left=active.left,
            right=active.right,
            bottom=band_bottom,
            top=band_top,
        )
    if right_stage:
        # Use the full pinned right column (not the legacy smaller BOARD_RIGHT_* slice).
        from cinemath.render_engine.layout.constraints import floor_buff_for_composition

        active = right_active()
        floor = max(float(active.bottom), g.bottom + floor_buff_for_composition())
        top = float(active.top) - 0.12
        h_inset = 0.06
        left = float(active.left) + h_inset
        right = float(active.right) - h_inset
        return Region(
            center=((left + right) / 2, (floor + top) / 2),
            max_w=right - left,
            max_h=max(top - floor, 0.5),
            left=left,
            right=right,
            bottom=floor,
            top=top,
        )
    return Region(
        center=(0.0, (g.board_full_bottom + g.board_full_top) / 2),
        max_w=g.full_max_w,
        max_h=g.board_full_top - g.board_full_bottom,
        left=g.left,
        right=g.right,
        bottom=g.board_full_bottom,
        top=g.board_full_top,
    )


class StageConductor:
    """Owns absolute placement, half-stage pin/swipe, and caption lifecycle."""

    def __init__(self, scene: ThreeDScene) -> None:
        self.scene = scene
        self.caption_mob: VMobject | None = None
        self.left_panel: VMobject | None = None
        self.use_right_stage = False
        self.mode = "2d"
        self._pin_caption_top = False
        self._layout_caption_text: str | None = None
        # Layout-owned content band for the equation board (no caption peek here).
        self._board_band: Region | None = None

    # --- regions ---------------------------------------------------------

    def content(self) -> Region:
        if self.use_right_stage and self.mode != "3d":
            return right_active()
        return full_frame()

    def archive_left(self) -> Region:
        return left_archive()

    def caption_band(self) -> Region:
        """Top instruction strip — stays inside the active content, not the archive."""
        region = self.content()
        g = frame_geom()
        if self.use_right_stage and self.mode != "3d":
            top = region.top - CAPTION_TOP_BUFF
            cap_h = min(1.35, region.max_h * 0.2) if stack_halves() else min(1.2, region.max_h * 0.16)
            bottom = max(region.bottom, top - cap_h)
        else:
            top = g.top
            bottom = g.caption_ceiling
        return Region(
            center=(region.center[0], (bottom + top) / 2),
            max_w=region.max_w,
            max_h=max(0.28, top - bottom),
            left=region.left,
            right=region.right,
            bottom=bottom,
            top=top,
        )

    def board_region(self) -> Region:
        """Content band for equation-board scroll.

        Layout assigns ``_board_band`` after caption hitboxes change. Until then,
        return the base board band (no caption peer peek).
        """
        if self._board_band is not None:
            return self._board_band
        return board_band(right_stage=self.use_right_stage and self.mode != "3d")

    def text_body_region(self) -> Region:
        """Band below the caption ceiling for wrapped statements and prose."""
        base = full_frame()
        g = frame_geom()
        side = min(0.28, base.max_w * 0.04)
        floor = base.bottom
        top = g.caption_ceiling - CAPTION_GAP
        if top <= floor + 0.5:
            top = base.top - 0.5
        return Region(
            center=(base.center[0], (floor + top) / 2),
            max_w=max(1.0, base.max_w - 2 * side),
            max_h=max(0.5, top - floor),
            left=base.left + side,
            right=base.right - side,
            bottom=floor,
            top=top,
        )

    # --- scene lifecycle -------------------------------------------------

    def begin_scene(self, *, pin_caption_top: bool = False) -> None:
        self.caption_mob = None
        self._layout_caption_text = None
        self._board_band = None
        self.use_right_stage = self.left_panel is not None
        self._pin_caption_top = pin_caption_top

    def release_left_for_3d(self) -> None:
        if self.left_panel is None:
            return
        shift = UP * 0.4 if stack_halves() else LEFT * 0.4
        self.scene.play(FadeOut(self.left_panel, shift=shift), run_time=0.4)
        self.left_panel = None
        self.use_right_stage = False

    # --- placement -------------------------------------------------------

    def place(
        self,
        mob: VMobject,
        *,
        at: str | list[float] | tuple[float, float] | None = "center",
        region: Region | None = None,
        policy: PlacePolicy = "slot",
    ) -> None:
        if policy == "keep":
            return
        target = region or self.content()
        if policy == "center" or at is None:
            mob.move_to(float(target.center[0]) * RIGHT + float(target.center[1]) * UP)
            return
        if isinstance(at, str):
            g = frame_geom()
            if self.use_right_stage and self.mode != "3d" and at in {"center", "title", "upper", "lower"}:
                active = right_active()
                if stack_halves():
                    # Soft hints in stacked half-stage: stay inside the bottom band.
                    frac = {"title": 0.32, "upper": 0.18, "center": 0.0, "lower": -0.28}[at]
                    y = active.center[1] + frac * active.max_h
                    mob.move_to(active.center[0] * RIGHT + y * UP)
                else:
                    # Soft hints in half-stage: keep X on the active column.
                    y = g.slots.get(at, (0.0, 0.0))[1]
                    mob.move_to(g.half_center_x * RIGHT + y * UP)
            else:
                x, y = g.slots.get(at, g.slots["center"])
                mob.move_to(x * RIGHT + y * UP)
            return
        # Absolute coords in animation JSON are board-space; remap to live frame.
        half_w, half_h = _manim_half_extents()
        sx = half_w / _REF_HALF_W
        sy = half_h / _REF_HALF_H
        if self.use_right_stage and self.mode != "3d" and stack_halves():
            # Board-space absolute coords are landscape-centered; park in bottom half.
            active = right_active()
            mob.move_to(
                float(at[0]) * sx * RIGHT
                + (active.center[1] + float(at[1]) * sy * 0.45) * UP
            )
            return
        mob.move_to(float(at[0]) * sx * RIGHT + float(at[1]) * sy * UP)

    def clamp_bottom(self, mob: VMobject, *, buff: float = 0.2) -> None:
        """Shift *mob* up so its bottom stays above the stage floor (+ *buff*)."""
        from cinemath.render_engine.layout.pass_layout import _clamp_members_bottom

        _clamp_members_bottom([mob], buff=float(buff))

    def fit(
        self,
        group: VMobject,
        region: Region | None = None,
        *,
        max_scale: float | None = None,
    ) -> None:
        region = region or self.content()
        if max_scale is None:
            max_scale = frame_geom().fit_max_scale
        w = max(float(group.width), 1e-3)
        h = max(float(group.height), 1e-3)
        w_lim = min(region.max_w, max(0.5, region.right - region.left))
        h_lim = min(region.max_h, max(0.5, region.top - region.bottom))
        scale = min(w_lim / w, h_lim / h, max_scale)
        if scale < 0.999 or scale > 1.001:
            group.scale(scale)
        group.move_to(float(region.center[0]) * RIGHT + float(region.center[1]) * UP)

    def fit_active_if_split(self, group: VMobject) -> None:
        if self.use_right_stage and self.mode != "3d" and group.submobjects:
            self.fit(group, self.content())

    # --- captions --------------------------------------------------------

    def show_caption(self, text: str, *, color: Any) -> None:
        caption = str(text).strip()
        if (
            self.caption_mob is not None
            and self._layout_caption_text is not None
            and self._layout_caption_text == caption
        ):
            self.scene.play(FadeIn(self.caption_mob), run_time=0.35)
            return

        from cinemath.render_engine import instructions as instr

        half = self.use_right_stage and self.mode != "3d"
        region = self.caption_band() if self._pin_caption_top else self.content()
        self.caption_mob = instr.build_instruction(
            text,
            color=color,
            max_width_cm=instr.instruction_parbox_cm(right_stage=half),
        )
        instr.place_instruction(
            self.caption_mob,
            region=region,
            pin_top=True,
        )
        self._layout_caption_text = None
        self.scene.play(FadeIn(self.caption_mob), run_time=0.35)

    def set_caption(self, text: str, *, color: Any) -> None:
        from cinemath.render_engine import instructions as instr

        region = self.caption_band() if self._pin_caption_top else self.content()
        self.caption_mob = instr.play_set_instruction(
            self.scene,
            self.caption_mob,
            text,
            color=color,
            region=region,
            pin_top=True,
        )
        self._layout_caption_text = None

    def fade_caption(self) -> list[Any]:
        if self.caption_mob is None:
            return []
        anim = FadeOut(self.caption_mob, shift=UP * 0.15)
        self.caption_mob = None
        return [anim]

    # --- half-stage pin / clear ------------------------------------------

    def pin_active_to_left(self, pieces: Sequence[VMobject]) -> None:
        anims = self.fade_caption()
        if not pieces:
            if anims:
                self.scene.play(*anims, run_time=0.35)
            return

        group = VGroup(*pieces)
        region = self.archive_left()
        w = max(float(group.width), 1e-3)
        h = max(float(group.height), 1e-3)
        scale = min(region.max_w / w, region.max_h / h, 1.0)

        out_shift = UP * 0.6 if stack_halves() else LEFT * 0.6
        if self.left_panel is not None:
            anims.append(FadeOut(self.left_panel, shift=out_shift))
        anims.append(
            group.animate.scale(scale).move_to(
                float(region.center[0]) * RIGHT + float(region.center[1]) * UP
            )
        )
        self.scene.play(*anims, run_time=0.75)
        self._apply_panel_dim(group, LEFT_PANEL_OPACITY)
        self.left_panel = group
        self.use_right_stage = True
        self.scene.wait(0.12)

    def clear_active(self, pieces: Sequence[VMobject]) -> None:
        fade = list(pieces)
        if self.caption_mob is not None:
            fade.append(self.caption_mob)
        if fade:
            self.scene.play(*[FadeOut(m) for m in fade], run_time=0.45)
        self.caption_mob = None

    def clear_left_panel(self) -> list[Any]:
        if self.left_panel is None:
            return []
        anim = FadeOut(self.left_panel)
        self.left_panel = None
        return [anim]

    def _apply_panel_dim(self, mob: VMobject, opacity: float) -> None:
        name = type(mob).__name__
        if name == "ParametricFunction":
            mob.set_fill(opacity=0)
            mob.set_stroke(opacity=opacity)
            return
        if name not in {"MathTex", "Tex", "SingleStringMathTex", "DecimalNumber"} and getattr(
            mob, "submobjects", None
        ):
            for sub in list(mob.submobjects):
                self._apply_panel_dim(sub, opacity)
            if mob.submobjects:
                return
        mob.set_opacity(opacity)
