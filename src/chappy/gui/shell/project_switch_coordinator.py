"""Coordinate project-switch side-effect ordering for the shell."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chappy.core.spectroscopy_project import SpectroscopyProject

ProjectSwitchCallback = Callable[["SpectroscopyProject | None"], None]


@dataclass(frozen=True, slots=True)
class ProjectSwitchPorts:
    """Operation-specific callbacks required for project switching."""

    clear_history: Callable[[], None]
    set_mode_project: ProjectSwitchCallback
    update_action_states: ProjectSwitchCallback
    set_view_project: ProjectSwitchCallback
    set_dock_project: ProjectSwitchCallback
    emit_project_changed: ProjectSwitchCallback


class ProjectSwitchCoordinator:
    """Apply project-switch side effects in a stable, testable order."""

    def __init__(self, ports: ProjectSwitchPorts) -> None:
        """Store project-switch callbacks.

        Args:
            ports: Ordered project-switch side-effect callbacks.
        """
        self._ports = ports

    def switch_project(self, project: SpectroscopyProject | None) -> None:
        """Run the shell project-switch workflow.

        Args:
            project: Project to activate, or None to clear the shell state.
        """
        self._ports.clear_history()
        self._ports.set_mode_project(project)
        self._ports.update_action_states(project)
        self._ports.set_view_project(project)
        self._ports.set_dock_project(project)
        self._ports.emit_project_changed(project)
