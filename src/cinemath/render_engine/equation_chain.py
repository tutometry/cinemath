"""Equation-board playback driven by an equation tree.

Layout gives a vertical **band** (``set_band``). This module only moves math
*inside* that band — it never reads caption or plot geometry.

History lives in ``EquationTree`` (see ``equation_tree.py``):

  ``write``   — root
  ``derive``  — commit: line below, parent stays full brightness
  ``fork``    — several columns; fork point stays full
  ``advance`` — replace a tip in place; parent does not return
  ``merge``   — several parents, one child underneath

``stack`` / ``on_screen`` still track paint order and visibility for scroll.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from manim import (
    DOWN,
    RIGHT,
    UP,
    AnimationGroup,
    FadeIn,
    FadeOut,
    MathTex,
    ReplacementTransform,
    ThreeDScene,
    TransformMatchingTex,
    VMobject,
    Write,
    rate_functions,
)

from cinemath.render_engine.equation_tree import EquationTree
from cinemath.render_engine.layout.bands import BOARD_BAND_INNER_MARGIN
from cinemath.render_engine.stage import Region

_LINE_BUFF = 0.62
_FORK_BUFF = 0.75
_FORK_GAP = 1.0
_FORK_MIN_GAP = 0.65
_FORK_SIDE_BUFF = 0.2
_SCROLL_RUN_TIME = 0.48
_FORK_FULL_MAX_W = 7.0
_ANCHOR_TOP_BUFF = 0.28
_BAND_TOP_MARGIN = BOARD_BAND_INNER_MARGIN
_NOTE_BUFF = 0.42
_NOTE_OPACITY = 0.92
_HORIZ_MARGIN = 0.28
# Prior lines stay on the board but read as inactive (see derive/fork).
_DIMMED_LINE_OPACITY = 0.38


class _FitMotion:
    """Exit and slide animations for one fit, plus the resting centers."""

    def __init__(self, *, anims: list[Any], finals: dict[str, Any]) -> None:
        self.anims = anims
        self.finals = finals

    def snap(self, board: EquationBoard) -> None:
        for node_id, final in self.finals.items():
            mob = board.mobjects.get(node_id)
            if mob is not None:
                mob.move_to(final)


class EquationBoard:
    """Continuous algebra board with chain and fork layout.

    Layout assigns the content band via ``set_band``; this class only owns
    relative structure: next_to, fork fan, scroll.
    """

    def __init__(
        self,
        scene: ThreeDScene,
        *,
        mobjects: dict[str, VMobject],
        on_screen: set[str],
        content_region: Callable[[], Region],
        accent_color: Callable[[], Any],
    ) -> None:
        self.scene = scene
        self.mobjects = mobjects
        self.on_screen = on_screen
        self._band_fn = content_region
        self._band: Region | None = None
        self._accent_color = accent_color
        self.stack: list[str] = []
        self.tree = EquationTree()

    def set_band(self, region: Region) -> None:
        """Accept the content band from layout (orchestrator)."""
        self._band = region

    def _content_region(self) -> Region:
        if self._band is not None:
            return self._band
        return self._band_fn()

    def clear(self) -> None:
        self.stack.clear()
        self.tree.clear()
        self._band = None

    def discard(self, ids: set[str] | list[str]) -> None:
        drop = set(ids)
        self.stack = [i for i in self.stack if i not in drop]
        for node_id in drop:
            self.tree.retire(node_id)

    def track_write(self, target_ids: list[str]) -> None:
        for tid in target_ids:
            mob = self.mobjects.get(tid)
            if tid not in self.stack and mob is not None:
                self.stack.append(tid)
        self._fit_after_write()

    def settle_into_band(self, *, animate: bool = False) -> None:
        """Pack the stack into the current band in one motion."""
        if self.scene is not None or self._visible():
            self._fit_after_write(animate=animate)

    def reflow(self, *, animate: bool = False) -> None:
        """Alias for ``settle_into_band`` (layout orchestrator entry)."""
        self.settle_into_band(animate=animate)

    def _clamp_stack_into_band(self, *, animate: bool = False, snap_top: bool = False) -> None:
        """Keep visible lines inside the content band (optional snap to top)."""
        visible = self._visible()
        if not visible:
            return
        _, safe_top = self._bounds()
        ceiling = safe_top - _BAND_TOP_MARGIN
        run_time = 0.35 if animate else 0.0
        extras = [self.mobjects[i] for i in visible]

        if snap_top:
            top_id = max(visible, key=lambda i: float(self.mobjects[i].get_top()[1]))
            top_mob = self.mobjects[top_id]
            target_y = safe_top - _ANCHOR_TOP_BUFF - float(top_mob.height) / 2
            dy = target_y - float(top_mob.get_center()[1])
            if abs(dy) >= 0.01:
                self._shift_group(dy, extra=extras, run_time=run_time)
            return

        highest = max(float(self.mobjects[i].get_top()[1]) for i in visible)
        if highest > ceiling:
            self._shift_group(
                -(highest - ceiling),
                extra=extras,
                run_time=run_time,
            )

    def write(self, target_ids: list[str]) -> None:
        """Reveal math lines; first line anchors only on ``board_only`` scenes."""
        mobs = [self.mobjects[t] for t in target_ids]
        self._clamp_stack_into_band()
        for mob in mobs:
            if not self.stack:
                self._anchor_line(mob)
            self._scroll_if_below(mob, extra=[mob])
        anims = [Write(m) if isinstance(m, MathTex) else FadeIn(m) for m in mobs]
        self.scene.play(*anims, run_time=0.65)
        self.on_screen.update(target_ids)
        for tid in target_ids:
            self.tree.root(tid)
        self.track_write(target_ids)

    def _anchor_line(self, mob: VMobject) -> None:
        """Place the first visible line at the top of the board band."""
        region = self._content_region()
        y = region.top - _ANCHOR_TOP_BUFF - float(mob.height) / 2
        mob.move_to([float(region.center[0]), y, 0.0])

    def _dim_prior_line(self, src_id: str) -> None:
        """Leave the parent equation on screen but visually de-emphasized."""
        if self.tree.is_fork_point(src_id):
            self.mobjects[src_id].set_opacity(1)
            return
        self.mobjects[src_id].set_opacity(_DIMMED_LINE_OPACITY)

    def _morph_from_parent(
        self,
        src: VMobject,
        dst: VMobject,
        *,
        hide_parent: bool,
        also: list[Any] | None = None,
    ) -> None:
        """Ghost-morph ``src`` into ``dst``. Parent opacity is never restored after hide.

        ``also`` plays in the same beat (an exit that makes room for this line).
        """
        extra = list(also or [])
        if not isinstance(src, MathTex) or not isinstance(dst, MathTex):
            dst.set_opacity(1)
            self.scene.play(FadeIn(dst), *extra, run_time=0.5)
            if hide_parent:
                src.set_opacity(0)
            return
        dst.set_opacity(1)
        if hide_parent:
            src.set_opacity(0)
        ghost = src.copy().set_opacity(1.0)
        ghost.move_to(src.get_center())
        self.scene.add(ghost)
        try:
            self.scene.play(
                TransformMatchingTex(
                    ghost,
                    dst,
                    transform_mismatches=True,
                    fade_transform_mismatches=True,
                ),
                *extra,
                run_time=1.05,
                rate_func=rate_functions.smooth,
            )
        except Exception:
            ghost.move_to(dst.get_center())
            dst.set_opacity(1)
            self.scene.play(
                ReplacementTransform(ghost, dst),
                *extra,
                run_time=0.85,
                rate_func=rate_functions.smooth,
            )
        finally:
            if ghost in self.scene.mobjects:
                self.scene.remove(ghost)
            if hide_parent:
                src.set_opacity(0)

    def _remember(self, node_id: str) -> None:
        self.on_screen.add(node_id)
        if node_id not in self.stack:
            self.stack.append(node_id)

    def note(self, src_id: str, dst_id: str, *, buff: float = _NOTE_BUFF) -> None:
        """Teacher instruction below ``src`` (prose node in the tree)."""
        _ = self.mobjects[src_id]
        dst = self.mobjects[dst_id]
        below = self.tree.is_fork_point(src_id)
        self.tree.note(src_id, dst_id, below=below)
        dst.set_opacity(0)
        motion = self._plan_fit(extra=[dst], include={dst_id})
        dst.set_opacity(_NOTE_OPACITY)
        self.scene.play(FadeIn(dst), *motion.anims, run_time=0.45)
        motion.snap(self)
        self._remember(dst_id)
        self._fit_after_write(animate=True)

    def derive(self, src_id: str, dst_id: str, *, buff: float = _LINE_BUFF) -> None:
        """Commit: new equation below ``src``. Parent stays on screen at full opacity."""
        src = self.mobjects[src_id]
        dst = self.mobjects[dst_id]
        self.tree.commit(src_id, dst_id)
        dst.set_opacity(0)
        motion = self._plan_fit(extra=[dst], include={dst_id})
        if not isinstance(src, MathTex):
            dst.set_opacity(1)
            src.set_opacity(_DIMMED_LINE_OPACITY)
            self.scene.play(Write(dst), *motion.anims, run_time=0.65)
            motion.snap(self)
            self._remember(dst_id)
            self._repack_branch_columns(animate=True)
            self._fit_after_write(animate=True)
            return
        self._morph_from_parent(src, dst, hide_parent=False, also=motion.anims)
        motion.snap(self)
        src.set_opacity(1)
        self._remember(dst_id)
        self._repack_branch_columns(animate=True)
        self._fit_after_write(animate=True)

    def advance(self, src_id: str, dst_id: str) -> None:
        """Replace a tip in its slot. ``src`` is retired and does not come back."""
        src = self.mobjects[src_id]
        dst = self.mobjects[dst_id]
        self.tree.advance(src_id, dst_id)
        dst.set_opacity(0)
        dst.move_to(src.get_center())
        self._morph_from_parent(src, dst, hide_parent=True)
        self.on_screen.discard(src_id)
        self._remember(dst_id)
        self._repack_branch_columns(animate=True)
        self._fit_after_write(animate=True)

    def merge(self, parent_ids: list[str], child_id: str, *, buff: float = _FORK_BUFF) -> None:
        """Join ``parent_ids`` into ``child`` centered under their span."""
        if len(parent_ids) < 2:
            return
        parents = [self.mobjects[pid] for pid in parent_ids]
        child = self.mobjects[child_id]
        self.tree.merge(parent_ids, child_id)
        child.set_opacity(0)
        span_x = sum(float(p.get_center()[0]) for p in parents) / len(parents)
        floor_y = min(float(p.get_bottom()[1]) for p in parents)
        child.move_to([span_x, floor_y - buff - float(child.height) / 2, 0.0])
        self._scroll_if_below(child, extra=[child, *parents])
        child.set_opacity(1)
        self.scene.play(Write(child), run_time=0.7)
        for pid in parent_ids:
            self._dim_prior_line(pid)
        self._remember(child_id)
        self._fit_after_write(animate=True)

    def fork(self, src_id: str, dst_ids: list[str], *, buff: float = _FORK_BUFF) -> None:
        src = self.mobjects[src_id]
        dsts = [self.mobjects[dst_id] for dst_id in dst_ids]
        if not dsts:
            return

        self.tree.fork(src_id, dst_ids)
        for dst in dsts:
            dst.set_opacity(0)
        self._place_fork_children(src, dsts, buff=buff)
        pending = {dst_id: self.mobjects[dst_id] for dst_id in dst_ids}
        # Lines that leave, lines that stay, and the new branches share one beat.
        motion = self._plan_fit(extra=dsts, pending=pending)

        # The stem stays the tree parent. The motion starts at the instruction
        # sitting just above the new columns, so the branches do not cross it.
        reveal = self._fork_reveal_source(src_id, dst_ids)
        ghosts: list[VMobject] = []
        anims = list(motion.anims)
        for dst in dsts:
            dst.set_opacity(1)
            ghost = reveal.copy().set_opacity(1.0)
            ghost.move_to(reveal.get_center())
            ghosts.append(ghost)
            self.scene.add(ghost)
            anims.append(ReplacementTransform(ghost, dst))
        if anims:
            self.scene.play(*anims, run_time=0.9, rate_func=rate_functions.smooth)
        motion.snap(self)

        for ghost in ghosts:
            if ghost in self.scene.mobjects:
                self.scene.remove(ghost)
        src.set_opacity(1)

        for dst_id in dst_ids:
            self._remember(dst_id)
        self._repack_branch_columns(animate=True)
        self._fit_after_write(animate=True)

    def _fork_reveal_source(self, src_id: str, dst_ids: list[str]) -> VMobject:
        """Mobject the new branches visually grow out of.

        Prefer the latest on-screen note under the stem that was written before
        the fork. Otherwise the stem equation itself.
        """
        src = self.mobjects[src_id]
        first_dst = min(
            (
                self.tree.nodes[dst_id].seq
                for dst_id in dst_ids
                if dst_id in self.tree.nodes
            ),
            default=10**9,
        )
        banners = [
            node
            for child in self.tree.children.get(src_id, [])
            if (node := self.tree.nodes.get(child)) is not None
            and node.op == "note"
            and node.seq < first_dst
            and child in self.on_screen
            and child in self.mobjects
        ]
        if not banners:
            return src
        banners.sort(key=lambda node: node.seq)
        return self.mobjects[banners[-1].id]

    def _bounds(self) -> tuple[float, float]:
        region = self._content_region()
        return region.bottom, region.top

    def _visible(self) -> list[str]:
        return [i for i in self.stack if i in self.mobjects and i in self.on_screen]

    def _shift_group(
        self,
        dy: float,
        *,
        extra: list[VMobject] | None = None,
        run_time: float = _SCROLL_RUN_TIME,
    ) -> None:
        if abs(dy) < 0.01:
            return
        on_screen_mobs = {self.mobjects[i] for i in self._visible()}
        movers: list[VMobject] = list(on_screen_mobs)
        if extra:
            for mob in extra:
                if mob is None:
                    continue
                if mob in on_screen_mobs:
                    if mob not in movers:
                        movers.append(mob)
                else:
                    # Layout-only targets must not flash on screen before reveal.
                    mob.shift(UP * dy)
        if not movers:
            return
        # Instant path: no one-frame play flash.
        if self.scene is None or run_time < 0.02:
            for mob in movers:
                mob.shift(UP * dy)
            return
        self.scene.play(
            *[m.animate.shift(UP * dy) for m in movers],
            run_time=run_time,
            rate_func=rate_functions.smooth,
        )

    def _prepare_room_below(
        self,
        anchor: VMobject,
        incoming: VMobject,
        *,
        buff: float,
    ) -> None:
        """Scroll the board up, then park ``incoming`` below ``anchor`` (still hidden)."""
        safe_bottom, _ = self._bounds()
        incoming.next_to(anchor, DOWN, buff=buff)
        overflow = safe_bottom - float(incoming.get_bottom()[1])
        if overflow <= 0.01:
            return
        self._up_shift_room(overflow, extra=[anchor, incoming])
        incoming.next_to(anchor, DOWN, buff=buff)

    def _place_fork_children(self, src: VMobject, dsts: list[VMobject], *, buff: float) -> None:
        region = self._content_region()
        max_width = self._fork_span(region)
        base_y = float(src.get_bottom()[1]) - buff
        for dst in dsts:
            dst.move_to([float(src.get_center()[0]), base_y - float(dst.height) / 2, 0.0])
        self._layout_branch_columns(
            [dst for dst in dsts],
            region=region,
            max_width=max_width,
            center_x=float(src.get_center()[0]),
        )

    def _fork_span(self, region: Region) -> float:
        inner = max(float(region.right - region.left) - 2 * _FORK_SIDE_BUFF, 0.5)
        if region.center[0] > 0.5:
            return min(region.max_w, inner)
        return min(region.max_w, _FORK_FULL_MAX_W, inner)

    def _split_column_xs(self, region: Region, count: int) -> list[float]:
        """Even column anchors inside the board band (uses width in split view)."""
        if count <= 1:
            return [float(region.center[0])]
        pad = max(0.18 * float(region.width), 0.35)
        left = float(region.left) + pad
        right = float(region.right) - pad
        span = right - left
        if count == 2:
            return [left + 0.28 * span, right - 0.28 * span]
        step = span / (count - 1)
        return [left + i * step for i in range(count)]

    def _derive_target_x(self, src_id: str) -> float:
        """Keep branch columns; center main-spine lines in the active board band."""
        region = self._content_region()
        cx = float(region.center[0])
        if self.tree.is_fork_point(src_id):
            return float(self.mobjects[src_id].get_center()[0])
        node = self.tree.nodes.get(src_id)
        if node and node.parents and self.tree.is_fork_point(node.parents[0]):
            return float(self.mobjects[src_id].get_center()[0])
        return cx

    def _branch_columns(
        self,
        pending: dict[str, VMobject] | None = None,
    ) -> dict[str, list[VMobject]]:
        columns: dict[str, list[VMobject]] = {}
        pending_ids = set(pending or {})
        for child, members in self.tree.fork_columns(pending_ids).items():
            mobs: list[VMobject] = []
            for tip in members:
                if pending and tip in pending:
                    mobs.append(pending[tip])
                elif tip in self.on_screen and tip in self.mobjects:
                    mobs.append(self.mobjects[tip])
            if mobs:
                columns[child] = mobs
        return columns

    def _layout_branch_columns(
        self,
        roots: list[VMobject],
        *,
        region: Region,
        max_width: float,
        center_x: float,
    ) -> None:
        """Pack parallel branch columns side-by-side with guaranteed gap."""
        if not roots:
            return
        if len(roots) == 1:
            roots[0].set_x(center_x)
            return

        widths = [max(float(mob.width), 0.5) for mob in roots]
        n = len(roots)
        gap = _FORK_GAP
        total = sum(widths) + gap * (n - 1)
        if total > max_width:
            gap = max(_FORK_MIN_GAP, (max_width - sum(widths)) / (n - 1))
            total = sum(widths) + gap * (n - 1)

        left_limit = region.left + _FORK_SIDE_BUFF
        right_limit = region.right - _FORK_SIDE_BUFF
        span = min(max_width, right_limit - left_limit)
        if total > span:
            gap = max(_FORK_MIN_GAP, (span - sum(widths)) / (n - 1))
            total = sum(widths) + gap * (n - 1)

        if n == 2 and float(region.center[0]) > 0.5:
            xs = self._split_column_xs(region, 2)
            y = float(roots[0].get_center()[1])
            roots[0].set_x(xs[0])
            roots[1].move_to([xs[1], y, 0.0])
            return

        if sum(widths) > span and n == 2:
            xs = self._split_column_xs(region, 2)
            y = float(roots[0].get_center()[1])
            roots[0].set_x(xs[0])
            roots[1].move_to([xs[1], y, 0.0])
            return

        cursor = center_x - total / 2
        for width, mob in zip(widths, roots, strict=False):
            mob.set_x(cursor + width / 2)
            cursor += width + gap

    def _repack_branch_columns(
        self,
        *,
        animate: bool = False,
        pending: dict[str, VMobject] | None = None,
    ) -> None:
        """Re-pack fork columns after a leaf is added. Banners stay out of the columns."""
        self._layout_fork_group(animate=animate, pending=pending)

    def _layout_fork_group(
        self,
        *,
        animate: bool = False,
        pending: dict[str, VMobject] | None = None,
        include: set[str] | None = None,
    ) -> None:
        """Place fork banners and columns inside the band without overlap.

        Notes on the fork stem stay full width. Math written before a
        ``below`` banner stays above it; math written after stays below it.
        Columns sit side by side only when every line fits; otherwise each
        branch is stacked full width, in order.
        """
        _ = animate  # positions are applied immediately; morphs own the motion
        columns = self._branch_columns(pending)
        if len(columns) < 2:
            return
        fork_id = next(
            (fid for fid in self.tree.fork_points if fid in self.mobjects),
            None,
        )
        if fork_id is None or fork_id not in self.mobjects:
            return
        visible = set(self.on_screen)
        if include:
            visible.update(include)
        if pending:
            visible.update(pending)

        region = self._content_region()
        cx = float(region.center[0])
        fork = self.mobjects[fork_id]
        children = list(self.tree.children.get(fork_id, []))
        roots = [
            child
            for child in children
            if (node := self.tree.nodes.get(child)) is not None and node.op == "fork"
        ]
        if len(roots) < 2:
            return
        id_columns = self.tree.fork_columns(set(pending) if pending else set())
        ordered_ids = [id_columns[root] for root in roots if root in id_columns]
        if len(ordered_ids) < 2:
            return

        def seq_of(node_id: str) -> int:
            node = self.tree.nodes.get(node_id)
            return node.seq if node is not None else 0

        def shown(node_id: str) -> bool:
            return node_id in visible and node_id in self.mobjects

        banners = [
            child
            for child in children
            if shown(child)
            and (node := self.tree.nodes.get(child)) is not None
            and node.op == "note"
        ]
        first_root = min(seq_of(root) for root in roots)
        above = [bid for bid in banners if seq_of(bid) < first_root]
        below = [bid for bid in banners if seq_of(bid) >= first_root]
        below.sort(key=seq_of)

        cursor = self._place_prefix_above_fork(fork_id)

        def place_centered(mob: VMobject, top: float) -> float:
            y = top - float(mob.height) / 2
            mob.move_to([cx, y, 0.0])
            return float(mob.get_bottom()[1]) - _LINE_BUFF

        for bid in above:
            cursor = place_centered(self.mobjects[bid], cursor)

        cuts = [first_root, *[seq_of(bid) for bid in below], 10**9]

        def place_segments(segments: list[list[VMobject]], top: float) -> float:
            segments = [seg for seg in segments if seg]
            if len(segments) < 2:
                if not segments:
                    return top
            widths = [max(float(mob.width) for mob in seg) for seg in segments]
            span = max(float(region.right - region.left) - 2 * _FORK_SIDE_BUFF, 0.5)
            gap = _FORK_GAP
            total = sum(widths) + gap * (len(segments) - 1)
            if total > span:
                gap = _FORK_MIN_GAP
                total = sum(widths) + gap * (len(segments) - 1)
            if len(segments) >= 2 and total <= span:
                cursor_x = cx - total / 2
                bottoms: list[float] = []
                for width, seg in zip(widths, segments, strict=False):
                    x = cursor_x + width / 2
                    y = top
                    for mob in seg:
                        y -= float(mob.height) / 2
                        mob.move_to([x, y, 0.0])
                        y -= float(mob.height) / 2 + _LINE_BUFF
                    bottoms.append(y)
                    cursor_x += width + gap
                return min(bottoms) if bottoms else top
            y = top
            for seg in segments:
                for mob in seg:
                    y -= float(mob.height) / 2
                    mob.move_to([cx, y, 0.0])
                    y -= float(mob.height) / 2 + _LINE_BUFF
                y -= _FORK_MIN_GAP
            return y

        for index, cut_start in enumerate(cuts[:-1]):
            cut_end = cuts[index + 1]
            segments: list[list[VMobject]] = []
            for members in ordered_ids:
                seg = [
                    self.mobjects[mid]
                    for mid in members
                    if shown(mid) and cut_start <= seq_of(mid) < cut_end
                ]
                segments.append(seg)
            if any(segments):
                cursor = place_segments(segments, cursor)
            if index < len(below):
                cursor = place_centered(self.mobjects[below[index]], cursor)

    def _place_prefix_above_fork(self, fork_id: str) -> float:
        """Stack pre-fork lines, centered, from the top of the band. Returns the cursor under the stem."""
        region = self._content_region()
        cx = float(region.center[0])
        y = float(region.top) - _ANCHOR_TOP_BUFF
        for node_id in self.stack:
            if node_id not in self.on_screen or node_id not in self.mobjects:
                continue
            mob = self.mobjects[node_id]
            y -= float(mob.height) / 2
            mob.move_to([cx, y, 0.0])
            y -= float(mob.height) / 2 + _LINE_BUFF
            if node_id == fork_id:
                break
        return y + _LINE_BUFF - _FORK_BUFF

    def _relayout_fork_column_stacks(self, *, animate: bool = False) -> None:
        self._layout_fork_group(animate=animate)

    def _band_ceiling(self) -> float:
        _, safe_top = self._bounds()
        return safe_top - _BAND_TOP_MARGIN

    def _up_shift_room(
        self,
        amount: float,
        *,
        extra: list[VMobject] | None = None,
    ) -> float:
        """Shift board content up, never past the content-band ceiling."""
        if amount <= 0.01:
            return 0.0
        ceiling = self._band_ceiling()
        movers: list[VMobject] = [self.mobjects[i] for i in self._visible()]
        if extra:
            for mob in extra:
                if mob is not None and mob not in movers:
                    movers.append(mob)
        if not movers:
            return 0.0
        highest = max(float(mob.get_top()[1]) for mob in movers)
        max_up = max(0.0, ceiling - highest)
        dy = min(amount, max_up)
        if dy > 0.01:
            self._shift_group(dy, extra=extra)
        return dy

    def _scroll_if_below(self, mob: VMobject, *, extra: list[VMobject] | None = None) -> None:
        safe_bottom, _ = self._bounds()
        overflow = safe_bottom - float(mob.get_bottom()[1])
        if overflow <= 0.01:
            return
        extras = list(extra or [])
        if mob not in extras:
            extras.append(mob)
        self._up_shift_room(overflow, extra=extras)

    def _fit_after_write(self, *, animate: bool = False) -> None:
        self._drop_until_fits(animate=animate)

    def _relayout(
        self,
        *,
        pending: dict[str, VMobject] | None = None,
        include: set[str] | None = None,
    ) -> None:
        if len(self._branch_columns(pending)) >= 2:
            self._layout_fork_group(pending=pending, include=include)
        else:
            self._stack_centered_from_top(include=include)

    def _drop_until_fits(
        self,
        *,
        extra: list[VMobject] | None = None,
        pending: dict[str, VMobject] | None = None,
        include: set[str] | None = None,
        animate: bool = False,
    ) -> None:
        """Fade lines that no longer fit, and glide the rest in that same play.

        The fork stem, both branches, and banner notes stay. Text size stays fixed.
        Stayers are never teleported ahead of the animation.
        """
        motion = self._plan_fit(extra=extra, pending=pending, include=include)
        if animate and self.scene is not None and motion.anims:
            self.scene.play(
                *motion.anims,
                run_time=0.35,
                rate_func=rate_functions.smooth,
            )
        motion.snap(self)

    def _plan_fit(
        self,
        *,
        extra: list[VMobject] | None = None,
        pending: dict[str, VMobject] | None = None,
        include: set[str] | None = None,
    ) -> _FitMotion:
        """Choose which lines leave so the rest fits.

        Stayers are held where the viewer last saw them and returned as move
        animations, so the next play eases them instead of popping.
        """
        origins = {
            node_id: self.mobjects[node_id].get_center().copy()
            for node_id in self._visible()
            if node_id in self.mobjects
        }
        dropped: list[VMobject] = []
        for _ in range(len(self.stack) + 1):
            self._relayout(pending=pending, include=include)
            if not self._below_band(extra):
                break
            old_id = next(
                (
                    i
                    for i in self.stack
                    if i in self.on_screen and i not in self._fork_group_ids()
                ),
                None,
            )
            if old_id is None:
                break
            mob = self.mobjects.get(old_id)
            self.stack = [i for i in self.stack if i != old_id]
            self.on_screen.discard(old_id)
            self.tree.retire(old_id)
            if mob is not None:
                if old_id in origins:
                    mob.move_to(origins[old_id])
                dropped.append(mob)
        self._relayout(pending=pending, include=include)
        finals = {
            node_id: self.mobjects[node_id].get_center().copy()
            for node_id in self._visible()
            if node_id in self.mobjects
        }
        anims: list[Any] = [FadeOut(mob) for mob in dropped]
        for node_id, final in finals.items():
            origin = origins.get(node_id)
            if origin is None:
                continue
            if abs(float(origin[0] - final[0])) + abs(float(origin[1] - final[1])) < 0.02:
                continue
            self.mobjects[node_id].move_to(origin)
            anims.append(self.mobjects[node_id].animate.move_to(final))
        return _FitMotion(anims=anims, finals=finals)

    def _below_band(self, extra: list[VMobject] | None = None) -> bool:
        safe_bottom, _ = self._bounds()
        mobs = [self.mobjects[i] for i in self._visible()]
        if extra:
            mobs.extend(mob for mob in extra if mob is not None)
        if not mobs:
            return False
        lowest = min(float(mob.get_bottom()[1]) for mob in mobs)
        return lowest < safe_bottom - 0.02

    def _stack_centered_from_top(self, include: set[str] | None = None) -> None:
        """Single column, centered in the band. Used before a fork exists."""
        visible = [i for i in self.stack if i in self.on_screen and i in self.mobjects]
        for extra_id in include or ():
            if extra_id in self.mobjects and extra_id not in visible:
                visible.append(extra_id)
        if not visible:
            return
        region = self._content_region()
        cx = float(region.center[0])
        y = float(region.top) - _ANCHOR_TOP_BUFF
        for node_id in visible:
            mob = self.mobjects[node_id]
            y -= float(mob.height) / 2
            mob.move_to([cx, y, 0.0])
            y -= float(mob.height) / 2 + _LINE_BUFF

    def _fork_group_ids(self) -> set[str]:
        """Fork stem, both branches, and banner notes. Overflow fade must not drop one side."""
        ids = set(self.tree.fork_points)
        for members in self.tree.fork_columns().values():
            ids.update(members)
        for node in self.tree.nodes.values():
            if (
                node.op == "note"
                and node.parents
                and self.tree.is_fork_point(node.parents[0])
            ):
                ids.add(node.id)
        return ids

    def _fade_oldest(self, *, animate: bool = True) -> None:
        if not self.stack:
            return
        protected = self._fork_group_ids()
        old_id = next(
            (
                i
                for i in self.stack
                if i in self.on_screen and i not in protected
            ),
            None,
        )
        if old_id is None:
            return
        self.stack = [i for i in self.stack if i != old_id]
        collapse = 0.0
        old_mob = self.mobjects.get(old_id)
        if old_mob is not None:
            collapse = float(old_mob.height) + _LINE_BUFF
        run_time = 0.35 if animate else 0.0
        if old_id in self.mobjects and old_id in self.on_screen:
            if self.scene is None or not animate:
                self.on_screen.discard(old_id)
            else:
                fade = FadeOut(self.mobjects[old_id], shift=UP * 0.2)
                movers = [self.mobjects[i] for i in self._visible() if i != old_id]
                if collapse > 0.01 and movers:
                    self.scene.play(
                        AnimationGroup(
                            fade,
                            *[m.animate.shift(UP * collapse) for m in movers],
                            lag_ratio=0.0,
                        ),
                        run_time=run_time,
                        rate_func=rate_functions.smooth,
                    )
                else:
                    self.scene.play(
                        fade,
                        run_time=run_time,
                        rate_func=rate_functions.smooth,
                    )
                self.on_screen.discard(old_id)
        self.tree.retire(old_id)
        if collapse > 0.01 and self._visible() and (self.scene is None or not animate):
            self._shift_group(collapse, run_time=run_time)
