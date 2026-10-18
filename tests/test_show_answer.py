"""Compiler invariants for show_answer on catalog lessons."""

from __future__ import annotations

from cinemath.catalog import plan_quadratic
from cinemath.render_engine.validate import validate_animation
from cinemath.templates import compile_plan


def _last_box_targets(animation: dict) -> list[str]:
    board = next(s for s in animation["scenes"] if s["id"].startswith("board_"))
    boxes = [a for a in board["actions"] if a.get("op") == "box"]
    assert boxes, "expected a box action from show_answer"
    return list(boxes[-1].get("targets") or [])


def test_quadratic_show_answer_boxes_roots_not_verify() -> None:
    plan = plan_quadratic("Solve for $x$: $x^2 - 5x + 6 = 0$.", a=1, b=-5, c=6)
    animation = validate_animation(compile_plan(plan))
    board = next(s for s in animation["scenes"] if s["id"].startswith("board_"))
    tex_by_id = {
        o["id"]: str(o.get("tex") or "")
        for o in board["objects"]
        if o.get("type") == "math"
    }
    targets = _last_box_targets(animation)
    boxed_tex = [tex_by_id[tid] for tid in targets if tid in tex_by_id]
    assert any("x = 2" in t or "x=2" in t for t in boxed_tex)
    assert any("x = 3" in t or "x=3" in t for t in boxed_tex)
    assert not any("6" in t and "+" in t and "verify" in t.lower() for t in boxed_tex)
