"""Concrete fit/editor transition guard for the Analysis workspace."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QApplication

if TYPE_CHECKING:
    from collections.abc import Callable

    from PySide6.QtWidgets import QWidget


class AnalysisTransitionGuardAdapter:
    """Guard surface and top-level transitions against busy or invalid Detail state."""

    def __init__(self, *, fit_running: Callable[[], bool], detail_widget: QWidget) -> None:
        self._fit_running = fit_running
        self._detail_widget = detail_widget
        self._invalid_editor: QWidget | None = None

    def fit_running(self) -> bool:
        """Return live fit state at command execution time."""
        return self._fit_running()

    def commit_pending_editor(self) -> bool:
        """Commit the focused Detail editor before leaving its surface."""
        focused = QApplication.focusWidget()
        self._invalid_editor = None
        if focused is None or not self._detail_widget.isAncestorOf(focused):
            return True
        focused.clearFocus()
        QApplication.processEvents()
        if focused.hasFocus():
            self._invalid_editor = focused
            return False
        return True

    def focus_invalid_editor(self) -> None:
        """Restore focus to an editor that rejected its commit."""
        if self._invalid_editor is not None:
            self._invalid_editor.setFocus()


__all__ = ["AnalysisTransitionGuardAdapter"]
