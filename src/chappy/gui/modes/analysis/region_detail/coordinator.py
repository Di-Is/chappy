"""Lifecycle signal coordinator for optimize mode."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from PySide6.QtCore import SignalInstance

    from chappy.gui.modes.analysis.region_detail.workflows.fit_workflow_controller import (
        FitResultRawPayload,
    )


class OptimizeEditorSignalPort(Protocol):
    """Optimize editor signals consumed by the mode coordinator."""

    fit_started: SignalInstance
    fit_completed: SignalInstance


class OptimizeModeCoordinatorPort(Protocol):
    """Optimize panel handoff methods used by the coordinator."""

    def handle_editor_fit_started(self) -> None:
        """Handle an editor fit-start signal."""
        ...

    def handle_editor_fit_completed(self, results: FitResultRawPayload) -> None:
        """Handle an editor fit-completed signal."""
        ...


class OptimizeModeCoordinator:
    """Coordinate optimize-mode signal routing and lifecycle handoff."""

    def __init__(
        self, *, panel: OptimizeModeCoordinatorPort, editor: OptimizeEditorSignalPort
    ) -> None:
        """Initialize the coordinator.

        Args:
            panel: Optimize panel handoff boundary.
            editor: Optimize editor signal boundary.
        """
        self._panel = panel
        self._editor = editor
        self._connected = False

    def connect(self) -> None:
        """Connect optimize-mode external signals exactly once."""
        if self._connected:
            return

        self._editor.fit_started.connect(self._panel.handle_editor_fit_started)
        self._editor.fit_completed.connect(self._panel.handle_editor_fit_completed)

        self._connected = True
