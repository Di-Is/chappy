"""Tests for project-switch ordering in the GUI shell."""

from __future__ import annotations

from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.shell.project_switch_coordinator import (
    ProjectSwitchCoordinator,
    ProjectSwitchPorts,
)


def test_project_switch_coordinator_applies_side_effects_in_stable_order() -> None:
    """Project switching should keep the shell side-effect order fixed."""
    calls: list[str] = []
    project = SpectroscopyProject(name="ordered")

    def _record(name: str):
        def _callback(_project: SpectroscopyProject | None = None) -> None:
            calls.append(name)

        return _callback

    coordinator = ProjectSwitchCoordinator(
        ProjectSwitchPorts(
            clear_history=lambda: calls.append("history_clear"),
            set_mode_project=_record("mode_shell_project"),
            update_action_states=_record("action_state_update"),
            set_view_project=_record("view_stack_project"),
            set_dock_project=_record("dock_coordinator_project"),
            emit_project_changed=_record("project_changed_signal"),
        )
    )

    coordinator.switch_project(project)

    assert calls == [
        "history_clear",
        "mode_shell_project",
        "action_state_update",
        "view_stack_project",
        "dock_coordinator_project",
        "project_changed_signal",
    ]
