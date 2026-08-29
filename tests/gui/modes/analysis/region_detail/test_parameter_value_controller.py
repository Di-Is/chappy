"""Tests for optimize parameter value controller."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass

import pytest

from chappy.application.history import ComponentParameterState
from chappy.application.optimize import OptimizeParameterMutationUseCase
from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.analysis import AnalysisRevision
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.components.base import Parameter
from chappy.core.components.tie_set import ParameterTieSet
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.modes.analysis.region_detail.parameters.parameter_value_controller import (
    OptimizeParameterValueController,
)


@dataclass(frozen=True, slots=True)
class _RecordedEdit:
    component_ids: list[str]
    param_name: str
    before_states: tuple[ComponentParameterState, ...]
    after_states: tuple[ComponentParameterState, ...]
    region_id: str | None


def _add_region(project: SpectroscopyProject, region_id: str) -> None:
    """Add one analysis-capable region with fresh lines."""
    line_id = f"line-{region_id}"
    project.absorption_lines[line_id] = AbsorptionLine(
        line_id=line_id,
        species="H I",
        rest_wavelength=1215.67,
        center_z=2.0,
        window_kms=100.0,
        multiplet_label="Ly alpha",
        transition_name="Ly alpha",
        oscillator_strength=0.4,
        gamma_value=1e8,
        region_id=region_id,
        needs_optimization=False,
    )
    project.absorption_regions[region_id] = AbsorptionRegion(
        region_id=region_id, line_ids=[line_id]
    )


class _Port:
    """Parameter value port test double."""

    def __init__(self) -> None:
        self.project = SpectroscopyProject()
        _add_region(self.project, "region-1")
        _add_region(self.project, "region-2")
        self.valid = True
        self.changed: list[tuple[str, float]] = []
        self.tree_refreshes: list[tuple[str, ...]] = []
        self.records: list[_RecordedEdit] = []
        self.region_id: str | None = "region-1"
        self.group_id: str | None = "group-1"
        self.fail_history = False
        self.fail_observer = False

    def value_mutation_project(self) -> SpectroscopyProject:
        """Return the active scientific project."""
        return self.project

    @contextlib.contextmanager
    def value_history_atomic_recording(self):
        """Provide a focused history rollback scope."""
        yield

    def validate_parameter_value(
        self, param_name: str, value: float, component: AbsorberComponent
    ) -> bool:
        """Return configured validation result."""
        _ = param_name, value, component
        return self.valid

    def emit_parameter_value_changed(self, param_name: str, value: float) -> None:
        """Record emitted parameter changes or inject observer failure."""
        if self.fail_observer:
            raise RuntimeError("injected parameter observer failure")
        self.changed.append((param_name, value))

    def refresh_parameter_tree_values(self, component_ids: tuple[str, ...]) -> None:
        """Record tree refreshes."""
        self.tree_refreshes.append(component_ids)

    def region_id_for_value_component(self, component: AbsorberComponent) -> str | None:
        """Return configured component region id."""
        _ = component
        return self.region_id

    def current_value_group_id(self) -> str | None:
        """Return configured current group id."""
        return self.group_id

    def record_value_parameter_edit(
        self,
        component_ids: list[str],
        param_name: str,
        before_states: tuple[ComponentParameterState, ...],
        after_states: tuple[ComponentParameterState, ...],
        region_id: str | None,
    ) -> None:
        """Record history edits or inject failure."""
        if self.fail_history:
            raise RuntimeError("injected parameter history failure")
        self.records.append(
            _RecordedEdit(component_ids, param_name, before_states, after_states, region_id)
        )


def _component(component_id: str = "component-1") -> AbsorberComponent:
    """Create a deterministic absorber component."""
    return AbsorberComponent(component_id=component_id, redshift=2.0, column_density=13.5)


def _controller(port: _Port) -> OptimizeParameterValueController:
    """Create a parameter value controller with production mutation rules."""
    return OptimizeParameterValueController(port=port, usecase=OptimizeParameterMutationUseCase())


def _state_value(state: ComponentParameterState, param_name: str) -> float:
    """Return a parameter value from a component history state."""
    for parameter in state.parameters:
        if parameter.name == param_name:
            return parameter.value
    raise AssertionError(f"Missing parameter state: {param_name}")


def test_apply_parameter_value_updates_all_analysis_regions_and_history() -> None:
    """A successful value edit must globally stale analysis and record history."""
    port = _Port()
    component = _component()

    assert _controller(port).apply_parameter_value(component, "redshift", 2.1) is True

    assert component.parameters["redshift"].value == 2.1
    assert port.changed == [("redshift", 2.1)]
    assert port.tree_refreshes == [(component.id,)]
    assert len(port.records) == 1
    record = port.records[0]
    assert record.component_ids == [component.id]
    assert _state_value(record.before_states[0], "redshift") == 2.0
    assert _state_value(record.after_states[0], "redshift") == 2.1
    assert all(
        state.current_revision == AnalysisRevision(1)
        for state in port.project.region_analysis_states()
    )
    assert all(line.needs_optimization for line in port.project.absorption_lines.values())


def test_shared_parameter_value_refreshes_every_tied_component_row() -> None:
    """A shared value edit should refresh every rendered tie-set member by ID."""
    port = _Port()
    first = _component("component-1")
    second = _component("component-2")
    tie_set = ParameterTieSet("z-1", mask=frozenset({"redshift"}), origin="user")
    tie_set.add_component(first)
    tie_set.add_component(second)

    assert _controller(port).apply_parameter_value(first, "redshift", 2.1) is True

    assert first.parameters["redshift"] is second.parameters["redshift"]
    assert second.parameters["redshift"].value == pytest.approx(2.1)
    assert port.tree_refreshes == [(first.id, second.id)]
    assert port.records[0].component_ids == [first.id, second.id]


def test_parameter_history_keeps_region_hint_without_local_invalidation() -> None:
    """The region hint remains history metadata while invalidation stays global."""
    port = _Port()
    port.region_id = None

    assert _controller(port).apply_parameter_value(_component(), "column_density", 14.0)

    assert port.records[0].region_id == "group-1"
    assert all(
        state.current_revision == AnalysisRevision(1)
        for state in port.project.region_analysis_states()
    )


def test_invalid_and_identical_values_are_no_change() -> None:
    """Rejected and identical values must not mutate history or revisions."""
    invalid_port = _Port()
    invalid_port.valid = False
    component = _component()
    assert _controller(invalid_port).apply_parameter_value(component, "redshift", 2.1) is False

    identical_port = _Port()
    assert _controller(identical_port).apply_parameter_value(component, "redshift", 2.0) is False

    for port in (invalid_port, identical_port):
        assert port.records == []
        assert all(
            state.current_revision == AnalysisRevision(0)
            for state in port.project.region_analysis_states()
        )


def test_parameter_history_failure_rolls_back_value_and_freshness() -> None:
    """A history failure must restore value, revisions, line flags, and modified."""
    port = _Port()
    port.fail_history = True
    component = _component()
    modified_before = port.project.modified

    with pytest.raises(RuntimeError, match="injected parameter history failure"):
        _controller(port).apply_parameter_value(component, "redshift", 2.1)

    assert component.parameters["redshift"].value == 2.0
    assert all(
        state.current_revision == AnalysisRevision(0)
        for state in port.project.region_analysis_states()
    )
    assert all(line.needs_optimization is False for line in port.project.absorption_lines.values())
    assert port.project.modified == modified_before


def test_parameter_observer_failure_keeps_committed_state() -> None:
    """A failed post-commit observer must not block later refresh actions."""
    port = _Port()
    port.fail_observer = True
    component = _component()

    assert _controller(port).apply_parameter_value(component, "redshift", 2.1) is True

    assert component.parameters["redshift"].value == 2.1
    assert port.tree_refreshes == [(component.id,)]
    assert all(
        state.current_revision == AnalysisRevision(1)
        for state in port.project.region_analysis_states()
    )


def test_covering_factor_is_initialized_without_render_time_mutation() -> None:
    """Covering factor initialization must only register the core default."""
    controller = _controller(_Port())
    component = _component()
    parameter = controller.ensure_covering_factor_parameter(component)

    assert parameter.fixed is True
    assert controller.is_parameter_initialized(parameter) is True
    parameter.fixed = False
    assert controller.ensure_covering_factor_parameter(component) is parameter
    assert parameter.fixed is False


def test_param_value_fails_fast_for_missing_required_parameter() -> None:
    """Missing required parameters should raise RuntimeError."""
    component = _component()
    del component.parameters["redshift"]

    with pytest.raises(RuntimeError, match="missing required parameter: redshift"):
        OptimizeParameterValueController.param_value(component, "redshift")


def test_mark_parameter_initialized_records_external_parameter() -> None:
    """External workflows can mark parameters as initialized."""
    controller = _controller(_Port())
    parameter = Parameter("covering_factor", 1.0)
    controller.mark_parameter_initialized(parameter)
    assert controller.is_parameter_initialized(parameter) is True
