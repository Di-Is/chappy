"""Tests for optimize mask workflow controller."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

import pytest
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

from chappy.application.optimize import (
    CreateMaskRequest,
    MaskMutationKind,
    MaskMutationUseCase,
    RemoveMaskRequest,
)
from chappy.application.history import MaskDefinitionSnapshot
from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.masking import MaskDefinition
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.modes.analysis.region_detail.mask.mask_panel import OptimizeMaskPanel
from chappy.gui.modes.analysis.region_detail.mask.mask_panel_adapter import (
    OptimizeMaskPanelAdapter,
)
from chappy.gui.modes.analysis.region_detail.mask.mask_workflow_controller import (
    OptimizeMaskWorkflowController,
)
from chappy.presentation.interaction.interaction_contracts import (
    InteractionChannel,
    InteractionId,
    InteractionPhase,
    InteractionStateSnapshot,
    MaskSelectionContext,
    MaskSelectionRequest,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(name="qapp")
def fixture_qapp() -> QApplication:
    """Provide a QApplication instance for Qt widgets."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _Port:
    """Mask workflow port test double."""

    def __init__(self) -> None:
        self.group_id: str | None = "group-1"
        self.velocity_active = False
        self.interaction_active = False
        self.available: bool | None = None
        self.expanded_count = 0
        self.velocity_warning_count = 0
        self.missing_group_warning_count = 0
        self.cancel_requested_count = 0
        self.active_mask_id: str | None = None
        self.focus_changes: list[str | None] = []
        self.fail_focus_change = False
        self.fail_active_sync = False
        self.analysis_refresh_count = 0
        self.requests: list[MaskSelectionRequest] = []
        self.rendered_masks: list[MaskDefinition] = []
        self.rendered_active_mask_id: str | None = None

    def current_mask_group_id(self) -> str | None:
        """Return the selected group identifier."""
        return self.group_id

    def show_mask_group_masks(
        self, masks: list[MaskDefinition], active_mask_id: str | None
    ) -> None:
        """Record rendered masks."""
        self.rendered_masks = masks
        self.rendered_active_mask_id = active_mask_id

    def set_mask_panel_available(self, available: bool) -> None:
        """Record panel availability."""
        self.available = available

    def expand_mask_panel(self) -> None:
        """Record expansion requests."""
        self.expanded_count += 1

    def set_mask_interaction_active(self, active: bool) -> None:
        """Record interaction activity."""
        self.interaction_active = active

    def is_mask_interaction_active(self) -> bool:
        """Return recorded interaction activity."""
        return self.interaction_active

    def is_velocity_plot_active(self) -> bool:
        """Return configured velocity state."""
        return self.velocity_active

    def show_mask_velocity_disabled_message(self) -> None:
        """Record velocity warnings."""
        self.velocity_warning_count += 1

    def show_mask_group_missing_message(self) -> None:
        """Record missing group warnings."""
        self.missing_group_warning_count += 1

    def emit_mask_selection_request(self, request: MaskSelectionRequest) -> None:
        """Record emitted selection requests."""
        self.requests.append(request)

    def emit_mask_focus_changed(self, mask_id: str | None) -> None:
        """Record focus changes."""
        if self.fail_focus_change:
            raise RuntimeError("injected mask focus failure")
        self.focus_changes.append(mask_id)

    def emit_mask_cancel_requested(self) -> None:
        """Record cancel requests."""
        self.cancel_requested_count += 1

    def refresh_mask_analysis_state(self) -> None:
        """Record post-commit analysis-view refreshes."""
        self.analysis_refresh_count += 1

    def sync_active_mask_id(self, mask_id: str | None) -> None:
        """Record active mask synchronization."""
        if self.fail_active_sync:
            raise RuntimeError("injected mask sync failure")
        self.active_mask_id = mask_id


class _History:
    """Atomic forward-history recorder for mask workflow tests."""

    def __init__(self) -> None:
        self.kinds: list[MaskMutationKind] = []

    @contextmanager
    def atomic_recording(self) -> Iterator[None]:
        before = list(self.kinds)
        try:
            yield
        except Exception:
            self.kinds = before
            raise

    def record_mask_mutation(
        self,
        *,
        kind: MaskMutationKind,
        mask_id: str,
        before: MaskDefinitionSnapshot | None,
        after: MaskDefinitionSnapshot | None,
        before_index: int | None,
        after_index: int | None,
        affected_region_ids: tuple[str, ...],
    ) -> None:
        _ = mask_id, before, after, before_index, after_index, affected_region_ids
        self.kinds.append(kind)


