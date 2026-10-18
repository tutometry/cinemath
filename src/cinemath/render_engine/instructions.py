"""On-screen instruction / narration banner.

Owns TeX wrapping and fitting inside a Region supplied by layout / StageConductor.
Does not score placement against peer content — layout owns cross-hitbox policy.
"""

from __future__ import annotations

import re
from typing import Any

from manim import (
    DOWN,
    RIGHT,
    UP,
    AnimationGroup,
    FadeIn,
    FadeOut,
    VMobject,
    rate_functions,
)

from cinemath.render_engine.composition import get_composition, scale_font
from cinemath.render_engine.sanitize import unicode_math_char
from cinemath.render_engine.stage import Region, full_frame
from cinemath.render_engine.texutil import escape_latex_text

_TOP_BUFF = 0.2

_FONT_SIZE = 34
_FULL_PARBOX_CM = 11.8
_HALF_PARBOX_CM = 6.6
_MOBILE_PARBOX_CM = 5.6
_STATEMENT_WEB_PARBOX_CM = 10.8
_CAPTION_ENTER_TIME = 0.35
_CAPTION_CROSSFADE_TIME = 0.4
# Already-delimited inline math.
_DELIM_MATH = re.compile(r"\$.+?\$|\\\(.+?\\\)")

# ASCII / TeX tokens that should be typeset as math inside prose.
_MATH_TOKEN = re.compile(
    r"(?:"
    r"\\[A-Za-z]+(?:\{[^{}]*\})*(?:_\{[^{}]*\}|_\w)*(?:\^\{[^{}]*\}|\^\w)*"
    r"|\|[A-Za-z\\]+\|(?:\^\d+)?"
    r"|\d*[A-Za-z][A-Za-z0-9]*(?:\^\d+)+(?:[A-Za-z]+\^\d+)*"
    r")"
)

_DASH_CHARS = {"-", "–", "—", "−"}
Box = tuple[float, float, float, float]  # left, right, bottom, top


def instruction_parbox_cm(*, right_stage: bool = False) -> float:
    """TeX parbox width for captions and prose (composition-aware)."""
    if get_composition().name == "mobile":
        return _MOBILE_PARBOX_CM
    if right_stage:
        return _HALF_PARBOX_CM
    return _FULL_PARBOX_CM


def statement_parbox_cm() -> float:
    """TeX parbox width for full-frame problem statements."""
    name = get_composition().name
    if name == "mobile":
        return _MOBILE_PARBOX_CM
    if name == "web":
        return _STATEMENT_WEB_PARBOX_CM
    return _FULL_PARBOX_CM


def build_instruction(
    text: str,
    *,
    color: Any,
    font_size: int | None = None,
    max_width_cm: float | None = None,
    right_stage: bool = False,
    apply_composition_scale: bool = True,
) -> VMobject:
    """Wrapped Computer Modern paragraph with inline math; placement via StageConductor."""
    from manim import Tex

    body = format_instruction_body(text)
    if max_width_cm is not None:
        width_cm = max_width_cm
    else:
        width_cm = instruction_parbox_cm(right_stage=right_stage)
    if font_size is None:
        raw = _FONT_SIZE
    else:
        raw = int(font_size)
    size = scale_font(raw) if apply_composition_scale else raw
    return Tex(
        rf"\parbox{{{width_cm:.1f}cm}}{{\raggedright {body}}}",
        font_size=size,
        color=color,
    )


def format_instruction_body(text: str) -> str:
    """Turn teacher prose into a TeX fragment safe inside a ``\\parbox``."""
    s = " ".join(text.strip().split())
    if not s:
        return ""
    s = s.translate(str.maketrans({"²": "^2", "³": "^3", "⁴": "^4"}))
    s = s.replace("−", "-").replace("–", "-").replace("—", "-").replace("…", "...")
    s = re.sub(r"√\(([^)]*)\)", r"$\\sqrt{\1}$", s)
    s = s.replace("√", r"$\sqrt{}$")

    pieces: list[str] = []
    pos = 0
    for match in _DELIM_MATH.finditer(s):
        if match.start() > pos:
            pieces.append(_unicode_math_to_inline(s[pos : match.start()]))
        pieces.append(match.group(0))
        pos = match.end()
    if pos < len(s):
        pieces.append(_unicode_math_to_inline(s[pos:]))
    s = _merge_adjacent_math("".join(pieces))

    pieces = []
    pos = 0
    for match in _DELIM_MATH.finditer(s):
        if match.start() > pos:
            pieces.append(_mathify_text_segment(s[pos : match.start()]))
        pieces.append(_normalize_delimited_math(match.group(0)))
        pos = match.end()
    if pos < len(s):
        pieces.append(_mathify_text_segment(s[pos:]))
    return _merge_adjacent_math("".join(pieces))


def place_instruction(
    mob: VMobject,
    *,
    region: Region | None = None,
    pin_top: bool = True,
    right_stage: bool | None = None,
) -> None:
    """Fit the banner at the top of ``region`` (layout owns peer clearance)."""
    region = _resolve_region(region, right_stage)
    _place_instruction_top(mob, region)
    _clamp_in_frame(mob, region)


