"""One-pass scene layout orchestrator.

Layout is the cross-hitbox reader: it assigns bands and triggers reflow.
Components (caption, board, plot) animate inside the band they are given.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from manim import DOWN, LEFT, RIGHT, UP, Axes, VGroup, VMobject

from cinemath.render_engine import graph_2d
from cinemath.render_engine.layout.constraints import (
    LayoutConstraints,
    chrome_label_buff,
    floor_buff_for_composition,
    reserve_constraints_below_caption,
)
from cinemath.render_engine.layout.bands import sync_board_band
from cinemath.render_engine.layout.constraints import LayoutConstraints
from cinemath.render_engine.layout.overlap import (
    _fit_group_in_region,
    mobjects_overlap,
    resolve_fixed_vs_content,
)
from cinemath.render_engine.layout.templates import (
    constraints_for_template,
    resolve_template,
)
from cinemath.render_engine.stage import Region, StageConductor

if TYPE_CHECKING:
    from cinemath.render_engine.equation_chain import EquationBoard

_DIRECTION = {"up": UP, "down": DOWN, "left": LEFT, "right": RIGHT}

_CHROME_TYPES = frozenset(
    {
        "axes",
        "axes3d",
        "plot",
        "surface",
        "polygon",
        "line",
        "arrow",
        "number_line",
        "dot",
        "feynman",
        "flow_field",
    }
)
_LABEL_TYPES = frozenset({"math", "text", "prose", "statement"})

# Object types that are positioned in axes-local space and must move with axes.
_AXES_DEPENDENT_TYPES = frozenset(
    {"plot", "polygon", "flow_field", "dot", "line", "arrow", "surface", "plane"}
)

def layout_scene(
    conductor: StageConductor,
    mobjects: Mapping[str, VMobject],
    meta: Mapping[str, dict[str, Any]],
    scene_data: dict[str, Any],
    *,
    caption_color: Any = "#FFFFFF",
) -> None:
    """Position scene mobjects once before caption and actions play.

    Opening captions are built and pinned here so content can be placed
    without overlapping the instruction banner.
    """
    template = resolve_template(scene_data)
    opening_caption = _layout_opening_caption(conductor, scene_data, caption_color)
    if template.name == "board_only":
        sync_board_band(conductor)
        return

    constraints = constraints_for_template(template, conductor)
    if opening_caption is not None and conductor._pin_caption_top:
        constraints = reserve_constraints_below_caption(constraints, opening_caption)

    if template.name == "plot_with_labels":
        _place_axes_in_region(mobjects, meta, constraints.region)
    else:
        _place_axes_from_at(conductor, mobjects, meta)
    _fit_axes_bundles(mobjects, meta, constraints)

    separate = scene_data.get("separate_labels", True)
    _apply_next_to(mobjects, scene_data, skip_labels=separate)

    if separate:
        chrome, labels = _split_chrome_labels(mobjects, meta)
        separate_labels_from_chrome(labels, chrome, constraints=constraints)

    is_3d = scene_data.get("mode") == "3d"
    if conductor.use_right_stage and mobjects and not is_3d:
        conductor.fit_active_if_split(VGroup(*mobjects.values()))
        if separate:
            chrome, labels = _split_chrome_labels(mobjects, meta)
            _reposition_plot_labels(labels, chrome, constraints=constraints)
        else:
            chrome, _labels = _split_chrome_labels(mobjects, meta)
            if chrome:
                _enforce_floor(VGroup(*chrome), constraints.floor)

    if opening_caption is not None and mobjects:
        resolve_fixed_vs_content(
            opening_caption,
            list(mobjects.values()),
            region=constraints.region,
        )


def reflow_after_caption_change(
    conductor: StageConductor,
    board: EquationBoard,
    *,
    animate: bool = False,
) -> None:
    """Settle the board into the band implied by the current caption hitbox."""
    sync_board_band(conductor, board)
    board.settle_into_band(animate=animate)


def apply_caption_change(
    conductor: StageConductor,
    board: EquationBoard | None,
    text: str,
    *,
    color: Any,
    font_size: int | None = None,
    max_width_cm: float | None = None,
    apply_composition_scale: bool = True,
) -> None:
    """Orchestrator: measure next caption → settle peers → then swap text.

    Order matters: board (and any other band-bound content) moves into the
    *upcoming* band before the instruction crossfades, so nothing teleports
    after the text change.
    """
    from manim import AnimationGroup, FadeIn, FadeOut, rate_functions

    from cinemath.render_engine import instructions as instr
    from cinemath.render_engine.layout.bands import compute_board_content_band

    half = conductor.use_right_stage and conductor.mode != "3d"
    region = conductor.caption_band() if conductor._pin_caption_top else conductor.content()
    width_cm = (
        max_width_cm
        if max_width_cm is not None
        else instr.instruction_parbox_cm(right_stage=half)
    )
    preview = instr.build_instruction(
        text,
        color=color,
        font_size=font_size,
        max_width_cm=width_cm,
        apply_composition_scale=apply_composition_scale,
    )
    instr.place_instruction(preview, region=region, pin_top=True)

    new_band = compute_board_content_band(conductor, caption=preview)
    conductor._board_band = new_band
    if board is not None:
        board.set_band(new_band)
        board.settle_into_band(animate=True)

    old = conductor.caption_mob
    if old is None:
        conductor.scene.play(
            FadeIn(preview),
            run_time=0.35,
            rate_func=rate_functions.smooth,
        )
    else:
        conductor.scene.play(
            AnimationGroup(FadeOut(old), FadeIn(preview), lag_ratio=0.3),
            run_time=0.4,
            rate_func=rate_functions.smooth,
        )
    conductor.caption_mob = preview
    conductor._layout_caption_text = None


def _layout_opening_caption(
    conductor: StageConductor,
    scene_data: dict[str, Any],
    color: Any,
) -> VMobject | None:
    text = str(scene_data.get("caption") or "").strip()
    if not text:
        return None
    from cinemath.render_engine import instructions as instr

    half = conductor.use_right_stage and conductor.mode != "3d"
    pin_top = conductor._pin_caption_top
    region = conductor.caption_band() if pin_top else conductor.content()
    mob = instr.build_instruction(
        text,
        color=color,
        max_width_cm=instr.instruction_parbox_cm(right_stage=half),
    )
    instr.place_instruction(mob, region=region, pin_top=pin_top)
    conductor.caption_mob = mob
    conductor._layout_caption_text = text
    return mob


def _fit_axes_bundles(
    mobjects: Mapping[str, VMobject],
    meta: Mapping[str, dict[str, Any]],
    constraints: LayoutConstraints,
) -> None:
    """Scale plot chrome so axes, curves, and ticks stay inside the content band."""
    region = Region(
        center=constraints.region.center,
        max_w=constraints.region.max_w,
        max_h=max(constraints.ceiling - constraints.floor, 0.5),
        left=constraints.region.left,
        right=constraints.region.right,
        bottom=constraints.floor,
        top=constraints.ceiling,
    )
    for oid, obj in meta.items():
        if obj.get("type") != "axes" or oid not in mobjects:
            continue
        members = _axes_members(oid, mobjects, meta)
        if not members:
            continue
        _fit_group_in_region(VGroup(*members), region)


def _place_axes_in_region(
    mobjects: Mapping[str, VMobject],
    meta: Mapping[str, dict[str, Any]],
    region: Region,
) -> None:
    """Center each axes bundle in the template content band."""
    clamp_buff = floor_buff_for_composition()
    for oid, obj in meta.items():
        if obj.get("type") != "axes" or oid not in mobjects:
            continue
        members = _axes_members(oid, mobjects, meta)
        _move_members_to(members, region.center)
        _clamp_members_bottom(members, buff=clamp_buff)


def _place_axes_from_at(
    conductor: StageConductor,
    mobjects: Mapping[str, VMobject],
    meta: Mapping[str, dict[str, Any]],
) -> None:
    """Place axes bundles using required authored ``at`` coords."""
    clamp_buff = floor_buff_for_composition()
    for oid, obj in meta.items():
        if obj.get("type") != "axes" or oid not in mobjects:
            continue
        if "at" not in obj:
            raise ValueError(
                f"axes {oid!r} missing required 'at' "
                f"(use template plot_with_labels to omit absolute placement)"
            )
        members = _axes_members(oid, mobjects, meta)
        axes = mobjects[oid]
        at = obj["at"]
        before = axes.get_center().copy()
        if isinstance(at, str):
            conductor.place(axes, at=at)
        else:
            conductor.place(axes, at=[float(at[0]), float(at[1])])
        delta = axes.get_center() - before
        for mob in members:
            if mob is not axes:
                mob.shift(delta)
        _clamp_members_bottom(members, buff=clamp_buff)


def _move_members_to(members: Sequence[VMobject], center: tuple[float, float]) -> None:
    if not members:
        return
    left = min(float(m.get_left()[0]) for m in members)
    right = max(float(m.get_right()[0]) for m in members)
    bottom = min(float(m.get_bottom()[1]) for m in members)
    top = max(float(m.get_top()[1]) for m in members)
    cx = (left + right) / 2.0
    cy = (bottom + top) / 2.0
    shift = (center[0] - cx) * RIGHT + (center[1] - cy) * UP
    for mob in members:
        mob.shift(shift)


def _axes_members(
    axes_id: str,
    mobjects: Mapping[str, VMobject],
    meta: Mapping[str, dict[str, Any]],
) -> list[VMobject]:
    members: list[VMobject] = [mobjects[axes_id]]
    for oid, obj in meta.items():
        if oid == axes_id or oid not in mobjects:
            continue
        if obj.get("type") in _AXES_DEPENDENT_TYPES and obj.get("axes") == axes_id:
            members.append(mobjects[oid])
    return members


def _clamp_members_bottom(members: Sequence[VMobject], *, buff: float) -> None:
    from cinemath.render_engine.stage import frame_geom

    if not members:
        return
    limit = frame_geom().bottom + float(buff)
    bottom = min(float(m.get_bottom()[1]) for m in members)
    if bottom < limit:
        shift = UP * (limit - bottom)
        for mob in members:
            mob.shift(shift)


def _apply_next_to(
    mobjects: Mapping[str, VMobject],
    scene_data: dict[str, Any],
    *,
    skip_labels: bool = False,
) -> None:
    for obj in scene_data.get("objects") or []:
        if "next_to" not in obj:
            continue
        if skip_labels and obj.get("type") in _LABEL_TYPES:
            continue
        oid = obj["id"]
        anchor_id = obj["next_to"]
        if oid not in mobjects or anchor_id not in mobjects:
            continue
        kwargs: dict[str, Any] = {}
        if "buff" in obj:
            kwargs["buff"] = float(obj["buff"])
        mobjects[oid].next_to(
            mobjects[anchor_id],
            _DIRECTION[obj.get("direction", "down")],
            **kwargs,
        )


def _split_chrome_labels(
    mobjects: Mapping[str, VMobject],
    meta: Mapping[str, dict[str, Any]],
) -> tuple[list[VMobject], list[VMobject]]:
    chrome = [
        mobjects[oid]
        for oid, obj in meta.items()
        if obj.get("type") in _CHROME_TYPES and oid in mobjects
    ]
    labels = [
        mobjects[oid]
        for oid, obj in meta.items()
        if obj.get("type") in _LABEL_TYPES and oid in mobjects
    ]
    return chrome, labels


def separate_labels_from_chrome(
    labels: Sequence[VMobject],
    chrome: Sequence[VMobject],
    *,
    constraints: LayoutConstraints,
    buff: float | None = None,
) -> None:
    """Keep labels above chrome inside the [floor, ceiling] band."""
    if not labels or not chrome:
        return
    label_buff = chrome_label_buff() if buff is None else buff
    floor = constraints.floor
    ceiling = constraints.ceiling
    target_cx = float(constraints.region.center[0])
    chrome_group = VGroup(*chrome)

    axes_mob = _find_axes(chrome)

    def _place_labels() -> None:
        if axes_mob is not None:
            for lab in labels:
                graph_2d.place_label_north_of_y_axis(lab, axes_mob, buff=label_buff)
        else:
            for lab in labels:
                _place_label_above_chrome(lab, chrome_group, buff=label_buff)

    _place_labels()

    for lab in labels:
        if any(mobjects_overlap(lab, c, pad=0.1) for c in chrome):
            _place_labels()

    highest_label = max(float(lab.get_top()[1]) for lab in labels)
    if highest_label > ceiling:
        drop = highest_label - ceiling + 0.15
        room = float(chrome_group.get_bottom()[1]) - floor
        chrome_group.shift(DOWN * min(drop, max(room, 0.0)))
        _place_labels()

    bundle = VGroup(*labels, chrome_group)
    top = max(float(lab.get_top()[1]) for lab in labels)
    bottom = float(chrome_group.get_bottom()[1])
    band_h = max(ceiling - floor, 0.5)
    need_h = top - bottom
    if need_h > band_h + 1e-6:
        anchor = chrome_group.get_center()
        bundle.scale(band_h / need_h, about_point=anchor)
        _shift_bundle_vertical(bundle, (floor + ceiling) / 2.0)
        _place_labels()
    else:
        if bottom < floor:
            bundle.shift(UP * (floor - bottom))
        top = max(float(lab.get_top()[1]) for lab in labels)
        if top > ceiling:
            bundle.shift(DOWN * (top - ceiling))
            bottom = float(chrome_group.get_bottom()[1])
            if bottom < floor:
                bundle.shift(UP * (floor - bottom))

    chrome_group.shift(RIGHT * (target_cx - float(chrome_group.get_center()[0])))
    _place_labels()
    top = max(float(lab.get_top()[1]) for lab in labels)
    if top > ceiling:
        bundle.shift(DOWN * (top - ceiling))
    _enforce_floor(chrome_group, floor)
    _place_labels()


def _find_axes(chrome: Sequence[VMobject]) -> Axes | None:
    axes = [mob for mob in chrome if isinstance(mob, Axes)]
    return axes[0] if len(axes) == 1 else None


def _reposition_plot_labels(
    labels: Sequence[VMobject],
    chrome: Sequence[VMobject],
    *,
    constraints: LayoutConstraints,
) -> None:
    """Re-apply label anchors after a global scale/move (split-stage fit)."""
    if not labels or not chrome:
        return
    label_buff = chrome_label_buff()
    axes_mob = _find_axes(chrome)
    if axes_mob is not None:
        for lab in labels:
            graph_2d.place_label_north_of_y_axis(lab, axes_mob, buff=label_buff)
    else:
        chrome_group = VGroup(*chrome)
        for lab in labels:
            _place_label_above_chrome(lab, chrome_group, buff=label_buff)
    _enforce_floor(VGroup(*chrome), constraints.floor)


def _place_label_above_chrome(lab: VMobject, chrome_group: VGroup, *, buff: float) -> None:
    """Fallback: center plot labels above chrome when no axes anchor exists."""
    lab.next_to(chrome_group, UP, buff=buff)
    _clear_label_chrome_overlap(lab, chrome_group)


def _clear_label_chrome_overlap(lab: VMobject, chrome_group: VGroup, *, pad: float = 0.14) -> None:
    for _ in range(10):
        if not mobjects_overlap(lab, chrome_group, pad=pad):
            return
        lab.shift(UP * 0.16)


def _shift_bundle_vertical(bundle: VGroup, target_y: float) -> None:
    dy = target_y - float(bundle.get_center()[1])
    if abs(dy) > 1e-6:
        bundle.shift(UP * dy)


def _enforce_floor(chrome: VMobject, floor: float) -> None:
    bottom = float(chrome.get_bottom()[1])
    if bottom < floor:
        chrome.shift(UP * (floor - bottom))
