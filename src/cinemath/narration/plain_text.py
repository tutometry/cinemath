"""Strip LaTeX / markup so TTS engines receive speakable prose."""

from __future__ import annotations

import re

from cinemath.narration.speak_math import latex_fragment_to_speech

_INLINE_DOLLAR = re.compile(r"\$([^$]+)\$")
_INLINE_PAREN = re.compile(r"\\\((.+?)\\\)")
_DISPLAY = re.compile(r"\$\$[^$]+\$\$|\\\[[^\]]+\\\]")
_CMD = re.compile(r"\\[a-zA-Z]+")
_BRACES = re.compile(r"[{}]")
_WS = re.compile(r"\s+")


def narration_to_speech(text: str) -> str:
    """Best-effort plain text for TTS from teacher / caption strings."""
    if not text:
        return ""
    out = text
    out = _DISPLAY.sub(" ", out)
    out = _INLINE_DOLLAR.sub(lambda m: latex_fragment_to_speech(m.group(1)), out)
    out = _INLINE_PAREN.sub(lambda m: latex_fragment_to_speech(m.group(1)), out)
    out = _CMD.sub(" ", out)
    out = out.replace("_", " ").replace("^", " ")
    out = _BRACES.sub(" ", out)
    out = out.replace(";", ",")
    out = _WS.sub(" ", out).strip()
    return out
