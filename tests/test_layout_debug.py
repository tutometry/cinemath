"""Layout debug overlay toggle."""

from __future__ import annotations

import pytest

from cinemath.render_engine.layout_debug import layout_debug_enabled, layout_debug_labels


def test_layout_debug_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CINEMATH_LAYOUT_DEBUG", raising=False)
    assert not layout_debug_enabled()


def test_layout_debug_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CINEMATH_LAYOUT_DEBUG", "1")
    assert layout_debug_enabled()
    monkeypatch.setenv("CINEMATH_LAYOUT_DEBUG_LABELS", "yes")
    assert layout_debug_labels()
