"""Handle identify mode and project lifecycle transitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from chappy.core.editing_mode import EditingMode

if TYPE_CHECKING:
    from collections.abc import Callable

    from chappy.core.identify_state import IdentifySessionState
    from chappy.core.spectroscopy_project import SpectroscopyProject


@dataclass(frozen=True, slots=True)
class IdentifyWorkflowLifecyclePorts:
    """Callbacks required for identify lifecycle transitions."""

    session_provider: Callable[[], IdentifySessionState]
    session_resolver: Callable[[SpectroscopyProject | None], IdentifySessionState]
    project_setter: Callable[[SpectroscopyProject | None], None]
    session_setter: Callable[[IdentifySessionState], None]
    velocity_workflow_reset_callback: Callable[[], None]
    detection_overlay_clear_callback: Callable[[], None]
    cursor_preview_clear_callback: Callable[[], None]
    preview_lock_enabled_provider: Callable[[], bool]
    preview_lock_clear_callback: Callable[[], None]
    preview_reapply_callback: Callable[[], None]
    refresh_candidates_callback: Callable[[], None]
    refresh_workflow_callback: Callable[[], None]


class IdentifyWorkflowLifecycleController:
    """Coordinate side effects for identify mode and project transitions."""

    def __init__(self, ports: IdentifyWorkflowLifecyclePorts) -> None:
        """Initialize the controller."""
        self._ports = ports

    def on_mode_changed(self, mode: EditingMode) -> None:
        """Synchronise identify workflow state with the active editing mode."""
        if mode == EditingMode.IDENTIFY:
            self._ports.refresh_candidates_callback()
            if self._ports.preview_lock_enabled_provider():
                self._ports.preview_reapply_callback()
            return

        self._ports.detection_overlay_clear_callback()
        if self._ports.preview_lock_enabled_provider():
            self._ports.preview_lock_clear_callback()
        self._ports.cursor_preview_clear_callback()

    def handle_project_changed(self, project: SpectroscopyProject | None) -> None:
        """Synchronise identify workflow state with the active project."""
        self._ports.project_setter(project)
        self._ports.session_setter(self._ports.session_resolver(project))
        self._ports.velocity_workflow_reset_callback()
        self._ports.cursor_preview_clear_callback()
        self._ports.refresh_candidates_callback()
        self._ports.refresh_workflow_callback()
