"""Tests for optimize component deletion controller."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass

import pytest

from chappy.application.optimize import ModelDeletionHistorySnapshot
from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.analysis import AnalysisRevision
from chappy.core.change_set import ChangeSet
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.components.continuum import ContinuumComponent
from chappy.core.components.tie_set import ParameterTieSet
from chappy.core.events import ComponentChanged
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.modes.analysis.region_detail.parameters.parameter_delete_controller import (
    OptimizeParameterDeleteController,
)


@dataclass(frozen=True, slots=True)
class _RecordedDelete:
    snapshot: ModelDeletionHistorySnapshot


class _Port:
    """Delete-port test double."""

    def __init__(self) -> None:
        self.records: list[_RecordedDelete] = []
        self.fail_record = False
        self.atomic_entries = 0

    def record_delete_components(self, snapshot: ModelDeletionHistorySnapshot) -> None:
        """Record deletion snapshots."""
        if self.fail_record:
            raise RuntimeError("injected delete history failure")
        self.records.append(_RecordedDelete(snapshot))

    @contextlib.contextmanager
    def delete_history_atomic_recording(self):
        """Record one atomic history boundary."""
        self.atomic_entries += 1
        yield


def _line(line_id: str, component_id: str, *, needs_optimization: bool = True) -> AbsorptionLine:
    """Return a minimal absorption line linked to a component."""
    return AbsorptionLine(
        line_id=line_id,
        species="H I",
        rest_wavelength=1215.67,
        center_z=2.0,
        window_kms=150.0,
        region_id="region-1",
        multiplet_label="",
        transition_name="Ly alpha",
        oscillator_strength=0.1,
        gamma_value=1e8,
        model_ids=[component_id],
        needs_optimization=needs_optimization,
    )


def _component(component_id: str) -> AbsorberComponent:
    """Return a deterministic absorber component."""
    return AbsorberComponent(component_id=component_id, redshift=2.0)


def test_delete_components_detaches_lines_and_records_topology() -> None:
    """Controller records exact links while freshness remains a transaction concern."""
    project = SpectroscopyProject()
    component = _component("component-1")
    project.model.add_component(component)
    line = _line("line-1", component.id, needs_optimization=True)
    project.absorption_lines[line.line_id] = line
    port = _Port()

    OptimizeParameterDeleteController(port=port).delete_components(project, [component])

    assert component not in project.model.components
    assert line.model_ids == []
    assert line.needs_optimization is False
    assert len(port.records) == 1
    snapshot = port.records[0].snapshot
    assert tuple(item.component_id for item in snapshot.components) == (component.id,)
    assert tuple((item.line_id, item.component_id, item.index) for item in snapshot.links) == (
        (line.line_id, component.id, 0),
    )
    assert snapshot.tie_set_indices == ()
    assert port.atomic_entries == 1


def test_delete_components_cleans_removed_multiplet_group() -> None:
    """Controller should remove empty tie sets from the model."""
    project = SpectroscopyProject()
    first = _component("component-1")
    second = _component("component-2")
    tie_set = ParameterTieSet("multiplet-1")
    tie_set.add_component(first)
    tie_set.add_component(second)
    project.model.add_component(first)
    project.model.add_component(second)
    project.model.add_tie_set(tie_set)
    first_line = _line("line-1", first.id)
    second_line = _line("line-2", second.id)
    project.absorption_lines = {first_line.line_id: first_line, second_line.line_id: second_line}
    port = _Port()

    OptimizeParameterDeleteController(port=port).delete_components(project, [first, second])

    assert first not in project.model.components
    assert second not in project.model.components
    assert first.tie_set is None
    assert second.tie_set is None
    assert tie_set not in tuple(project.model.iter_tie_sets())
    assert first_line.model_ids == []
    assert second_line.model_ids == []


def test_delete_dissolving_one_tie_set_keeps_a_sibling_sharing_its_tie_id() -> None:
    """Dissolving one tie set must not remove another that shares the same tie_id."""
    project = SpectroscopyProject()
    first_a = _component("component-1")
    first_b = _component("component-2")
    second_a = _component("component-3")
    second_b = _component("component-4")
    first = ParameterTieSet("multiplet-1")
    first.add_component(first_a)
    first.add_component(first_b)
    second = ParameterTieSet("multiplet-1")
    second.add_component(second_a)
    second.add_component(second_b)
    for component in (first_a, first_b, second_a, second_b):
        project.model.add_component(component)
    project.model.add_tie_set(first)
    project.model.add_tie_set(second)
    port = _Port()

    OptimizeParameterDeleteController(port=port).delete_components(project, [first_a, first_b])

    assert first not in tuple(project.model.iter_tie_sets())
    assert second in tuple(project.model.iter_tie_sets())
    assert second_a.tie_set is second
    assert second_b.tie_set is second
    assert second_a.parameters["redshift"] is second_b.parameters["redshift"]


def test_delete_of_only_direct_component_dissolves_external_parent() -> None:
    """Deleting the sole direct member leaves one participation unit, dissolving the parent."""
    project = SpectroscopyProject()
    inner_a = _component("component-1")
    inner_b = _component("component-2")
    direct = _component("component-3")
    for component in (inner_a, inner_b, direct):
        project.model.add_component(component)
    inner = ParameterTieSet("inner")
    inner.add_component(inner_a)
    inner.add_component(inner_b)
    outer = ParameterTieSet("outer", mask=frozenset({"redshift"}), origin="user")
    outer.add_component(direct)
    outer.attach_tie_set(inner)
    project.model.add_tie_set(inner)
    project.model.add_tie_set(outer)
    port = _Port()

    OptimizeParameterDeleteController(port=port).delete_components(project, [direct])

    assert direct not in project.model.components
    assert outer not in tuple(project.model.iter_tie_sets())
    assert inner in tuple(project.model.iter_tie_sets())
    assert inner.parent_tie is None
    assert inner_a.tie_set is inner
    assert inner_b.tie_set is inner
    assert inner_a.parameters["redshift"] is inner.shared_parameters["redshift"]


def test_delete_components_does_not_cascade_through_user_tie_set() -> None:
    """Deleting one member of a user tie set must not delete the other member."""
    project = SpectroscopyProject()
    first = _component("component-1")
    second = _component("component-2")
    tie_set = ParameterTieSet("user-1", mask=frozenset({"redshift"}), origin="user")
    tie_set.add_component(first)
    tie_set.add_component(second)
    project.model.add_component(first)
    project.model.add_component(second)
    project.model.add_tie_set(tie_set)
    port = _Port()

    OptimizeParameterDeleteController(port=port).delete_components(project, [first])

    assert first not in project.model.components
    assert second in project.model.components
    assert second.tie_set is None
    assert tie_set not in tuple(project.model.iter_tie_sets())


def test_delete_history_failure_restores_exact_component_and_tie_topology() -> None:
    """A history failure restores component links, shared parameters, and freshness."""
    project = SpectroscopyProject()
    first = _component("component-1")
    second = _component("component-2")
    left_continuum = ContinuumComponent(name="left-continuum")
    right_continuum = ContinuumComponent(name="right-continuum")
    tie_set = ParameterTieSet("user-1", mask=frozenset({"redshift"}), origin="user")
    tie_set.add_component(first)
    tie_set.add_component(second)
    project.model.add_component(left_continuum)
    project.model.add_component(first)
    project.model.add_component(right_continuum)
    project.model.add_component(second)
    project.model.add_tie_set(tie_set)
    component_order_before = tuple(component.id for component in project.model.components)
    line = _line("line-1", first.id, needs_optimization=False)
    line.model_ids.append(second.id)
    project.absorption_lines[line.line_id] = line
    project.absorption_regions["region-1"] = AbsorptionRegion(
        region_id="region-1", line_ids=[line.line_id]
    )
    port = _Port()
    port.fail_record = True

    with pytest.raises(RuntimeError, match="injected delete history failure"):
        OptimizeParameterDeleteController(port=port).delete_components(project, [first])

    assert first in project.model.components
    assert second in project.model.components
    assert tuple(component.id for component in project.model.components) == component_order_before
    assert project.model.get_component_by_id(first.id) is first
    assert line.model_ids == [first.id, second.id]
    restored_tie = first.tie_set
    assert isinstance(restored_tie, ParameterTieSet)
    assert second.tie_set is restored_tie
    assert first.parameters["redshift"] is second.parameters["redshift"]
    assert project.region_analysis_state("region-1").current_revision == AnalysisRevision(0)
    assert line.needs_optimization is False

    forwarded_changes: list[ChangeSet] = []
    project.model.events.subscribe(forwarded_changes.append)
    first.notify_changed()
    assert len(forwarded_changes) == 1
    assert forwarded_changes[0].contains(ComponentChanged)


def test_delete_observer_failure_keeps_committed_scientific_state() -> None:
    """An isolated observer failure keeps deletion and reaches later listeners."""
    project = SpectroscopyProject()
    component = _component("component-1")
    project.model.add_component(component)
    line = _line("line-1", component.id, needs_optimization=False)
    project.absorption_lines[line.line_id] = line
    project.absorption_regions["region-1"] = AbsorptionRegion(
        region_id="region-1", line_ids=[line.line_id]
    )
    port = _Port()
    later_events: list[object] = []

    def fail_observer(_changes: object) -> None:
        raise RuntimeError("injected delete observer failure")

    project.model.events.subscribe(fail_observer)
    project.model.events.subscribe(later_events.append)

    OptimizeParameterDeleteController(port=port).delete_components(project, [component])

    assert component not in project.model.components
    assert line.model_ids == []
    assert project.region_analysis_state("region-1").current_revision == AnalysisRevision(1)
    assert len(port.records) == 1
    assert len(later_events) == 1
