"""Lifecycle boundary for continuum mode."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chappy.core.editing_mode import EditingMode

if TYPE_CHECKING:
    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.modes.common.lifecycle import ModeRefreshRequest
    from chappy.gui.modes.common.shell_ports import ModeContinuumPort, ModeLineOverlayPort


class ContinuumModeLifecycle:
    """Lifecycle object for continuum mode."""

    def __init__(
        self, line_overlay_port: ModeLineOverlayPort, continuum_port: ModeContinuumPort
    ) -> None:
        """Initialize the lifecycle.

        Args:
            line_overlay_port: Required line overlay adapter for continuum mode.
            continuum_port: Required continuum visualization adapter for continuum mode.
        """
        self.project: SpectroscopyProject | None = None
        self.active = False
        self.last_refresh: ModeRefreshRequest | None = None
        self._line_overlay_port = line_overlay_port
        self._continuum_port = continuum_port

    def set_project(self, project: SpectroscopyProject | None) -> None:
        """Set the active project.

        Args:
            project: Active project, or None when no project is open.
        """
        self.project = project

    def activate(self) -> None:
        """Activate continuum mode."""
        self.active = True
        self._clear_line_overlays()
        self._show_continuum()

    def deactivate(self) -> None:
        """Deactivate continuum mode."""
        self.active = False

    def refresh(self, request: ModeRefreshRequest) -> None:
        """Record a refresh request.

        Args:
            request: Refresh request for continuum mode.
        """
        if request.mode is not EditingMode.CONTINUUM:
            msg = "ContinuumModeLifecycle received a refresh for another mode"
            raise ValueError(msg)
        self.last_refresh = request
        self._clear_line_overlays()
        self._show_continuum()

    def _clear_line_overlays(self) -> None:
        """Clear line overlays."""
        self._line_overlay_port.clear_line_overlays()

    def _show_continuum(self) -> None:
        """Show continuum visualization for continuum mode."""
        self._continuum_port.show_continuum()
