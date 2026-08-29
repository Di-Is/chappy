"""Tests for typed model history application."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

import pytest

from chappy.application.history import (
    ComponentParameterState,
    HistoryApplyError,
    HistoryApplyErrorCode,
    HistoryRecorder,
    HistoryRefreshTarget,
    ModelComponentHistoryCommand,
    ModelComponentLinkSnapshot,
    ModelParameterEditCommand,
    NamedParameterState,
    component_parameter_state,
)
from chappy.application.history.snapshot_mapping import absorber_component_snapshot
from chappy.application.optimize import (
    AbsorberModelTopologyUseCase,
    DeleteOptimizeModelComponentsUseCase,
)
from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.analysis import (
    AnalysisArtifact,
    AnalysisRevision,
    FitSummary,
    RegionAnalysisState,
)
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.components.tie_set import ParameterTieSet
from chappy.core.history import CommandHistory, HistoryEvent, OperationId
from chappy.core.spectroscopy_project import SpectroscopyProject

from history_apply_fakes import FakeHistoryRefreshPort, build_usecase

if TYPE_CHECKING:
    from chappy.application.history.apply.usecase import HistoryApplyUseCase


class _Parameter:
    """Small parameter test double accepted by the model history applier."""

    def __init__(self) -> None:
        """Initialize parameter state."""
        self.value = 1.0
        self.min_val = 0.0
        self.max_val = 10.0
        self.fixed = False
        self.error = 0.5

    def set_value(self, value: float) -> None:
        """Set the parameter value."""
        self.value = value


class _Component:
    """Small component test double accepted by the model history applier."""

    def __init__(self) -> None:
        """Initialize component parameters."""
        self.parameters = {"redshift": _Parameter()}


class _Project:
    """Small project test double accepted by the model history applier."""

    def __init__(self) -> None:
        """Initialize project model and component lookup."""
        self.name = "History Apply Test"
        self.model = object()
        self.component = _Component()
        self.absorption_lines: dict[str, object] = {}
        self.removed_component_ids: list[str] = []

    def find_absorber_component(self, component_id: str) -> _Component | None:
        """Return the fake component for its expected ID."""
        if component_id == "comp-1":
            return self.component
        return None

    def remove_absorber_component(self, component: AbsorberComponent) -> bool:
        """Record component removal for model add undo tests."""
        self.removed_component_ids.append(component.id)
        return True


def _history(
    project: SpectroscopyProject | None, *, refresh_port: FakeHistoryRefreshPort | None = None
) -> tuple[CommandHistory, HistoryApplyUseCase, list[SpectroscopyProject | None]]:
    """Connect a real history stack to the model history handler.

    Returns the mutable holder alongside the stack so a test can clear the
    connected project mid-run, mirroring ``HistoryBridge.set_project(None)``.
    """
    holder: list[SpectroscopyProject | None] = [project]
    history = CommandHistory()
    usecase = build_usecase(
        project_provider=lambda: holder[0], refresh_port=refresh_port or FakeHistoryRefreshPort()
    )
    history.set_applier(usecase)
    return history, usecase, holder


def _component_state(value: float) -> ComponentParameterState:
    """Create one component parameter state."""
    return ComponentParameterState(
        component_id="comp-1",
        parameters=(
            NamedParameterState(
                name="redshift", value=value, vary=True, min_value=None, max_value=None, error=0.02
            ),
        ),
    )


def _scientific_parameter_project() -> SpectroscopyProject:
    """Build one capable region and a component at the command after-state."""
    project = SpectroscopyProject()
    component = AbsorberComponent(component_id="comp-1", redshift=2.0)
    project.model.add_component_storage(component)
    line = AbsorptionLine(
        line_id="line-1",
        species="C IV",
        rest_wavelength=1548.2,
        center_z=2.0,
        window_kms=100.0,
        multiplet_label="C IV",
        transition_name="1548",
        oscillator_strength=0.1,
        gamma_value=1e8,
        region_id="region-1",
        model_ids=[component.id],
    )
    line.needs_optimization = False
    project.load_absorption_state(
        regions={"region-1": AbsorptionRegion("region-1", line_ids=[line.line_id])},
        lines={line.line_id: line},
    )
    revision = AnalysisRevision(3)
    project.set_region_analysis_state(
        RegionAnalysisState(
            region_id="region-1",
            current_revision=revision,
            artifact=AnalysisArtifact(
                region_id="region-1",
                source_revision=revision,
                fit_summary=FitSummary(chi_squared=1.0),
            ),
        )
    )
    project.modified = datetime(2020, 1, 1, tzinfo=UTC)
    return project


def test_restore_component_parameters_restores_error() -> None:
    """Typed model restore should restore parameter uncertainty."""
    project = _Project()
    _history_stack, usecase, _holder = _history(cast("SpectroscopyProject", project))
    state = ComponentParameterState(
        component_id="comp-1",
        parameters=(
            NamedParameterState(
                name="redshift", value=2.0, vary=False, min_value=1.0, max_value=3.0, error=0.02
            ),
        ),
    )

    usecase._model_applier.restore_component_parameters((state,))

    parameter = project.component.parameters["redshift"]
    assert parameter.value == 2.0
    assert parameter.fixed is True
    assert parameter.error == 0.02


def test_parameter_history_rebuilds_storage_and_refreshes_after_commit() -> None:
    """Parameter history should rebuild once in storage and refresh only after commit."""
    project = _scientific_parameter_project()
    refresh_port = FakeHistoryRefreshPort()
    history, _usecase, _holder = _history(project, refresh_port=refresh_port)
    event = HistoryEvent(
        command=ModelParameterEditCommand(
            param_name="redshift",
            component_ids=("comp-1",),
            before=(_component_state(1.0),),
            after=(_component_state(2.0),),
            region_id="region-1",
        )
    )

    assert history.push(event)
    assert history.undo().success

    assert project.require_absorber_component("comp-1").parameters["redshift"].value == 1.0
    state = project.region_analysis_state("region-1")
    assert state is not None
    assert state.current_revision == AnalysisRevision(4)
    assert state.artifact is not None
    assert state.artifact.source_revision == AnalysisRevision(3)
    assert project.absorption_lines["line-1"].needs_optimization
    assert refresh_port.region_ids_for(HistoryRefreshTarget.OPTIMIZE_PANEL) == [None]

    assert history.redo().success
    assert project.require_absorber_component("comp-1").parameters["redshift"].value == 2.0
    state = project.region_analysis_state("region-1")
    assert state is not None
    assert state.current_revision == AnalysisRevision(5)
    assert state.artifact is not None
    assert state.artifact.source_revision == AnalysisRevision(3)
    assert refresh_port.region_ids_for(HistoryRefreshTarget.OPTIMIZE_PANEL) == [None, None]


def test_public_undo_returns_missing_target_failure_and_keeps_history_stack() -> None:
    """A stale Undo target is a typed target failure with no project connected."""
    history, _usecase, _holder = _history(None)
    event = HistoryEvent(
        command=ModelParameterEditCommand(
            param_name="redshift",
            component_ids=("comp-1",),
            before=(_component_state(1.0),),
            after=(_component_state(2.0),),
            region_id="region-1",
        )
    )

    assert history.push(event)

    with pytest.raises(HistoryApplyError) as exc_info:
        history.undo()

    assert exc_info.value.error_code is HistoryApplyErrorCode.TARGET_NOT_FOUND
    assert history.can_undo
    assert not history.can_redo


def test_public_redo_returns_missing_target_failure_and_keeps_history_stack() -> None:
    """A stale Redo target is a typed target failure once the project disconnects."""
    project = _scientific_parameter_project()
    history, _usecase, holder = _history(project)
    event = HistoryEvent(
        command=ModelParameterEditCommand(
            param_name="redshift",
            component_ids=("comp-1",),
            before=(_component_state(1.0),),
            after=(_component_state(2.0),),
            region_id="region-1",
        )
    )
    assert history.push(event)
    assert history.undo().success
    holder[0] = None

    with pytest.raises(HistoryApplyError) as exc_info:
        history.redo()

    assert exc_info.value.error_code is HistoryApplyErrorCode.TARGET_NOT_FOUND
    assert not history.can_undo
    assert history.can_redo


def test_parameter_history_no_change_does_not_increment_revision() -> None:
    """An already-restored target must advance history without stale-state churn."""
    project = _scientific_parameter_project()
    project.require_absorber_component("comp-1").parameters["redshift"].error = 0.02
    refresh_port = FakeHistoryRefreshPort()
    history, _usecase, _holder = _history(project, refresh_port=refresh_port)
    event = HistoryEvent(
        command=ModelParameterEditCommand(
            param_name="redshift",
            component_ids=("comp-1",),
            before=(_component_state(2.0),),
            after=(_component_state(1.0),),
            region_id="region-1",
        )
    )
    assert history.push(event)
    before_state = project.region_analysis_state("region-1")
    before_modified = project.modified

    assert history.undo().success

    assert project.region_analysis_state("region-1") == before_state
    assert project.modified == before_modified
    assert not project.absorption_lines["line-1"].needs_optimization
    assert refresh_port.calls == []


def test_parameter_history_rejects_out_of_bounds_target_without_clamping() -> None:
    """Invalid target snapshots must fail before mutation instead of clamping."""
    project = _scientific_parameter_project()
    history, _usecase, _holder = _history(project)
    invalid = ComponentParameterState(
        component_id="comp-1",
        parameters=(
            NamedParameterState(
                name="redshift", value=4.0, vary=True, min_value=0.0, max_value=3.0, error=0.1
            ),
        ),
    )
    event = HistoryEvent(
        command=ModelParameterEditCommand(
            param_name="redshift",
            component_ids=("comp-1",),
            before=(invalid,),
            after=(_component_state(2.0),),
            region_id="region-1",
        )
    )
    assert history.push(event)
    before_project_state = project.region_analysis_states()
    before_history = history.get_state()

    with pytest.raises(HistoryApplyError) as exc_info:
        history.undo()

    assert exc_info.value.error_code is HistoryApplyErrorCode.INVALID_STATE
    parameter = project.require_absorber_component("comp-1").parameters["redshift"]
    assert parameter.value == 2.0
    assert project.region_analysis_states() == before_project_state
    assert history.get_state() == before_history


def test_parameter_history_rollback_restores_runtime_and_freshness_on_rebuild_failure() -> None:
    """Derived-model failure must restore parameters, artifacts, flags, and history."""
    project = _scientific_parameter_project()
    history, _usecase, _holder = _history(project)
    event = HistoryEvent(
        command=ModelParameterEditCommand(
            param_name="redshift",
            component_ids=("comp-1",),
            before=(_component_state(1.0),),
            after=(_component_state(2.0),),
            region_id="region-1",
        )
    )
    assert history.push(event)
    before_states = project.region_analysis_states()
    before_modified = project.modified
    before_history = history.get_state()

    with (
        patch.object(
            project.model,
            "rebuild_model_storage",
            side_effect=RuntimeError("derived rebuild failed"),
        ),
        pytest.raises(RuntimeError, match="derived rebuild failed"),
    ):
        history.undo()

    parameter = project.require_absorber_component("comp-1").parameters["redshift"]
    assert parameter.value == 2.0
    assert parameter.error == 0.0
    assert project.region_analysis_states() == before_states
    assert not project.absorption_lines["line-1"].needs_optimization
    assert project.modified == before_modified
    assert history.get_state() == before_history


def test_parameter_history_preserves_tied_parameter_identity_and_exact_state() -> None:
    """Shared parameters must be restored once without breaking object identity."""
    project = _scientific_parameter_project()
    first = project.require_absorber_component("comp-1")
    second = AbsorberComponent(component_id="comp-2", redshift=2.0)
    project.model.add_component_storage(second)
    tie_set = ParameterTieSet("shared-z", mask=frozenset({"redshift"}), origin="user")
    tie_set.add_component(first)
    tie_set.add_component(second)
    project.model.add_tie_set(tie_set)
    shared = first.parameters["redshift"]
    assert second.parameters["redshift"] is shared
    shared.min_val = 0.0
    shared.max_val = 4.0
    shared.set_value(1.0)
    shared.fixed = False
    shared.error = 0.1
    before = (component_parameter_state(first), component_parameter_state(second))
    shared.min_val = -0.1
    shared.max_val = 5.0
    shared.set_value(2.0)
    shared.fixed = True
    shared.error = 0.2
    after = (component_parameter_state(first), component_parameter_state(second))
    history, _usecase, _holder = _history(project)
    event = HistoryEvent(
        command=ModelParameterEditCommand(
            param_name="redshift",
            component_ids=(first.id, second.id),
            before=before,
            after=after,
            region_id="region-1",
        )
    )
    assert history.push(event)

    assert history.undo().success
    assert first.parameters["redshift"] is shared
    assert second.parameters["redshift"] is shared
    assert (shared.value, shared.min_val, shared.max_val, shared.fixed, shared.error) == (
        1.0,
        0.0,
        4.0,
        False,
        0.1,
    )

    assert history.redo().success
    assert first.parameters["redshift"] is shared
    assert second.parameters["redshift"] is shared
    assert (shared.value, shared.min_val, shared.max_val, shared.fixed, shared.error) == (
        2.0,
        -0.1,
        5.0,
        True,
        0.2,
    )


def test_parameter_history_gui_observer_failure_keeps_commit() -> None:
    """Post-commit GUI failure must not restore science or the Undo stack."""
    project = _scientific_parameter_project()
    refresh_port = FakeHistoryRefreshPort(
        fail_targets=frozenset({HistoryRefreshTarget.OPTIMIZE_PANEL})
    )
    history, _usecase, _holder = _history(project, refresh_port=refresh_port)
    event = HistoryEvent(
        command=ModelParameterEditCommand(
            param_name="redshift",
            component_ids=("comp-1",),
            before=(_component_state(1.0),),
            after=(_component_state(2.0),),
            region_id="region-1",
        )
    )
    assert history.push(event)

    assert history.undo().success

    assert project.require_absorber_component("comp-1").parameters["redshift"].value == 1.0
    state = project.region_analysis_state("region-1")
    assert state is not None
    assert state.current_revision == AnalysisRevision(4)
    assert history.can_redo
    assert not history.can_undo


def test_record_model_add_pushes_typed_command_that_undo_removes_component() -> None:
    """Model add recording should undo through the typed model command path."""
    project = _scientific_parameter_project()
    component = project.require_absorber_component("comp-1")
    history, _usecase, _holder = _history(project)
    artifact = project.region_analysis_state("region-1").artifact  # type: ignore[union-attr]
    assert artifact is not None

    recorder = HistoryRecorder(history, lambda: project)
    recorder.record_model_add({"line-1": component}, [])
    result = history.undo()

    assert result.success
    assert project.find_absorber_component("comp-1") is None
    assert project.absorption_lines["line-1"].model_ids == []
    assert project.absorption_lines["line-1"].needs_optimization
    state = project.region_analysis_state("region-1")
    assert state is not None and state.current_revision == AnalysisRevision(4)
    assert state.artifact is artifact

    assert history.redo().success
    assert project.find_absorber_component("comp-1") is not None
    assert project.absorption_lines["line-1"].model_ids == ["comp-1"]
    state = project.region_analysis_state("region-1")
    assert state is not None and state.current_revision == AnalysisRevision(5)
    assert state.artifact is artifact


def test_bulk_tied_model_delete_undo_redo_restores_order_topology_and_freshness() -> None:
    """Bulk deletion history rebuilds tied components and exact line order globally."""
    project = _scientific_parameter_project()
    first = project.require_absorber_component("comp-1")
    second = AbsorberComponent(component_id="comp-2", redshift=2.0)
    third = AbsorberComponent(component_id="comp-3", redshift=2.0)
    project.model.add_component_storage(second)
    project.model.add_component_storage(third)
    project.absorption_lines["line-1"].model_ids[:] = [first.id, second.id, third.id]
    tie_set = ParameterTieSet("bulk-tie", mask=frozenset({"redshift"}), origin="user")
    tie_set.add_component(first)
    tie_set.add_component(second)
    project.model.add_tie_set(tie_set)
    history_snapshot = AbsorberModelTopologyUseCase().capture_deletion_history(
        project, (first, second)
    )
    assert DeleteOptimizeModelComponentsUseCase().delete_components(project, (first, second))
    history, _usecase, _holder = _history(project)
    recorder = HistoryRecorder(history, lambda: project)
    recorder.record_model_delete_snapshot(history_snapshot)
    artifact = project.region_analysis_state("region-1").artifact  # type: ignore[union-attr]
    assert artifact is not None

    assert history.undo().success
    restored_first = project.require_absorber_component(first.id)
    restored_second = project.require_absorber_component(second.id)
    assert tuple(component.id for component in project.model.components) == (
        first.id,
        second.id,
        third.id,
    )
    assert project.absorption_lines["line-1"].model_ids == [first.id, second.id, third.id]
    restored_ties = tuple(project.model.iter_tie_sets())
    assert len(restored_ties) == 1
    assert restored_first.parameters["redshift"] is restored_second.parameters["redshift"]
    state = project.region_analysis_state("region-1")
    assert state is not None and state.current_revision == AnalysisRevision(4)
    assert state.artifact is artifact

    assert history.redo().success
    assert project.find_absorber_component(first.id) is None
    assert project.find_absorber_component(second.id) is None
    assert project.model.components == [third]
    assert project.absorption_lines["line-1"].model_ids == [third.id]
    assert tuple(project.model.iter_tie_sets()) == ()
    state = project.region_analysis_state("region-1")
    assert state is not None and state.current_revision == AnalysisRevision(5)
    assert state.artifact is artifact


def test_model_component_history_rejects_undeclared_extra_line_link_before_mutation() -> None:
    """An extra runtime link prevents removing a component through an incomplete command."""
    project = _scientific_parameter_project()
    component = project.require_absorber_component("comp-1")
    extra_line = AbsorptionLine(
        line_id="line-extra",
        species="C IV",
        rest_wavelength=1550.0,
        center_z=2.0,
        window_kms=100.0,
        multiplet_label="C IV",
        transition_name="1550",
        oscillator_strength=0.1,
        gamma_value=1e8,
        region_id="region-extra",
        model_ids=[component.id],
    )
    project.absorption_lines[extra_line.line_id] = extra_line
    project.absorption_regions["region-extra"] = AbsorptionRegion(
        "region-extra", line_ids=[extra_line.line_id]
    )
    history, _usecase, _holder = _history(project)
    command = ModelComponentHistoryCommand(
        op_id=OperationId.MODEL_ADD,
        components=(absorber_component_snapshot(component),),
        component_indices=(0,),
        links=(ModelComponentLinkSnapshot("line-1", component.id, 0),),
        tie_sets_before=(),
        tie_set_indices_before=(),
        tie_sets_after=(),
        tie_set_indices_after=(),
    )
    assert history.push(HistoryEvent(command=command))
    order_before = tuple(project.model.components)
    states_before = project.stored_region_analysis_states_for_transaction()
    history_before = history.get_state()

    with pytest.raises(HistoryApplyError, match="source topology does not match"):
        history.undo()

    assert tuple(project.model.components) == order_before
    assert project.model.get_component_by_id(component.id) is component
    assert project.absorption_lines["line-1"].model_ids == [component.id]
    assert project.absorption_lines[extra_line.line_id].model_ids == [component.id]
    assert project.stored_region_analysis_states_for_transaction() == states_before
    assert history.get_state() == history_before


def test_model_component_exact_target_no_change_is_fully_inert() -> None:
    """An already-absent add Undo target does not stale global analysis."""
    project = _scientific_parameter_project()
    target = AbsorberComponent(component_id="comp-2", redshift=2.0)
    history, _usecase, _holder = _history(project)
    command = ModelComponentHistoryCommand(
        op_id=OperationId.MODEL_ADD,
        components=(absorber_component_snapshot(target),),
        component_indices=(1,),
        links=(ModelComponentLinkSnapshot("line-1", target.id, 1),),
        tie_sets_before=(),
        tie_set_indices_before=(),
        tie_sets_after=(),
        tie_set_indices_after=(),
    )
    assert history.push(HistoryEvent(command=command))
    states_before = project.stored_region_analysis_states_for_transaction()
    modified_before = project.modified

    assert history.undo().success

    assert project.stored_region_analysis_states_for_transaction() == states_before
    assert project.modified == modified_before
    assert not project.absorption_lines["line-1"].needs_optimization


def test_model_component_rebuild_failure_restores_exact_tie_identity_and_stack() -> None:
    """Topology rollback retains component, tie, shared parameter, and subscription identities."""
    project = _scientific_parameter_project()
    first = project.require_absorber_component("comp-1")
    second = AbsorberComponent(component_id="comp-2", redshift=2.0)
    project.model.add_component_storage(second)
    second_line = AbsorptionLine(
        line_id="line-2",
        species="C IV",
        rest_wavelength=1550.0,
        center_z=2.0,
        window_kms=100.0,
        multiplet_label="C IV",
        transition_name="1550",
        oscillator_strength=0.1,
        gamma_value=1e8,
        region_id="region-1",
        model_ids=[second.id],
    )
    project.absorption_lines[second_line.line_id] = second_line
    project.absorption_regions["region-1"].line_ids.append(second_line.line_id)
    tie_set = ParameterTieSet("rollback-tie", mask=frozenset({"redshift"}), origin="user")
    tie_set.add_component(first)
    tie_set.add_component(second)
    project.model.add_tie_set(tie_set)
    shared = first.parameters["redshift"]
    history, _usecase, _holder = _history(project)
    recorder = HistoryRecorder(history, lambda: project)
    recorder.record_model_add({"line-1": first, second_line.line_id: second}, (tie_set,))
    order_before = tuple(project.model.components)
    states_before = project.stored_region_analysis_states_for_transaction()
    modified_before = project.modified
    history_before = history.get_state()

    with (
        patch.object(
            project.model,
            "rebuild_model_storage",
            side_effect=RuntimeError("component rebuild failed"),
        ),
        pytest.raises(RuntimeError, match="component rebuild failed"),
    ):
        history.undo()

    assert tuple(project.model.components) == order_before
    assert project.model.get_component_by_id(first.id) is first
    assert project.model.get_component_by_id(second.id) is second
    assert tuple(project.model.iter_tie_sets()) == (tie_set,)
    assert first.tie_set is tie_set and second.tie_set is tie_set
    assert first.parameters["redshift"] is shared
    assert second.parameters["redshift"] is shared
    assert project.absorption_lines["line-1"].model_ids == [first.id]
    assert project.absorption_lines[second_line.line_id].model_ids == [second.id]
    assert project.stored_region_analysis_states_for_transaction() == states_before
    assert project.modified == modified_before
    assert history.get_state() == history_before
    received: list[object] = []
    project.model.events.subscribe(received.append)
    first.notify_changed()
    assert len(received) == 1
