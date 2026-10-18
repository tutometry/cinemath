"""Optional lesson narration (Kokoro TTS + Piper fallback). Default off."""

from cinemath.narration.config import narration_requested
from cinemath.narration.pipeline import apply_narration

__all__ = ["apply_narration", "narration_requested"]
