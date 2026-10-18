"""Tiny helpers for building animation.json dicts from templates."""

from __future__ import annotations

from typing import Any


def script(problem: str, answer: str, steps: list[str], scenes: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": 1,
        "problem": problem,
        "answer": answer,
        "steps": steps,
        "scenes": scenes,
    }


def scene(
    sid: str,
    *,
    caption: str,
    objects: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    template: str,
    mode: str = "2d",
    pin: bool = True,
    separate_labels: bool = True,
) -> dict[str, Any]:
    return {
        "id": sid,
        "mode": mode,
        "caption": caption,
        "pin": pin,
        "separate_labels": separate_labels,
        "template": template,
        "objects": objects,
        "actions": actions,
    }


def math(oid: str, tex: str, at: str = "center", font_size: int = 40, color: str = "white") -> dict[str, Any]:
    return {"id": oid, "type": "math", "tex": tex, "at": at, "font_size": font_size, "color": color}


def prose(
    oid: str,
    content: str,
    at: str = "center",
    font_size: int = 28,
    color: str = "white",
) -> dict[str, Any]:
    return {
        "id": oid,
        "type": "prose",
        "content": content,
        "at": at,
        "font_size": font_size,
        "color": color,
    }


def text(oid: str, content: str, at: str = "center", font_size: int = 32, color: str = "white") -> dict[str, Any]:
    return {
        "id": oid,
        "type": "text",
        "content": content,
        "at": at,
        "font_size": font_size,
        "color": color,
    }


def write(*ids: str) -> dict[str, Any]:
    return {"op": "write", "targets": list(ids)}


def create(*ids: str) -> dict[str, Any]:
    return {"op": "create", "targets": list(ids)}


def fade_in(*ids: str) -> dict[str, Any]:
    return {"op": "fade_in", "targets": list(ids)}


def indicate(*ids: str) -> dict[str, Any]:
    return {"op": "indicate", "targets": list(ids)}


def box(*ids: str) -> dict[str, Any]:
    return {"op": "box", "targets": list(ids)}


def wait(seconds: float = 0.8) -> dict[str, Any]:
    return {"op": "wait", "seconds": seconds}


def move_camera(phi: float = 70, theta: float = -40, run_time: float = 1.0) -> dict[str, Any]:
    return {"op": "move_camera", "phi": phi, "theta": theta, "run_time": run_time}


def derive(frm: str, to: str, *, buff: float = 0.55) -> dict[str, Any]:
    """Commit: new line below ``frm``. Parent stays on screen at full opacity."""
    return {"op": "derive", "from": frm, "to": to, "buff": buff}


def advance(frm: str, to: str) -> dict[str, Any]:
    """Move a branch tip in place. ``frm`` is retired and does not reappear."""
    return {"op": "advance", "from": frm, "to": to}


def fork(frm: str, *to: str, buff: float = 0.75) -> dict[str, Any]:
    """Fan one equation into multiple child equations underneath it."""
    return {"op": "fork", "from": frm, "to": list(to), "buff": buff}


def merge(frm: list[str], to: str, *, buff: float = 0.7) -> dict[str, Any]:
    """Join branch tips into one equation centered under them."""
    return {"op": "merge", "from": list(frm), "to": to, "buff": buff}


def set_caption(text: str) -> dict[str, Any]:
    return {"op": "set_caption", "text": text}


def note(frm: str, to: str, *, buff: float = 0.42) -> dict[str, Any]:
    """Teacher instruction line in the equation tree (below ``frm``)."""
    return {"op": "note", "from": frm, "to": to, "buff": buff}


def fade_out(*ids: str) -> dict[str, Any]:
    return {"op": "fade_out", "targets": list(ids)}


def transform(frm: str, to: str) -> dict[str, Any]:
    """Morph / swipe one on-screen object into another."""
    return {"op": "transform", "from": frm, "to": to}
