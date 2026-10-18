"""Cross-cutting pipeline utilities."""

from cinemath.core.ingest import ProblemInput, load_problem
from cinemath.core.logger import configure, fmt_path, get_logger, log_step

__all__ = [
    "ProblemInput",
    "RunResult",
    "configure",
    "fmt_path",
    "get_logger",
    "load_problem",
    "log_step",
    "run_pipeline",
]


def __getattr__(name: str):
    # Lazy: pipeline imports render, and render imports logger via this package.
    if name in {"RunResult", "run_pipeline"}:
        from cinemath.core import pipeline as _pipeline

        return getattr(_pipeline, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