def play_set_instruction(
    scene,
    old: VMobject | None,
    text: str,
    *,
    color: Any,
    region: Region | None = None,
    pin_top: bool = True,
    right_stage: bool | None = None,
) -> VMobject:
    """Fade to a new instruction banner; returns the new mobject."""
    region = _resolve_region(region, right_stage)
    half = region.center[0] > 0.5 and get_composition().name != "mobile"
    new_mob = build_instruction(
        text,
        color=color,
        max_width_cm=instruction_parbox_cm(right_stage=half),
    )
    place_instruction(new_mob, region=region, pin_top=pin_top)
    if old is None:
        scene.play(
            FadeIn(new_mob),
            run_time=_CAPTION_ENTER_TIME,
            rate_func=rate_functions.smooth,
        )
        return new_mob
    scene.play(
        AnimationGroup(
            FadeOut(old),
            FadeIn(new_mob),
            lag_ratio=0.3,
        ),
        run_time=_CAPTION_CROSSFADE_TIME,
        rate_func=rate_functions.smooth,
    )
    return new_mob


def _resolve_region(region: Region | None, right_stage: bool | None) -> Region:
    if region is not None:
        return region
    if right_stage:
        from cinemath.render_engine.stage import right_active

        return right_active()
    return full_frame()


def _place_instruction_top(
    mob: VMobject,
    region: Region,
    max_w: float | None = None,
) -> None:
    _fit_in_region(mob, region)
    if max_w is not None:
        _fit_width(mob, max_w)
    y = region.top - _TOP_BUFF - float(mob.height) / 2
    mob.move_to(float(region.center[0]) * RIGHT + y * UP)


def _region_box(region: Region) -> Box:
    return (region.left, region.right, region.bottom, region.top)


def _unicode_math_to_inline(s: str) -> str:
    out: list[str] = []
    for ch in s:
        tex = unicode_math_char(ch)
        if tex is not None:
            out.append(f"${tex}$" if tex.startswith("\\") or tex == "-" else escape_latex_text(tex))
        elif ch in _DASH_CHARS and ch != "-":
            out.append("-")
        else:
            out.append(ch)
    return "".join(out)


def _mathify_text_segment(segment: str) -> str:
    if not segment:
        return ""
    parts: list[str] = []
    pos = 0
    for match in _MATH_TOKEN.finditer(segment):
        if match.start() > pos:
            parts.append(escape_latex_text(segment[pos : match.start()]))
        token = match.group(0)
        if token.startswith("\\"):
            parts.append(f"${token}$")
        else:
            parts.append(f"${_caret_braces(token)}$")
        pos = match.end()
    if pos < len(segment):
        parts.append(escape_latex_text(segment[pos:]))
    return "".join(parts)


def _normalize_delimited_math(chunk: str) -> str:
    if chunk.startswith("\\(") and chunk.endswith("\\)"):
        inner = chunk[2:-2]
        return f"${_caret_braces(inner)}$"
    if chunk.startswith("$") and chunk.endswith("$"):
        return f"${_caret_braces(chunk[1:-1])}$"
    return chunk


def _caret_braces(expr: str) -> str:
    return re.sub(r"\^(\d+)", r"^{\1}", expr)


def _merge_adjacent_math(s: str) -> str:
    def _join(match: re.Match[str]) -> str:
        left, sep, right = match.group(1), match.group(2), match.group(3)
        if re.search(r"\\[A-Za-z]+\s*$", left) and re.match(r"[A-Za-z]", right):
            return f"${left} {right}$"
        if sep and re.search(r"[A-Za-z0-9}]$", left) and re.match(r"[A-Za-z\\]", right):
            return f"${left} {right}$"
        return f"${left}{right}$"

    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"\$([^$]+)\$(\s*)\$([^$]+)\$", _join, s)
    return s


def _fit_width(mob: VMobject, max_w: float) -> None:
    w = float(mob.width)
    if w > max_w and w > 1e-6:
        mob.scale(max_w / w)


def _region_max_width(region: Region) -> float:
    return min(region.max_w, max(0.5, region.right - region.left))


def _region_max_height(region: Region) -> float:
    return min(region.max_h, max(0.5, region.top - region.bottom))


def _fit_in_region(mob: VMobject, region: Region) -> None:
    """Scale wrapped text down so it fits the layout region."""
    max_w = _region_max_width(region)
    max_h = _region_max_height(region)
    _fit_width(mob, max_w)
    h = float(mob.height)
    if h > max_h and h > 1e-6:
        mob.scale(max_h / h)
    _fit_width(mob, max_w)


def _clamp_in_frame(mob: VMobject, region: Region) -> None:
    _fit_in_region(mob, region)
    left_limit, right_limit, bottom_limit, top_limit = _region_box(region)

    if float(mob.get_right()[0]) > right_limit:
        _fit_in_region(mob, region)
        mob.set_x(float(region.center[0]))
        mob.to_edge(UP, buff=_TOP_BUFF)
        mob.set_x(float(region.center[0]))

    if float(mob.get_left()[0]) < left_limit:
        mob.shift(RIGHT * (left_limit - float(mob.get_left()[0])))

    if float(mob.get_top()[1]) > top_limit:
        mob.shift(DOWN * (float(mob.get_top()[1]) - top_limit))
        _fit_in_region(mob, region)

    if float(mob.get_bottom()[1]) < bottom_limit:
        mob.shift(UP * (bottom_limit - float(mob.get_bottom()[1])))
        _fit_in_region(mob, region)
