#!/usr/bin/env python3
"""Regenerate animation.json for the isolated board-fork micro lesson."""

from __future__ import annotations

import json
from pathlib import Path

from cinemath.render_engine.validate import validate_animation
from cinemath.templates import dsl

DIR = Path(__file__).resolve().parent


def main() -> None:
    script = dsl.script(
        problem="Micro: fork two roots after factoring.",
        answer="x = 2, x = 3",
        steps=["Fork", "Solve branches"],
        scenes=[
            dsl.scene(
                "fork_demo",
                caption="Set each factor equal to zero.",
                template="board_only",
                pin=False,
                objects=[
                    dsl.math("eq0", r"(x - 2)(x - 3) = 0", font_size=36),
                    dsl.math("eq1", r"x - 2 = 0", font_size=36),
                    dsl.math("eq2", r"x - 3 = 0", font_size=36),
                    dsl.math("eq3", r"x = 2", font_size=36),
                    dsl.math("eq4", r"x = 3", font_size=36),
                ],
                actions=[
                    dsl.wait(0.6),
                    dsl.write("eq0"),
                    dsl.wait(0.8),
                    dsl.fork("eq0", "eq1", "eq2", buff=0.75),
                    dsl.wait(0.6),
                    dsl.derive("eq1", "eq3", buff=0.55),
                    dsl.wait(0.4),
                    dsl.derive("eq2", "eq4", buff=0.55),
                    dsl.wait(0.8),
                    dsl.box("eq3", "eq4"),
                    dsl.wait(1.0),
                ],
            )
        ],
    )
    out = validate_animation(script)
    path = DIR / "animation.json"
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
