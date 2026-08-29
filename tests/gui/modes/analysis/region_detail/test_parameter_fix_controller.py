"""Tests for optimize parameter fixed-state controller."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass

import pytest

from chappy.application.history import ComponentParameterState
from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.analysis import AnalysisRevision
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.components.base import Parameter
from chappy.core.components.tie_set import ParameterTieSet
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.modes.analysis.region_detail.parameters.parameter_fix_controller import (
    OptimizeParameterFixController,
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
    """Parameter-fix port test double."""

    def __init__(self) -> None:
        self.project = SpectroscopyProject()
        _add_region(self.project, "region-1")
        _add_region(self.project, "region-2")
        self.initialized_parameters: list[Parameter] = []
        self.records: list[_RecordedEdit] = []
        self.styles_refresh_count = 0
        self.dialog_refresh_count = 0
        self.fail_history = False
        self.fail_dialog_refresh = False

    def fix_mutation_project(self) -> SpectroscopyProject:
        """Return the active scientific project."""
        return self.project

    @contextlib.contextmanager
    def fix_history_atomic_recording(self):
        """Provide a focused history rollback scope."""
        yield

    def mark_fix_parameter_initialized(self, parameter: Parameter) -> None:
        """Record initialized parameters."""
        self.initialized_parameters.append(parameter)

    def region_id_for_fix_component(self, component: AbsorberComponent) -> str | None:
        """Return a deterministic region id."""
        return f"region:{component.id}"

    def current_fix_group_id(self) -> str | None:
        """Return a deterministic current Analysis region ID."""
        return "active-region"

    def record_fix_parameter_edit(
        self,
        component_ids: list[str],
        param_name: str,
        before_states: tuple[ComponentParameterState, ...],
        after_states: tuple[ComponentParameterState, ...],
        region_id: str | None,
    ) -> None:
        """Record a parameter edit."""
        if self.fail_history:
            raise RuntimeError("injected fixed history failure")
        self.records.append(
            _RecordedEdit(component_ids, param_name, before_states, after_states, region_id)
        )

    def refresh_fix_parameter_styles(self) -> None:
        """Record style refreshes."""
        self.styles_refresh_count += 1

    def refresh_fix_parameter_dialog(self) -> None:
        """Record dialog refreshes."""
        if self.fail_dialog_refresh:
            raise RuntimeError("injected fixed observer failure")
        self.dialog_refresh_count += 1


def _controller(port: _Port) -> OptimizeParameterFixController:
    """Return a fixed-state controller for tests."""
    return OptimizeParameterFixController(port=port)


def _component(component_id: str) -> AbsorberComponent:
    """Return a deterministic absorber component."""
    return AbsorberComponent(component_id=component_id, redshift=2.0)


def test_set_fixed_state_records_single_component_edit() -> None:
    """Controller should set fixed state and record a single component edit."""
    port = _Port()
    component = _component("component-1")

    _controller(port).set_fixed_state(component, "redshift", True)

    assert component.parameters["redshift"].fixed is True
    assert len(port.records) == 1
    assert port.records[0].component_ids == [component.id]
    assert port.records[0].param_name == "redshift"
    assert port.records[0].region_id == f"region:{component.id}"
    assert all(
        state.current_revision == AnalysisRevision(1)
        for state in port.project.region_analysis_states()
    )
    assert all(line.needs_optimization for line in port.project.absorption_lines.values())


def test_set_fixed_state_for_components_deduplicates_multiplet_group() -> None:
    """Controller should update a multiplet only once for duplicated selections."""
    port = _Port()
    first = _component("component-1")
    second = _component("component-2")
    tie_set = ParameterTieSet("multiplet-1")
    tie_set.add_component(first)
    tie_set.add_component(second)

    _controller(port).set_fixed_state_for_components((first, second), "redshift", True)

    assert first.parameters["redshift"].fixed is True
    assert second.parameters["redshift"].fixed is True
    assert len(port.records) == 1
    assert port.records[0].component_ids == [first.id, second.id]


def test_handle_fix_action_records_one_bulk_history_entry() -> None:
    """Controller should record one aggregate history entry for bulk toggles."""
    port = _Port()
    first = _component("component-1")
    second = _component("component-2")

    _controller(port).handle_fix_action_for_components([first, second], "redshift", True)

    assert first.parameters["redshift"].fixed is True
    assert second.parameters["redshift"].fixed is True
    assert len(port.records) == 1
    assert port.records[0].component_ids == [first.id, second.id]
    assert port.records[0].region_id == "active-region"
    assert port.styles_refresh_count == 1
    assert port.dialog_refresh_count == 1


def test_handle_fix_action_no_change_skips_post_commit_ui_notifications() -> None:
    """An identical context-menu fixed state should not refresh styles or dialogs."""
    port = _Port()
    component = _component("component-1")

    _controller(port).handle_fix_action_for_components([component], "redshift", False)

    assert port.records == []
    assert port.styles_refresh_count == 0
    assert port.dialog_refresh_count == 0


def test_set_fixed_state_fixes_masked_parameter_for_all_members() -> None:
    """Fixing a masked parameter on a partial-mask tie set should fix every member."""
    port = _Port()
    first = _component("component-1")
    second = _component("component-2")
    tie_set = ParameterTieSet("z-b-1", mask=frozenset({"redshift", "b_parameter"}))
    tie_set.add_component(first)
    tie_set.add_component(second)

    _controller(port).set_fixed_state(first, "redshift", True)

    assert first.parameters["redshift"].fixed is True
    assert second.parameters["redshift"].fixed is True
    assert len(port.records) == 1
    assert port.records[0].component_ids == [first.id, second.id]


def test_set_fixed_state_keeps_unmasked_parameter_per_component() -> None:
    """Fixing an unmasked parameter should only affect the edited component."""
    port = _Port()
    first = _component("component-1")
    second = _component("component-2")
    tie_set = ParameterTieSet("z-b-1", mask=frozenset({"redshift", "b_parameter"}))
    tie_set.add_component(first)
    tie_set.add_component(second)

    _controller(port).set_fixed_state(first, "column_density", True)

    assert first.parameters["column_density"].fixed is True
    assert second.parameters["column_density"].fixed is False
    assert len(port.records) == 1
    assert port.records[0].component_ids == [first.id]


def test_resolve_shared_fix_target_returns_sole_tie_set() -> None:
    """A single fully-masked tie set covering the selection should be returned."""
    first = _component("component-1")
    second = _component("component-2")
    tie_set = ParameterTieSet("full-1")
    tie_set.add_component(first)
    tie_set.add_component(second)

    result = OptimizeParameterFixController.resolve_shared_fix_target((first, second), "redshift")

    assert result is tie_set


def test_resolve_shared_fix_target_returns_none_for_unmasked_parameter() -> None:
    """A parameter outside the tie set mask should not resolve a shared target."""
    first = _component("component-1")
    second = _component("component-2")
    tie_set = ParameterTieSet("z-1", mask=frozenset({"redshift"}))
    tie_set.add_component(first)
    tie_set.add_component(second)

    result = OptimizeParameterFixController.resolve_shared_fix_target(
        (first, second), "column_density"
    )

    assert result is None


def test_resolve_shared_fix_target_returns_none_for_mixed_tie_sets() -> None:
    """Selections spanning more than one qualifying tie set should not resolve."""
    first = _component("component-1")
    second = _component("component-2")
    third = _component("component-3")
    fourth = _component("component-4")
    tie_set_a = ParameterTieSet("full-a")
    tie_set_a.add_component(first)
    tie_set_a.add_component(second)
    tie_set_b = ParameterTieSet("full-b")
    tie_set_b.add_component(third)
    tie_set_b.add_component(fourth)

    result = OptimizeParameterFixController.resolve_shared_fix_target((first, third), "redshift")

    assert result is None


def test_resolve_shared_fix_target_returns_none_for_untied_selection() -> None:
    """A selection with no tied components should not resolve a shared target."""
    first = _component("component-1")
    second = _component("component-2")

    result = OptimizeParameterFixController.resolve_shared_fix_target((first, second), "redshift")

    assert result is None


def test_resolve_shared_fix_target_returns_none_for_partially_tied_selection() -> None:
    """Mixing a tied and an untied component should fall back to no shared target."""
    first = _component("component-1")
    second = _component("component-2")
    untied = _component("component-3")
    tie_set = ParameterTieSet("full-1")
    tie_set.add_component(first)
    tie_set.add_component(second)

    result = OptimizeParameterFixController.resolve_shared_fix_target(
        (first, second, untied), "redshift"
    )

    assert result is None


def test_set_fixed_state_for_components_processes_unmasked_parameter_individually() -> None:
    """Bulk fixed-state toggles should record one atomic command."""
    port = _Port()
    first = _component("component-1")
    second = _component("component-2")
    tie_set = ParameterTieSet("z-b-1", mask=frozenset({"redshift", "b_parameter"}))
    tie_set.add_component(first)
    tie_set.add_component(second)

    _controller(port).set_fixed_state_for_components((first, second), "column_density", True)

    assert first.parameters["column_density"].fixed is True
    assert second.parameters["column_density"].fixed is True
    assert len(port.records) == 1
    assert port.records[0].component_ids == [first.id, second.id]


def test_identical_fixed_state_is_no_change() -> None:
    """Submitting an identical fixed state must not invalidate or record history."""
    port = _Port()
    component = _component("component-1")

    impact = _controller(port).set_fixed_state(component, "redshift", False)

    assert impact.changed is False
    assert port.records == []
    assert all(
        state.current_revision == AnalysisRevision(0)
        for state in port.project.region_analysis_states()
    )


def test_fixed_history_failure_rolls_back_parameter_and_freshness() -> None:
    """A failed fixed-state history record must restore the full transaction."""
    port = _Port()
    port.fail_history = True
    component = _component("component-1")
    modified_before = port.project.modified

    with pytest.raises(RuntimeError, match="injected fixed history failure"):
        _controller(port).set_fixed_state(component, "redshift", True)

    assert component.parameters["redshift"].fixed is False
    assert all(
        state.current_revision == AnalysisRevision(0)
        for state in port.project.region_analysis_states()
    )
    assert all(line.needs_optimization is False for line in port.project.absorption_lines.values())
    assert port.project.modified == modified_before


def test_fixed_observer_failure_keeps_committed_state() -> None:
    """A post-commit dialog refresh failure must not escape or revert state."""
    port = _Port()
    port.fail_dialog_refresh = True
    component = _component("component-1")

    _controller(port).handle_fix_action_for_components([component], "redshift", True)

    assert component.parameters["redshift"].fixed is True
    assert port.styles_refresh_count == 1
    assert port.dialog_refresh_count == 0
    assert all(
        state.current_revision == AnalysisRevision(1)
        for state in port.project.region_analysis_states()
    )
