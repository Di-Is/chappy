"""Continuum visualization adapter used by mode lifecycle objects."""

from __future__ import annotations

from typing import Protocol


class ContinuumVisualizationController(Protocol):
    """Continuum coordinator operations required for mode changes."""

    def set_continuum_visible(self, visible: bool) -> None:
        """Update continuum visibility semantically."""
        ...


class ContinuumWindow(Protocol):
    """Main-window subset required by the continuum mode adapter."""

    @property
    def continuum_coordinator(self) -> ContinuumVisualizationController | None:
        """Return the continuum coordinator when available."""
        ...


class ModeContinuumAdapter:
    """Apply mode-specific continuum visualization state."""

    def __init__(self, window: ContinuumWindow) -> None:
        """Initialize the adapter.

        Args:
            window: Main-window-like object exposing the continuum coordinator.
        """
        self._window = window

    def show_continuum(self) -> None:
        """Show continuum visualization for continuum mode."""
        self._update(visible=True)

    def hide_continuum(self) -> None:
        """Hide continuum visualization for non-continuum modes."""
        self._update(visible=False)

    def _update(self, *, visible: bool) -> None:
        """Forward continuum visualization updates to the GUI coordinator."""
        controller = self._window.continuum_coordinator
        if controller is None:
            msg = "Continuum visualization requires a continuum coordinator."
            raise RuntimeError(msg)
        controller.set_continuum_visible(visible)
