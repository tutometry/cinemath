# Micro fixture: board fork (two roots)

Isolated beat: factored quadratic → **fork** → **derive** on each branch (`x - 2 = 0` → `x = 2`, etc.) → box.

Uses `derive` (commit below, parent stays bright) — not `advance` (in-place replace).

No LLM, no plot, no problem statement.

```bash
cd cinemath
uv run python docs/fixtures/board-fork-two-roots/build.py
uv run cinemath render docs/fixtures/board-fork-two-roots/animation.json \
  -o docs/fixtures/board-fork-two-roots/review.mp4 -q m -c web
```

Invariant focus: **Q5** (fork readability) in `docs/engineering/quadratic-animation-invariants.md`.
