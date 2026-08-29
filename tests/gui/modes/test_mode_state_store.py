"""Tests for GUI mode state store invariants."""

from __future__ import annotations

import pytest

from chappy.core.editing_mode import EditingMode
from chappy.gui.modes import mode_state_store
from chappy.gui.modes.mode_state_store import ModeStateStore


class _StoredModeSettings:
    """Settings double returning a fixed stored mode value."""

    stored_current = "not-a-mode"

    def __init__(self, _organization: str, _application: str) -> None:
        """Accept QSettings constructor arguments."""

    def value(self, key: str, default: str) -> str:
        """Return the stored mode for the current mode key."""
        if key == "editing_mode/current":
            return self.stored_current
        return default

    def setValue(self, key: str, value: str) -> None:
        """Accept save requests."""


class _LegacyBrowseSettings(_StoredModeSettings):
    """Settings double simulating a pre-rename installation."""

    stored_current = "browse"


def test_invalid_stored_mode_falls_back_to_start(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown persisted mode values degrade to START instead of failing startup."""
    monkeypatch.setattr(mode_state_store, "QSettings", _StoredModeSettings)

    store = ModeStateStore()

    assert store.current_mode is EditingMode.START


def test_legacy_browse_mode_falls_back_to_start(monkeypatch: pytest.MonkeyPatch) -> None:
    """The pre-rename value "browse" restores to START without raising."""
    monkeypatch.setattr(mode_state_store, "QSettings", _LegacyBrowseSettings)

    store = ModeStateStore()

    assert store.current_mode is EditingMode.START
