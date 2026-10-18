# cinemath

CLI and library that turns a math problem into a short educational Manim animation.

> This is the Cinemath git repo. Tutometry's API calls the HTTP worker; it does not import this code.

![Pseudoscalar Yukawa β-function lesson](preview.gif)

**Architecture (v0.4):**

1. **LLM classifies** → picks one catalog planner (`plan_*`) or `teach_freeform`
2. **Catalog planner** → local `plan_*` builds `plan.json` (SymPy / arithmetic)
3. **Freeform teacher** → LLM writes `plan.json` when no catalog entry fits
4. **Local verify** → SymPy checks freeform plans; failures are re-fed to the LLM until correct (`verify.json`)
5. **Local visual compilers** → `animation.json`
6. **Local renderer** → Manim video

Algebra steps use an **equation chain** (`render_engine/equation_chain.py`): dim the prior line, scroll up to make room, then morph a copy into the next equation with `TransformMatchingTex`. Step **explanations** become larger instruction banners (`render_engine/instructions.py`) placed above the active work, at the bottom under plots, or at the top when that is clearest.

Every animation opens with a **problem statement** beat (`problem_statement.py`): the statement is written onto the board, held to read, then cleared before the solution.

Graphs live in **`graph_2d.py`** / **`graph_3d.py`**: auto axis ranges, filled regions, full-frame surfaces with flat captions.

## Setup

```bash
cd cinemath   # from monorepo root
brew install cairo pkg-config   # once, for Manim
uv sync
cp .env.example .env            # set ANTHROPIC_API_KEY
```

Optional: `ANTHROPIC_CLASSIFY_MODEL` (default Haiku) for routing/OCR; `ANTHROPIC_TEACH_MODEL` (default Sonnet) for freeform plans. `ANTHROPIC_MODEL` overrides both when the specific vars are unset. If Anthropic returns “key is not workspace-scoped”, set `ANTHROPIC_WORKSPACE_ID=wrkspc_…` (or use a workspace-scoped API key). Use `--verbose` / `CINEMATH_LOG_LEVEL=DEBUG` for full pipeline logs (color on in TTY; set `NO_COLOR=1` or `CINEMATH_LOG_COLOR=0` to disable).

**Ollama (classify only):** set `CINEMATH_CLASSIFY_PROVIDER=ollama`, `OLLAMA_BASE_URL`, and `OLLAMA_CLASSIFY_MODEL` (default `llama3.1:8b`). Routes catalog `plan_*` classification and `/v1/classify-topic` through local Ollama. Freeform teaching and image/PDF extraction still require Anthropic. On mautedpc, Ollama must listen on an address reachable from Docker (e.g. `OLLAMA_HOST=0.0.0.0:11434` in the Ollama systemd unit, firewall accordingly); the stack sets `OLLAMA_BASE_URL=http://host.docker.internal:11434` on `cinemath-worker`.

## Usage

```bash
uv run cinemath solve examples/01_watermelons.txt
uv run cinemath solve examples/07_double_integral.md
uv run cinemath solve examples/10_scalar_decay.md
uv run cinemath solve path/to/photo.png
```

See [`problems/curated/README.md`](../problems/curated/README.md) for the full **difficulty ladder** (arithmetic → QFT).

## Worker (HTTP, co-deployed with Tutometry)

Production image (`Dockerfile`) defaults to **`cinemath-worker`** — an HTTP server on the Docker network at `http://cinemath-worker:8080` (`CINEMATH_WORKER_URL` on the Next.js app). Routes: `POST /v1/generate`, `POST /v1/classify-topic`, `POST /v1/extract-assignment`, `GET /v1/artifacts/{job}/{attempt}/{file}` with bearer `WORKER_SHARED_SECRET` (same value as Tutometry `CINEMATH_WORKER_SECRET`). Required env: `ANTHROPIC_API_KEY`, `WORKER_SHARED_SECRET`. Optional: `ANTHROPIC_WORKSPACE_ID`, `ANTHROPIC_CLASSIFY_MODEL`, `ANTHROPIC_TEACH_MODEL`, `CINEMATH_CLASSIFY_PROVIDER`, `OLLAMA_BASE_URL`, `OLLAMA_CLASSIFY_MODEL`.

On mautedpc, `.github/workflows/deploy-cinemath.yml` builds and rolls the worker via `scripts/ci-deploy-cinemath.sh`. API contract: `contracts/cinemath-worker.openapi.yaml`.

For one-shot batch runs (no HTTP), use **`cinemath-worker-job`** and pass JSON on **stdin** or **argv[1]**.

**Problem banks:** [`problems/README.md`](problems/README.md) — Lamar (650+ scraped), MIT, Arizona, OpenStax, organized under `problems/by-type/<planner>/` for batch testing. Sync with `uv run python scripts/sync_problem_banks.py`.

**Source layout:** `src/cinemath/` is grouped by concern:

- `core/` — pipeline, ingest, logging
- `plan/` — teacher plan schema and validation
- `teaching/` — LLM teacher and SymPy verify
- `planners/` — catalog solvers by domain (`algebra/`, `arithmetic/`, `calculus/`)
- `render_engine/`, `templates/`, `problems/` — animation IR and problem banks

## Preprint

Architecture write-up with pipeline diagram:
[`docs/cinemath_showcase_report.pdf`](docs/cinemath_showcase_report.pdf)

## Output

```text
outputs/<timestamp>_<slug>/
  problem.txt
  plan.json         # catalog planner or freeform LLM teacher
  lesson.md
  verify.json       # freeform plans only (SymPy check + retry summary)
  animation.json    # intermediate representation (re-render with cinemath)
  animation.mp4
```

Manim renders into a temp directory by default; use `--keep-media` to retain `media/` for debugging.

## Visual tools

`plan.json` now chooses **local visual capabilities** with a `visuals[]` list instead of one
mutually exclusive problem type.

| Tool | Purpose |
|---|---|
| `equation_board` | Board: caption + stacked math per step |
| `state_claim` / `show_qed` | Proof-style opener / closer |
| `plot_2d` | 2D quadratic parabola + marked roots |
| `show_region_rectangle` | 2D rectangular integration region |
| `plot_surface_3d` | 3D surface over a rectangular domain |
| `paper_long_multiply` | Paper long multiplication + side digit calc |
| `paper_long_divide` | Paper long division |
| `paper_long_add` | Paper long addition + side column calc |
| `paper_long_subtract` | Paper long subtraction + borrow marks |
| `show_lagrangian` | QFT Lagrangian / interaction setup |
| `feynman_1to2` | Tree-level 1→2 decay diagram |
| `feynman_loop` | One-loop / 1PI layouts (`loop_bubble`, `four_point_loop`, `yukawa_triangle`) |
| `rg_flow_2d` | 2D RG flow arrow field from β(x,y) expressions |
| `show_answer` | Final highlighted answer beat |

Common recipes:

- Generic worked solution: `equation_board`
- Quadratic: `plot_2d` + `equation_board` + `show_answer`
- Rectangle double integral: `show_region_rectangle` + `equation_board` + `plot_surface_3d` + `show_answer`
- Proof / identity derivation: `state_claim` + `equation_board` + `show_qed`
- Paper arithmetic: one matching `paper_long_*`
- QFT decay: `show_lagrangian` + `feynman_1to2` + `equation_board` + `show_answer`
- QFT β / RG: `show_lagrangian` + `feynman_loop` + `equation_board` + `rg_flow_2d` + `show_answer`
