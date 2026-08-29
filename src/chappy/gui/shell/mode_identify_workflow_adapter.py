"""Identify workflow adapter used by mode lifecycle objects."""

from __future__ import annotations

from typing import Protocol


class IdentifyWorkflowController(Protocol):
    """Identify coordinator operations required by identify mode."""

    def set_identify_active(self, active: bool) -> None:
        """Synchronize whether the Identify workflow is active."""
        ...


class IdentifyWorkflowWindow(Protocol):
    """Main-window subset required by the identify workflow adapter."""

    @property
    def identify_coordinator(self) -> IdentifyWorkflowController | None:
        """Return the identify coordinator when available."""
        ...


class ModeIdentifyWorkflowAdapter:
    """Apply identify-specific workflow state for mode lifecycle events."""

    def __init__(self, window: IdentifyWorkflowWindow) -> None:
        """Initialize the adapter.

        Args:
            window: Main-window-like object exposing the identify coordinator.
        """
        self._window = window

    def activate_identify_workflow(self) -> None:
        """Activate identify workflow state."""
        self._notify(active=True)

    def deactivate_identify_workflow(self) -> None:
        """Deactivate identify workflow state."""
        self._notify(active=False)

    def _notify(self, *, active: bool) -> None:
        """Forward mode-change semantics to the identify coordinator."""
        controller = self._window.identify_coordinator
        if controller is None:
            msg = "Identify workflow updates require an identify coordinator."
            raise RuntimeError(msg)
        controller.set_identify_active(active)