def _project() -> SpectroscopyProject:
    """Create one analysis-capable mask project."""
    project = SpectroscopyProject()
    project.absorption_lines["line-1"] = AbsorptionLine(
        line_id="line-1",
        species="C IV",
        rest_wavelength=1548.2,
        center_z=2.0,
        window_kms=100.0,
        multiplet_label="C IV",
        transition_name="1548",
        oscillator_strength=0.1,
        gamma_value=1e8,
        region_id="group-1",
    )
    project.absorption_regions["group-1"] = AbsorptionRegion(
        region_id="group-1", line_ids=["line-1"]
    )
    return project


def _controller(qapp: QApplication, port: _Port) -> OptimizeMaskWorkflowController:
    """Create a controller with concrete mask mutation adapter."""
    assert qapp is not None
    mask_panel = OptimizeMaskPanel()
    adapter = OptimizeMaskPanelAdapter(mask_panel)
    return OptimizeMaskWorkflowController(
        port=port,
        mask_adapter=adapter,
        usecase=MaskMutationUseCase(),
        history=_History(),
        event_parent=QObject(),
    )


def _mask(identifier: str, group_id: str = "group-1") -> MaskDefinition:
    """Create a deterministic mask definition."""
    return MaskDefinition.from_range(100.0, 110.0, identifier=identifier).with_group_id(group_id)


def _snapshot(
    context: MaskSelectionContext | None, *, phase: InteractionPhase = InteractionPhase.IDLE
) -> InteractionStateSnapshot[MaskSelectionContext]:
    """Create a mask selection snapshot."""
    return InteractionStateSnapshot(
        interaction_id=InteractionId("mask-test"),
        channel=InteractionChannel.MASK_SELECTION,
        phase=phase,
        context=context,
    )


def test_attach_model_renders_masks_for_current_group(qapp: QApplication) -> None:
    """Attaching a model should render masks filtered by the current group."""
    port = _Port()
    controller = _controller(qapp, port)
    project = _project()
    project.absorption_lines["line-2"] = AbsorptionLine(
        line_id="line-2",
        species="Si IV",
        rest_wavelength=1393.8,
        center_z=2.0,
        window_kms=100.0,
        multiplet_label="Si IV",
        transition_name="1393",
        oscillator_strength=0.1,
        gamma_value=1e8,
        region_id="group-2",
    )
    project.absorption_regions["group-2"] = AbsorptionRegion(
        region_id="group-2", line_ids=["line-2"]
    )
    first = project.model.add_mask_definition(_mask("mask-1"))
    project.model.add_mask_definition(_mask("mask-2", group_id="group-2"))

    controller.attach_project(project)

    assert port.rendered_masks == [first]
    assert port.rendered_active_mask_id is None


def test_request_add_mask_emits_create_request(qapp: QApplication) -> None:
    """Add requests should arm mask selection for the current Analysis region."""
    port = _Port()
    controller = _controller(qapp, port)
    controller.attach_project(_project())

    controller.request_add_mask()

    assert port.expanded_count == 1
    assert port.interaction_active is True
    assert len(port.requests) == 1
    request = port.requests[0]
    assert request.selection_mode == "create"
    assert request.group_id == "group-1"
    assert request.mask_id is None


def test_handle_selection_snapshot_commits_mask(qapp: QApplication) -> None:
    """Committed idle snapshots should upsert masks and invalidate the group."""
    port = _Port()
    controller = _controller(qapp, port)
    project = _project()
    controller.attach_project(project)
    result_mask = _mask("mask-1")
    context = MaskSelectionContext(
        selection_mode="create",
        mask_id=result_mask.identifier,
        group_id="group-1",
        start_pos=100.0,
        current_pos=110.0,
        end_pos=110.0,
        initial_range=None,
        excluded_ranges=None,
        result_mask=result_mask,
        cancel_reason=None,
    )

    controller.handle_selection_snapshot(_snapshot(context))

    assert project.model.mask_definitions == (project.model.find_mask("mask-1"),)
    assert port.active_mask_id == "mask-1"
    assert port.focus_changes == ["mask-1"]
    assert port.analysis_refresh_count == 1
    assert port.interaction_active is False


