"""Equation-tree structure: fork, advance, merge — no Manim."""

from cinemath.render_engine.equation_tree import EquationTree


def test_fork_stem_stays_and_advance_retires_tip() -> None:
    tree = EquationTree()
    tree.root("eq0")
    tree.fork("eq0", ["eq1", "eq2"])
    tree.advance("eq1", "eq3")

    assert tree.role("eq0") == "stem"
    assert tree.role("eq1") == "gone"
    assert tree.role("eq3") == "tip"
    assert tree.tip("eq1") == "eq3"
    columns = tree.fork_columns()
    assert columns["eq1"] == ["eq3"]
    assert columns["eq2"] == ["eq2"]


def test_fork_columns_skip_banner_notes() -> None:
    tree = EquationTree()
    tree.root("eq0")
    tree.note("eq0", "intro")
    tree.fork("eq0", ["eq1", "eq2"])
    tree.note("eq0", "verify", below=True)
    columns = tree.fork_columns()
    assert set(columns) == {"eq1", "eq2"}
    assert "intro" not in columns
    assert "verify" not in columns
    assert tree.nodes["verify"].banner == "below"
    assert tree.nodes["intro"].op == "note"


def test_merge_joins_tips() -> None:
    tree = EquationTree()
    tree.root("eq0")
    tree.fork("eq0", ["eq1", "eq2"])
    tree.advance("eq1", "eq3")
    tree.advance("eq2", "eq4")
    tree.merge(["eq3", "eq4"], "eq5")

    assert tree.nodes["eq5"].op == "merge"
    assert tree.nodes["eq5"].parents == ("eq3", "eq4")
    assert tree.role("eq5") == "tip"
    assert tree.role("eq3") == "history"
    assert tree.is_fork_point("eq0")
