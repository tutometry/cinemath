"""Equation tree: git-style history for the algebra board.

Nodes are equations. Edges are explicit, so playback never guesses:

- ``root``    — first line (``write``)
- ``commit``  — one parent, new line below; parent stays, dimmed (``derive``)
- ``fork``    — one parent, several children in columns; parent stays full
- ``advance`` — move a tip in place; the parent line is retired (does not return)
- ``merge``   — several parents, one child below their span

Fork points are protected: overflow cleanup must not fade the line you branched from.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EqNode:
    id: str
    parents: tuple[str, ...] = ()
    op: str = "root"
    seq: int = 0
    # ``below``: a fork-stem note that sits under the current branches, not in a column.
    banner: str = ""


@dataclass
class EquationTree:
    nodes: dict[str, EqNode] = field(default_factory=dict)
    children: dict[str, list[str]] = field(default_factory=dict)
    replaced_by: dict[str, str] = field(default_factory=dict)
    fork_points: set[str] = field(default_factory=set)
    retired: set[str] = field(default_factory=set)
    _seq: int = 0

    def clear(self) -> None:
        self.nodes.clear()
        self.children.clear()
        self.replaced_by.clear()
        self.fork_points.clear()
        self.retired.clear()
        self._seq = 0

    def root(self, node_id: str) -> None:
        if node_id not in self.nodes:
            self.nodes[node_id] = EqNode(node_id, (), "root")

    def commit(self, parent: str, child: str) -> None:
        self._link(child, (parent,), "commit")

    def note(self, parent: str, child: str, *, below: bool = False) -> None:
        """Instruction line. ``below`` hangs it under a fork's branches, full width."""
        self._link(child, (parent,), "note")
        if below:
            self.nodes[child].banner = "below"

    def fork(self, parent: str, children: list[str]) -> None:
        self.fork_points.add(parent)
        for child in children:
            self._link(child, (parent,), "fork")

    def advance(self, parent: str, child: str) -> None:
        self._link(child, (parent,), "advance")
        self.retired.add(parent)
        self.replaced_by[parent] = child

    def merge(self, parents: list[str], child: str) -> None:
        self._link(child, tuple(parents), "merge")

    def retire(self, node_id: str) -> None:
        self.retired.add(node_id)

    def is_fork_point(self, node_id: str) -> bool:
        return node_id in self.fork_points and node_id not in self.retired

    def tip(self, node_id: str) -> str:
        seen: set[str] = set()
        while node_id in self.replaced_by and node_id not in seen:
            seen.add(node_id)
            node_id = self.replaced_by[node_id]
        return node_id

    def fork_columns(self, pending: set[str] | None = None) -> dict[str, list[str]]:
        """Visible members of each column under a fork, keyed by the original child."""
        pending = pending or set()
        columns: dict[str, list[str]] = {}
        for fork_id in list(self.nodes):
            if not self.is_fork_point(fork_id):
                continue
            for child in self.children.get(fork_id, []):
                child_node = self.nodes.get(child)
                if child_node is not None and child_node.op == "note":
                    continue
                members = [
                    n
                    for n in self._column_members(child)
                    if n not in self.retired or n in pending
                ]
                if not members and child in pending:
                    members = [child]
                if members:
                    columns[child] = members
        return columns

    def branch_tips(self, pending: set[str] | None = None) -> list[str]:
        """Last visible node in each fork column."""
        tips: list[str] = []
        for members in self.fork_columns(pending).values():
            if members:
                tips.append(members[-1])
        return tips

    def _column_members(self, node_id: str) -> list[str]:
        members: list[str] = []

        def walk(nid: str) -> None:
            if nid in self.replaced_by:
                walk(self.replaced_by[nid])
                return
            if nid in self.retired:
                return
            members.append(nid)
            for child in self.children.get(nid, []):
                op = self.nodes[child].op if child in self.nodes else ""
                if op in {"commit", "advance"}:
                    walk(child)

        walk(node_id)
        return members

    def role(self, node_id: str) -> str:
        """``gone`` | ``stem`` | ``history`` | ``tip``."""
        if node_id in self.retired or node_id not in self.nodes:
            return "gone"
        if self.is_fork_point(node_id):
            return "stem"
        living = [c for c in self.children.get(node_id, []) if c not in self.retired]
        if living:
            return "history"
        return "tip"

    def _link(self, child: str, parents: tuple[str, ...], op: str) -> None:
        self._seq += 1
        self.nodes[child] = EqNode(child, parents, op, seq=self._seq)
        for parent in parents:
            if parent not in self.nodes:
                self._seq += 1
                self.nodes[parent] = EqNode(parent, (), "root", seq=self._seq)
            self.children.setdefault(parent, []).append(child)
