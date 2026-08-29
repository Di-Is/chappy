"""Tests for main window close-event lifecycle behavior."""

from __future__ import annotations

from typing import cast

from PySide6.QtGui import QCloseEvent

from chappy.gui.shell.main_window import MainWindow


class _IgnoringWindowLifecycle:
    """Close-event lifecycle that cancels shutdown."""

    def handle_close_event(self, event: QCloseEvent) -> None:
        """Ignore the close event to simulate a cancelled shutdown prompt."""
        event.ignore()


class _MainWindowCloseEventHarness:
    """Minimal object carrying the attributes used by ``closeEvent``."""

    def __init__(self) -> None:
        """Initialize close-event collaborators."""
        self._window_lifecycle = _IgnoringWindowLifecycle()


def test_close_event_delegates_cancellation_to_window_lifecycle() -> None:
    """Keep the application running when the shutdown prompt is cancelled."""
    harness = _MainWindowCloseEventHarness()
    event = QCloseEvent()

    MainWindow.closeEvent(cast(MainWindow, harness), event)

    assert not event.isAccepted()
