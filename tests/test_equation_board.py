"""Equation-board scroll / fade policy."""

from __future__ import annotations

from manim import DOWN, MathTex

from cinemath.render_engine.equation_chain import EquationBoard, _LINE_BUFF
from cinemath.render_engine.sanitize import to_math_tex
from cinemath.render_engine.stage import Region


def test_fit_fades_until_lines_sit_in_band() -> None:
    """A short band drops older lines until the rest fits. Glyph size stays put."""
    band = Region(
        center=(0.0, 0.0),
        max_w=6.0,
        max_h=1.2,
        left=-3.0,
        right=3.0,
        bottom=-0.8,
        top=0.4,
    )
    tex_lines = [r"a", r"b", r"c", r"d"]
    mobjects = {f"eq{i}": MathTex(to_math_tex(t)) for i, t in enumerate(tex_lines)}
    ids = list(mobjects.keys())
    widths = {eid: float(mobjects[eid].width) for eid in ids}

    board = EquationBoard(
        scene=None,  # type: ignore[arg-type]
        mobjects=mobjects,
        on_screen=set(ids),
        content_region=lambda: band,
        accent_color=lambda: "yellow",
    )
    board.set_band(band)
    for i, eid in enumerate(ids):
        mob = mobjects[eid]
        if i == 0:
            board._anchor_line(mob)
        else:
            mob.next_to(mobjects[ids[i - 1]], DOWN, buff=_LINE_BUFF)
        board.stack.append(eid)

    board._fit_after_write()
    visible = board._visible()
    assert visible
    assert len(visible) < 4
    for eid in visible:
        mob = mobjects[eid]
        assert float(mob.get_bottom()[1]) >= band.bottom - 0.08
        assert float(mob.get_top()[1]) <= band.top + 0.08
        assert abs(float(mob.width) - widths[eid]) < 1e-5


def test_shrinking_band_fades_in_one_motion() -> None:
    """A line leaves in the same play the others glide. Nothing pops, and nothing shifts beforehand."""
    from manim import FadeOut

    band = _tall_board_band()
    short = Region(
        center=(0.0, -1.5),
        max_w=12.0,
        max_h=2.0,
        left=-6.0,
        right=6.0,
        bottom=-2.5,
        top=-0.5,
    )
    mobjects = {f"eq{i}": MathTex(to_math_tex(tex)) for i, tex in enumerate(["a", "b", "c", "d"])}

    class _RecordingScene(_StubScene):
        def __init__(self) -> None:
            super().__init__()
            self.plays: list[tuple[object, ...]] = []

        def play(self, *args, **kwargs) -> None:
            self.plays.append(args)

    scene = _RecordingScene()
    board = EquationBoard(
        scene=scene,  # type: ignore[arg-type]
        mobjects=mobjects,
        on_screen=set(),
        content_region=lambda: band,
        accent_color=lambda: "yellow",
    )
    board.set_band(band)
    for eid in mobjects:
        board.write([eid])
    scene.plays.clear()
    board.set_band(short)
    board.settle_into_band(animate=True)

    assert len(scene.plays) == 1
    assert any(isinstance(anim, FadeOut) for anim in scene.plays[0])
    assert any(type(anim).__name__ == "_AnimationBuilder" for anim in scene.plays[0])
    assert "eq0" not in board.on_screen


class _StubScene:
    """Minimal scene so fork/derive can run without a Manim render."""

    mobjects: list

    def __init__(self) -> None:
        self.mobjects = []

    def add(self, *mobs) -> None:
        for mob in mobs:
            if mob not in self.mobjects:
                self.mobjects.append(mob)

    def remove(self, mob) -> None:
        while mob in self.mobjects:
            self.mobjects.remove(mob)

    def play(self, *args, **kwargs) -> None:
        return None


def _tall_board_band() -> Region:
    return Region(
        center=(0.0, 0.0),
        max_w=12.0,
        max_h=8.0,
        left=-6.0,
        right=6.0,
        bottom=-3.5,
        top=3.5,
    )


def _boxes_overlap(a, b, *, pad: float = 0.02) -> bool:
    return not (
        float(a.get_right()[0]) < float(b.get_left()[0]) + pad
        or float(b.get_right()[0]) < float(a.get_left()[0]) + pad
        or float(a.get_bottom()[1]) > float(b.get_top()[1]) - pad
        or float(b.get_bottom()[1]) > float(a.get_top()[1]) - pad
    )