def test_handle_selection_snapshot_cancel_resets_interaction(qapp: QApplication) -> None:
    """Cancelled snapshots should reset active selection without mutating masks."""
    port = _Port()
    controller = _controller(qapp, port)
    project = _project()
    controller.attach_project(project)
    port.interaction_active = True

    controller.handle_selection_snapshot(_snapshot(None, phase=InteractionPhase.CANCELLED))

    assert port.interaction_active is False
    assert project.model.mask_definitions == ()


def test_update_panel_state_cancels_active_interaction_without_regions(qapp: QApplication) -> None:
    """Disabling mask availability should cancel active interaction exactly once."""
    port = _Port()
    controller = _controller(qapp, port)
    port.interaction_active = True

    controller.update_panel_state(has_regions=False)

    assert port.available is False
    assert port.interaction_active is False
    assert port.cancel_requested_count == 1


def test_removing_non_active_mask_preserves_current_focus(qapp: QApplication) -> None:
    """Deleting another mask must not clear the user's current mask focus."""
    project = _project()
    active = project.model.add_mask_definition(_mask("mask-active"))
    other = project.model.add_mask_definition(_mask("mask-other"))
    port = _Port()
    controller = _controller(qapp, port)
    controller.attach_project(project)
    controller.select_mask(active.identifier)
    port.focus_changes.clear()

    controller.apply_mutation(RemoveMaskRequest(mask_id=other.identifier))

    assert controller.active_mask_id == active.identifier
    assert port.active_mask_id == active.identifier
    assert port.focus_changes == []
    assert project.model.find_mask(other.identifier) is None


def test_removing_active_mask_clears_focus(qapp: QApplication) -> None:
    """Deleting the focused mask clears focus exactly once after commit."""
    project = _project()
    active = project.model.add_mask_definition(_mask("mask-active"))
    port = _Port()
    controller = _controller(qapp, port)
    controller.attach_project(project)
    controller.select_mask(active.identifier)
    port.focus_changes.clear()

    controller.apply_mutation(RemoveMaskRequest(mask_id=active.identifier))

    assert controller.active_mask_id is None
    assert port.active_mask_id is None
    assert port.focus_changes == [None]


def test_post_commit_notify_failure_keeps_science_and_active_state(qapp: QApplication) -> None:
    """An isolated observer failure cannot block mask focus or later listeners."""
    project = _project()
    port = _Port()
    controller = _controller(qapp, port)
    controller.attach_project(project)
    created = _mask("mask-created")

    def fail_observer(change_set: object) -> None:
        _ = change_set
        raise RuntimeError("mask notify failed")

    project.model.events.subscribe(fail_observer)
    later_events: list[object] = []
    project.model.events.subscribe(later_events.append)
    controller.apply_mutation(CreateMaskRequest(mask=created))

    assert project.model.find_mask(created.identifier) is not None
    state = project.region_analysis_state("group-1")
    assert state is not None and state.current_revision.value == 1
    assert controller.active_mask_id == created.identifier
    assert port.active_mask_id == created.identifier
    assert len(later_events) == 1


def test_post_commit_focus_failure_does_not_block_later_mask_actions(qapp: QApplication) -> None:
    """A failed focus signal must not block panel expansion or analysis refresh."""
    project = _project()
    port = _Port()
    port.fail_focus_change = True
    controller = _controller(qapp, port)
    controller.attach_project(project)
    created = _mask("mask-created")

    controller.apply_mutation(CreateMaskRequest(mask=created))

    assert project.model.find_mask(created.identifier) is not None
    assert controller.active_mask_id == created.identifier
    assert port.expanded_count == 1
    assert port.analysis_refresh_count == 1


def test_post_commit_sync_failure_does_not_block_later_mask_actions(qapp: QApplication) -> None:
    """A failed legacy sync must keep internal focus and run later actions."""
    project = _project()
    port = _Port()
    controller = _controller(qapp, port)
    controller.attach_project(project)
    port.fail_active_sync = True
    created = _mask("mask-created")

    controller.apply_mutation(CreateMaskRequest(mask=created))

    assert project.model.find_mask(created.identifier) is not None
    assert controller.active_mask_id == created.identifier
    assert port.active_mask_id is None
    assert port.focus_changes == [created.identifier]
    assert port.expanded_count == 1
    assert port.analysis_refresh_count == 1
