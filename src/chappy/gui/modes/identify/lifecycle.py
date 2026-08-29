"""Lifecycle boundary for identify mode."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chappy.core.editing_mode import EditingMode

if TYPE_CHECKING:
    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.modes.common.lifecycle import ModeRefreshRequest
    from chappy.gui.modes.common.shell_ports import (
        ModeContinuumPort,
        ModeIdentifyWorkflowPort,
        ModeLineOverlayPort,
    )


class IdentifyModeLifecycle:
    """Lifecycle object for identify mode."""

    def __init__(
        self,
        line_overlay_port: ModeLineOverlayPort,
        continuum_port: ModeContinuumPort,
        identify_workflow_port: ModeIdentifyWorkflowPort,
    ) -> None:
        """Initialize the lifecycle.

        Args:
            line_overlay_port: Required line overlay adapter for identify mode.
            continuum_port: Required continuum visualization adapter for identify mode.
            identify_workflow_port: Required identify workflow adapter.
        """
        self.project: SpectroscopyProject | None = None
        self.active = False
        self.last_refresh: ModeRefreshRequest | None = None
        self._line_overlay_port = line_overlay_port
        self._continuum_port = continuum_port
        self._identify_workflow_port = identify_workflow_port

    def set_project(self, project: SpectroscopyProject | None) -> None:
        """Set the active project.

        Args:
            project: Active project, or None when no project is open.
        """
        self.project = project

    def activate(self) -> None:
        """Activate identify mode."""
        self.active = True
        self._show_line_overlays()
        self._hide_continuum()
        self._activate_identify_workflow()

    def deactivate(self) -> None:
        """Deactivate identify mode."""
        self.active = False
        self._deactivate_identify_workflow()

    def refresh(self, request: ModeRefreshRequest) -> None:
        """Record a refresh request.

        Args:
            request: Refresh request for identify mode.
        """
        if request.mode is not EditingMode.IDENTIFY:
            msg = "IdentifyModeLifecycle received a refresh for another mode"
            raise ValueError(msg)
        self.last_refresh = request
        self._show_line_overlays()
        self._hide_continuum()
        self._activate_identify_workflow()

    def _show_line_overlays(self) -> None:
        """Display identify-mode line overlays."""
        self._line_overlay_port.show_identify_line_overlays()

    def _hide_continuum(self) -> None:
        """Hide continuum visualization outside continuum mode."""
        self._continuum_port.hide_continuum()

    def _activate_identify_workflow(self) -> None:
        """Activate identify workflow state through the adapter."""
        self._identify_workflow_port.activate_identify_workflow()

    def _deactivate_identify_workflow(self) -> None:
        """Deactivate identify workflow state through the adapter."""
        self._identify_workflow_port.deactivate_identify_workflow()
