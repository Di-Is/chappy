"""Tests for identify workflow lifecycle transitions."""

from __future__ import annotations

from chappy.core.editing_mode import EditingMode
from chappy.core.identify_state import IdentifySessionState
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.modes.identify.workflow_lifecycle_controller import (
    IdentifyWorkflowLifecycleController,
    IdentifyWorkflowLifecyclePorts,
)


def test_mode_leave_clears_detection_overlay_preview_lock_and_cursor_preview() -> None:
    events: list[str] = []
    session = IdentifySessionState()
    controller = IdentifyWorkflowLifecycleController(
        IdentifyWorkflowLifecyclePorts(
            session_provider=lambda: session,
            session_resolver=lambda _project: session,
            project_setter=lambda _project: events.append("project_set"),
            session_setter=lambda _session: events.append("session_set"),
            velocity_workflow_reset_callback=lambda: events.append("velocity_reset"),
            detection_overlay_clear_callback=lambda: events.append("detection_clear"),
            cursor_preview_clear_callback=lambda: events.append("preview_clear"),
            preview_lock_enabled_provider=lambda: True,
            preview_lock_clear_callback=lambda: events.append("preview_lock_clear"),
            preview_reapply_callback=lambda: events.append("preview_reapply"),
            refresh_candidates_callback=lambda: events.append("refresh_candidates"),
            refresh_workflow_callback=lambda: events.append("refresh_workflow"),
        )
    )

    controller.on_mode_changed(EditingMode.ANALYSIS)

    assert events == ["detection_clear", "preview_lock_clear", "preview_clear"]


def test_mode_enter_refreshes_candidates_and_reapplies_preview() -> None:
    events: list[str] = []
    session = IdentifySessionState()
    controller = IdentifyWorkflowLifecycleController(
        IdentifyWorkflowLifecyclePorts(
            session_provider=lambda: session,
            session_resolver=lambda _project: session,
            project_setter=lambda _project: events.append("project_set"),
            session_setter=lambda _session: events.append("session_set"),
            velocity_workflow_reset_callback=lambda: events.append("velocity_reset"),
            detection_overlay_clear_callback=lambda: events.append("detection_clear"),
            cursor_preview_clear_callback=lambda: events.append("preview_clear"),
            preview_lock_enabled_provider=lambda: True,
            preview_lock_clear_callback=lambda: events.append("preview_lock_clear"),
            preview_reapply_callback=lambda: events.append("preview_reapply"),
            refresh_candidates_callback=lambda: events.append("refresh_candidates"),
            refresh_workflow_callback=lambda: events.append("refresh_workflow"),
        )
    )

    controller.on_mode_changed(EditingMode.IDENTIFY)

    assert events == ["refresh_candidates", "preview_reapply"]


def test_project_change_updates_session_resets_velocity_and_refreshes_panel() -> None:
    events: list[str] = []
    detached_session = IdentifySessionState()
    project = SpectroscopyProject()
    state = {"project": None, "session": detached_session}

    def set_project(value: SpectroscopyProject | None) -> None:
        state["project"] = value
        events.append("project_set")

    def set_session(value: IdentifySessionState) -> None:
        state["session"] = value
        events.append("session_set")

    controller = IdentifyWorkflowLifecycleController(
        IdentifyWorkflowLifecyclePorts(
            session_provider=lambda: state["session"],
            session_resolver=lambda value: (
                detached_session if value is None else value.identify_state
            ),
            project_setter=set_project,
            session_setter=set_session,
            velocity_workflow_reset_callback=lambda: events.append("velocity_reset"),
            detection_overlay_clear_callback=lambda: events.append("detection_clear"),
            cursor_preview_clear_callback=lambda: events.append("preview_clear"),
            preview_lock_enabled_provider=lambda: False,
            preview_lock_clear_callback=lambda: events.append("preview_lock_clear"),
            preview_reapply_callback=lambda: events.append("preview_reapply"),
            refresh_candidates_callback=lambda: events.append("refresh_candidates"),
            refresh_workflow_callback=lambda: events.append("refresh_workflow"),
        )
    )

    controller.handle_project_changed(project)

    assert state == {"project": project, "session": project.identify_state}
    assert events == [
        "project_set",
        "session_set",
        "velocity_reset",
        "preview_clear",
        "refresh_candidates",
        "refresh_workflow",
    ]
