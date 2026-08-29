"""Top-level lifecycle for the Analysis workspace."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chappy.core.editing_mode import EditingMode

if TYPE_CHECKING:
    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.modes.common.lifecycle import ModeRefreshRequest
    from chappy.gui.modes.common.shell_ports import ModeContinuumPort, ModeLineOverlayPort


class AnalysisLifecycleCoordinator:
    """Own Analysis enter, exit, and project changes, but never surface changes."""

    def __init__(
        self, line_overlay_port: ModeLineOverlayPort, continuum_port: ModeContinuumPort
    ) -> None:
        self.project: SpectroscopyProject | None = None
        self.active = False
        self.last_refresh: ModeRefreshRequest | None = None
        self._line_overlay_port = line_overlay_port
        self._continuum_port = continuum_port

    def set_project(self, project: SpectroscopyProject | None) -> None:
        """Set the project shared by all Analysis surfaces."""
        self.project = project

    def activate(self) -> None:
        """Enter Analysis once, independent of its current surface."""
        self.active = True
        self._apply_common_state()

    def deactivate(self) -> None:
        """Leave Analysis once."""
        self.active = False

    def refresh(self, request: ModeRefreshRequest) -> None:
        """Refresh top-level Analysis without changing the active surface."""
        if request.mode is not EditingMode.ANALYSIS:
            msg = "Analysis lifecycle received a refresh for another mode"
            raise ValueError(msg)
        self.last_refresh = request
        self._apply_common_state()

    def _apply_common_state(self) -> None:
        self._line_overlay_port.show_confirmed_line_overlays()
        self._continuum_port.hide_continuum()
