"""Unit tests for catalog planners."""

from __future__ import annotations

from cinemath.catalog import (
    plan_double_integral,
    plan_linear_system_2d,
    plan_linear_system_3d,
    plan_quadratic,
    run_catalog,
)
from cinemath.render_engine.validate import validate_animation
from cinemath.templates import compile_plan


def test_plan_quadratic() -> None:
    plan = plan_quadratic("Solve for $x$: $x^2 - 5x + 6 = 0$", a=1, b=-5, c=6)
    assert plan["answer"] == "x = 2, x = 3"


def test_quadratic_factor_process() -> None:
    plan = plan_quadratic("Solve", a=1, b=-5, c=6)
    titles = [s["title"] for s in plan["steps"]]
    assert titles == [
        "Identify the quadratic",
        "Find two numbers",
        "Split the middle term",
        "Factor by grouping",
        "Solve for x",
        "Verify",
    ]
    pair = next(s for s in plan["steps"] if s["title"] == "Find two numbers")
    assert r"(-2) \cdot (-3) = 6" in pair["math"][0]
    solve = next(s for s in plan["steps"] if s["title"] == "Solve for x")
    assert solve["math"] == []
    assert solve["cases"] == [
        {"math": ["x - 2 = 0", "x = 2"]},
        {"math": ["x - 3 = 0", "x = 3"]},
    ]
    verify = next(s for s in plan["steps"] if s["title"] == "Verify")
    assert verify["math"] == []
    assert len(verify["cases"]) == 2


def test_quadratic_board_verify_continues_branches() -> None:
    plan = plan_quadratic("Solve", a=1, b=-5, c=6)
    animation = validate_animation(compile_plan(plan))
    board = next(s for s in animation["scenes"] if s["id"].startswith("board_"))
    actions = board["actions"]
    fork = next(a for a in actions if a["op"] == "fork")
    stem_id = fork["from"]
    objects = {o["id"]: o for o in board["objects"]}
    assert objects[stem_id]["type"] == "math"
    assert "(x - 2)" in objects[stem_id]["tex"] or "(x-2)" in objects[stem_id]["tex"]
    post_fork = actions[actions.index(fork) + 1 :]
    assert not any(a["op"] == "derive" and a["from"] == stem_id for a in post_fork)
    assert not any(a["op"] == "fork" and objects[a["from"]]["type"] != "math" for a in actions)
    assert sum(1 for a in actions if a["op"] == "fork") == 1
    assert not any(o["type"] == "prose" for o in objects.values())
    assert not any(a["op"] == "note" for a in actions)
    captions = [a["text"] for a in actions if a["op"] == "set_caption"]
    assert any("Substitute" in text for text in captions)
    fork_at = actions.index(fork)
    assert any(a["op"] == "set_caption" for a in actions[:fork_at])


def test_plan_double_integral() -> None:
    plan = plan_double_integral(
        r"Evaluate $\iint_R 6xy^2\,dA$.",
        integrand="6*x*y**2",
        x_min=2,
        x_max=4,
        y_min=1,
        y_max=2,
    )
    region = next(v for v in plan["visuals"] if v["tool"] == "show_region_rectangle")
    assert region["value"] == 84.0


def test_run_catalog_linear() -> None:
    plan = run_catalog(
        "plan_linear",
        {
            "problem_statement": "Solve for $x$: $2x + 5 = 17$.",
            "left": "2*x + 5",
            "right": "17",
        },
    )
    assert plan is not None
    assert plan["answer"] == "x = 6"
    math_lines = [line for step in plan["steps"] for line in step["math"]]
    assert math_lines == [
        "2 x + 5 = 17",
        "2 x + 5 - 5 = 17 - 5",
        "2 x = 12",
        r"\frac{2 x}{2} = \frac{12}{2}",
        "x = 6",
    ]
    assert plan["steps"][1]["explanation"] == "Subtract $5$ from both sides."
    assert plan["steps"][2]["explanation"] == "Divide both sides by $2$."
    assert plan["steps"][1]["speech"].count("[[beat]]") == 2
    assert "five" in plan["steps"][1]["speech"]
    assert "seventeen" in plan["steps"][1]["speech"]


def test_run_catalog_linear_both_sides() -> None:
    plan = run_catalog(
        "plan_linear",
        {
            "problem_statement": "Solve for $x$: $2x + 5 = x + 10$.",
            "left": "2*x + 5",
            "right": "x + 10",
        },
    )
    assert plan is not None
    assert plan["answer"] == "x = 5"
    math_lines = [line for step in plan["steps"] for line in step["math"]]
    assert math_lines == [
        "2 x + 5 = x + 10",
        "2 x + 5 - x = x + 10 - x",
        "x + 5 = 10",
        "x + 5 - 5 = 10 - 5",
        "x = 5",
    ]
    assert plan["steps"][1]["explanation"] == "Subtract $x$ from both sides."


def test_run_catalog_freeform() -> None:
    assert run_catalog("teach_freeform", {"reason": "proof"}) is None


def test_plan_linear_system_2d() -> None:
    plan = plan_linear_system_2d(
        "Solve $x+y=5$, $x-y=1$.",
        a1=1,
        b1=1,
        c1=5,
        a2=1,
        b2=-1,
        c2=1,
    )
    assert plan["answer"] == r"x = 3,\; y = 2"
    vis = next(v for v in plan["visuals"] if v["tool"] == "plot_lines_2d")
    assert vis["solution"] == {"x": 3.0, "y": 2.0}
    animation = validate_animation(compile_plan(plan))
    assert any(s["id"].startswith("plot_lines_2d_") for s in animation["scenes"])


def test_plan_linear_system_3d() -> None:
    plan = plan_linear_system_3d(
        "Solve $x+y=3$, $y+z=5$, $x+z=4$.",
        a1=1,
        b1=1,
        c1=0,
        d1=3,
        a2=0,
        b2=1,
        c2=1,
        d2=5,
        a3=1,
        b3=0,
        c3=1,
        d3=4,
    )
    assert plan["answer"] == r"x = 1,\; y = 2,\; z = 3"
    vis = next(v for v in plan["visuals"] if v["tool"] == "plot_planes_3d")
    assert vis["solution"] == {"x": 1.0, "y": 2.0, "z": 3.0}
    animation = validate_animation(compile_plan(plan))
    assert any(s["id"].startswith("plot_planes_3d_") for s in animation["scenes"])
    planes = next(s for s in animation["scenes"] if s["id"].startswith("plot_planes_3d_"))
    assert planes["mode"] == "3d"
    assert sum(1 for o in planes["objects"] if o["type"] == "plane") == 3
