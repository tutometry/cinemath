# CPO / CTO A/B — narrated sample lesson

**Checkable artifact (in git):**

```
cinemath/docs/samples/narration-quadratic/animation.mp4
```

GitHub (spike PR branch):  
https://github.com/mauted/tutometry/blob/cursor/kokoro-tts-spike-a8f4/cinemath/docs/samples/narration-quadratic/animation.mp4

~1–2 MB · catalog quadratic · web composition (720p30) · **muxed narration** (Kokoro when rebuilt locally).

| File | Role |
| --- | --- |
| `plan.json` | Deterministic catalog teacher plan (no LLM) |
| `animation.json` | Compiled Manim script |
| `animation.mp4` | **A/B “with narration”** variant |
| `narration/manifest.json` | Line text + `start_seconds` for mux |

**Silent B-side** (same visuals, narration pipeline not run):

```bash
cd cinemath
uv run cinemath render docs/samples/narration-quadratic/animation.json \
  -o /tmp/quadratic-silent.mp4 -q w -c web
```

**Regenerate narrated file** (requires `uv sync --extra narration` and Kokoro weights in `~/.cache/cinemath/tts`):

```bash
cd cinemath
uv sync --extra narration
./scripts/fetch-kokoro-onnx-models.sh   # once, if needed
uv run python scripts/build-narration-sample.py
```

Placeholder beeps (CI only): `CINEMATH_TTS_MOCK=1 uv run python scripts/build-narration-sample.py`

Spike docs: [`../../../../docs/engineering/kokoro-tts-spike.md`](../../../../docs/engineering/kokoro-tts-spike.md)