def test_quadratic_board_fork_does_not_overlap_or_leave_band() -> None:
    """Fork stem is math, banner notes stay out of the columns, ink stays in the band."""
    from cinemath.catalog import plan_quadratic
    from cinemath.render_engine.composition import apply_manim_config, set_composition_env
    from cinemath.render_engine.layout.bands import sync_board_band
    from cinemath.render_engine.validate import validate_animation
    from cinemath.templates import compile_plan
    from tests.layout_helpers import build_scene_mobjects

    set_composition_env("web")
    apply_manim_config()
    animation = validate_animation(
        compile_plan(plan_quadratic("Solve", a=1, b=-5, c=6))
    )
    scene = next(s for s in animation["scenes"] if s["id"].startswith("board_"))
    stage, mobjects, meta = build_scene_mobjects(scene, "web", use_right_stage=True)
    stage.use_right_stage = True
    board = EquationBoard(
        scene=_StubScene(),  # type: ignore[arg-type]
        mobjects=mobjects,
        on_screen=set(),
        content_region=stage.board_region,
        accent_color=lambda: "yellow",
    )
    sync_board_band(stage, board)
    region = stage.board_region()

    def assert_ink_in_band(step: str) -> None:
        visible = [i for i in board.stack if i in board.on_screen]
        for left_i, right_i in (
            (a, b) for i, a in enumerate(visible) for b in visible[i + 1 :]
        ):
            assert not _boxes_overlap(mobjects[left_i], mobjects[right_i]), (
                step,
                left_i,
                right_i,
            )
        for node_id in visible:
            mob = mobjects[node_id]
            assert float(mob.get_left()[0]) >= region.left - 0.08, (step, node_id)
            assert float(mob.get_right()[0]) <= region.right + 0.08, (step, node_id)
            assert float(mob.get_bottom()[1]) >= region.bottom - 0.08, (step, node_id)
            assert float(mob.get_top()[1]) <= region.top + 0.08, (step, node_id)

    for action in scene["actions"]:
        op = action["op"]
        if op == "write":
            board.write(action["targets"])
        elif op == "note":
            board.note(action["from"], action["to"])
        elif op == "derive":
            board.derive(action["from"], action["to"])
        elif op == "fork":
            assert meta[action["from"]]["type"] == "math"
            board.fork(action["from"], action["to"])
        elif op in {"box", "highlight", "set_caption"}:
            continue
        else:
            continue
        assert_ink_in_band(op)


def test_fork_motion_starts_at_the_instruction_above_it() -> None:
    """Branches grow out of the note sitting above them, not the equation above that note."""
    from manim import ReplacementTransform

    band = _tall_board_band()
    mobjects = {
        "eq0": MathTex(to_math_tex(r"(x-2)(x-3)=0")),
        "note": MathTex(to_math_tex(r"0")),
        "eq1": MathTex(to_math_tex(r"x-2=0")),
        "eq2": MathTex(to_math_tex(r"x-3=0")),
    }

    class _RecordingScene(_StubScene):
        def __init__(self) -> None:
            super().__init__()
            self.starts: list[tuple[float, float]] = []

        def play(self, *args, **kwargs) -> None:
            note = mobjects["note"].get_center()
            for anim in args:
                if isinstance(anim, ReplacementTransform):
                    center = anim.mobject.get_center()
                    assert abs(float(center[0]) - float(note[0])) < 0.05
                    assert abs(float(center[1]) - float(note[1])) < 0.05
                    self.starts.append((float(center[0]), float(center[1])))

    scene = _RecordingScene()
    board = EquationBoard(
        scene=scene,  # type: ignore[arg-type]
        mobjects=mobjects,
        on_screen=set(),
        content_region=lambda: band,
        accent_color=lambda: "yellow",
    )
    board.set_band(band)
    board.write(["eq0"])
    board.note("eq0", "note")
    board.fork("eq0", ["eq1", "eq2"])

    assert len(scene.starts) == 2
    assert board._fork_reveal_source("eq0", ["eq1", "eq2"]) is mobjects["note"]


def test_fork_exit_and_enter_share_one_play() -> None:
    """A line that leaves to make room fades in the same play the branches arrive."""
    from manim import FadeOut, ReplacementTransform

    band = Region(
        center=(0.0, 0.0),
        max_w=8.0,
        max_h=2.3,
        left=-4.0,
        right=4.0,
        bottom=-1.15,
        top=1.15,
    )
    mobjects = {
        "old": MathTex(to_math_tex(r"x^{2}-5x+6=0")),
        "stem": MathTex(to_math_tex(r"(x-2)(x-3)=0")),
        "eq1": MathTex(to_math_tex(r"x-2=0")),
        "eq2": MathTex(to_math_tex(r"x-3=0")),
    }

    class _RecordingScene(_StubScene):
        def __init__(self) -> None:
            super().__init__()
            self.plays: list[tuple[type, ...]] = []

        def play(self, *args, **kwargs) -> None:
            self.plays.append(tuple(type(anim) for anim in args))

    scene = _RecordingScene()
    board = EquationBoard(
        scene=scene,  # type: ignore[arg-type]
        mobjects=mobjects,
        on_screen=set(),
        content_region=lambda: band,
        accent_color=lambda: "yellow",
    )
    board.set_band(band)
    board.write(["old"])
    board.derive("old", "stem")
    assert "old" in board.on_screen
    board.fork("stem", ["eq1", "eq2"])

    fork_plays = [kinds for kinds in scene.plays if ReplacementTransform in kinds]
    assert len(fork_plays) == 1
    assert FadeOut in fork_plays[0]
    assert "old" not in board.on_screen
    assert "eq1" in board.on_screen
    assert "eq2" in board.on_screen


