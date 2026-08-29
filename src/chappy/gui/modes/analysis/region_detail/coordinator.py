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


class OptimizeModeStateSignalPort(Protocol):
    """Mode state signals consumed by the optimize coordinator."""

    group_removed: SignalInstance


class OptimizeModeCoordinatorPort(Protocol):
    """Optimize panel handoff methods used by the coordinator."""

    def handle_editor_fit_started(self) -> None:
        """Handle an editor fit-start signal."""
        ...

    def handle_editor_fit_completed(self, results: FitResultRawPayload) -> None:
        """Handle an editor fit-completed signal."""
        ...

    def handle_mode_group_removed(self, group_name: str) -> None:
        """Handle a removed group notification."""
        ...


class OptimizeModeCoordinator:
    """Coordinate optimize-mode signal routing and lifecycle handoff."""

    def __init__(
        self,
        *,
        panel: OptimizeModeCoordinatorPort,
        editor: OptimizeEditorSignalPort,
        mode_state: OptimizeModeStateSignalPort | None = None,
    ) -> None:
        """Initialize the coordinator.

        Args:
            panel: Optimize panel handoff boundary.
            editor: Optimize editor signal boundary.
            mode_state: Optional mode state signal boundary.
        """
        self._panel = panel
        self._editor = editor
        self._mode_state = mode_state
        self._connected = False

    def connect(self) -> None:
        """Connect optimize-mode external signals exactly once."""
        if self._connected:
            return

        self._editor.fit_started.connect(self._panel.handle_editor_fit_started)
        self._editor.fit_completed.connect(self._panel.handle_editor_fit_completed)

        if self._mode_state is not None:
            self._mode_state.group_removed.connect(self._panel.handle_mode_group_removed)

        self._connected = True