def test_fork_keeps_parent_visible() -> None:
    band = _tall_board_band()
    mobjects = {
        "eq0": MathTex(to_math_tex(r"(x-2)(x-3)=0")),
        "eq1": MathTex(to_math_tex(r"x-2=0")),
        "eq2": MathTex(to_math_tex(r"x-3=0")),
    }
    board = EquationBoard(
        scene=_StubScene(),  # type: ignore[arg-type]
        mobjects=mobjects,
        on_screen=set(),
        content_region=lambda: band,
        accent_color=lambda: "yellow",
    )
    board.set_band(band)
    mobjects["eq0"].set_opacity(1.0)
    board.on_screen.add("eq0")
    board.stack.append("eq0")
    board._anchor_line(mobjects["eq0"])

    board.fork("eq0", ["eq1", "eq2"])

    assert mobjects["eq0"].get_fill_opacity() == 1.0


def test_fade_oldest_keeps_fork_point() -> None:
    band = _tall_board_band()
    mobjects = {
        "old": MathTex(to_math_tex(r"a")),
        "eq0": MathTex(to_math_tex(r"b")),
        "eq1": MathTex(to_math_tex(r"c")),
        "eq2": MathTex(to_math_tex(r"d")),
    }
    board = EquationBoard(
        scene=None,  # type: ignore[arg-type]
        mobjects=mobjects,
        on_screen={"old", "eq0", "eq1", "eq2"},
        content_region=lambda: band,
        accent_color=lambda: "yellow",
    )
    board.set_band(band)
    board.stack = ["old", "eq0", "eq1", "eq2"]
    board.tree.root("old")
    board.tree.commit("old", "eq0")
    board.tree.fork("eq0", ["eq1", "eq2"])
    board._fade_oldest(animate=False)
    assert "old" not in board.on_screen
    assert "eq0" in board.on_screen
    assert "eq1" in board.on_screen
    assert "eq2" in board.on_screen


def test_advance_replaces_branch_tip_in_place() -> None:
    band = _tall_board_band()
    mobjects = {
        "eq0": MathTex(to_math_tex(r"(x-2)(x-3)=0")),
        "eq1": MathTex(to_math_tex(r"x-2=0")),
        "eq2": MathTex(to_math_tex(r"x-3=0")),
        "eq3": MathTex(to_math_tex(r"x=2")),
    }
    board = EquationBoard(
        scene=_StubScene(),  # type: ignore[arg-type]
        mobjects=mobjects,
        on_screen=set(),
        content_region=lambda: band,
        accent_color=lambda: "yellow",
    )
    board.set_band(band)
    board.on_screen.add("eq0")
    board.stack.append("eq0")
    board._anchor_line(mobjects["eq0"])
    board.fork("eq0", ["eq1", "eq2"])
    y_before = float(mobjects["eq1"].get_center()[1])
    board.advance("eq1", "eq3")
    y_after = float(mobjects["eq3"].get_center()[1])
    assert abs(y_after - y_before) < 0.08


def test_advance_retires_parent() -> None:
    band = _tall_board_band()
    mobjects = {
        "eq0": MathTex(to_math_tex(r"(x-2)(x-3)=0")),
        "eq1": MathTex(to_math_tex(r"x-2=0")),
        "eq2": MathTex(to_math_tex(r"x-3=0")),
        "eq3": MathTex(to_math_tex(r"x=2")),
    }
    board = EquationBoard(
        scene=_StubScene(),  # type: ignore[arg-type]
        mobjects=mobjects,
        on_screen=set(),
        content_region=lambda: band,
        accent_color=lambda: "yellow",
    )
    board.set_band(band)
    board.on_screen.add("eq0")
    board.stack.append("eq0")
    board._anchor_line(mobjects["eq0"])
    board.fork("eq0", ["eq1", "eq2"])
    board.advance("eq1", "eq3")

    assert "eq1" not in board.on_screen
    assert mobjects["eq1"].get_fill_opacity() == 0.0
    assert "eq3" in board.on_screen
    assert mobjects["eq3"].get_fill_opacity() == 1.0


def test_derive_keeps_parent_full_opacity() -> None:
    band = _tall_board_band()
    mobjects = {
        "eq0": MathTex(to_math_tex(r"x-2=0")),
        "eq1": MathTex(to_math_tex(r"x=2")),
    }
    board = EquationBoard(
        scene=_StubScene(),  # type: ignore[arg-type]
        mobjects=mobjects,
        on_screen=set(),
        content_region=lambda: band,
        accent_color=lambda: "yellow",
    )
    board.set_band(band)
    mobjects["eq0"].set_opacity(1.0)
    board.on_screen.add("eq0")
    board.stack.append("eq0")
    board._anchor_line(mobjects["eq0"])

    board.derive("eq0", "eq1")

    assert mobjects["eq0"].get_fill_opacity() == 1.0
    assert mobjects["eq1"].get_fill_opacity() == 1.0
