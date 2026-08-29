"""Tests for atomic continuum component creation mutations."""

from __future__ import annotations

import contextlib

import numpy as np
import pytest

from chappy.application.continuum import ContinuumComponentMutationUseCase
from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.analysis import AnalysisRevision
from chappy.core.components.continuum import ContinuumComponent
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.core.spectrum import Spectrum


def _add_region(project: SpectroscopyProject, region_id: str) -> None:
    """Add one analysis-capable region with a fresh line."""
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


def _project() -> SpectroscopyProject:
    """Create a project with observed data and two analysis regions."""
    project = SpectroscopyProject(name="Continuum Component Mutation Test")
    wavelength = np.linspace(4000.0, 4200.0, 201)
    project.model.set_observed_spectrum(
        Spectrum(wavelength=wavelength, flux=np.ones_like(wavelength))
    )
    _add_region(project, "region-1")
    _add_region(project, "region-2")
    return project


@contextlib.contextmanager
def _history_scope():
    """Provide a successful history recording boundary."""
    yield


def test_add_component_commits_points_global_invalidation_and_history() -> None:
    """Component, initial points, global stale state, and history commit together."""
    project = _project()
    recorded: list[ContinuumComponent] = []
    points = [(4050.0, 1.0), (4150.0, 1.1)]

    result = ContinuumComponentMutationUseCase().add_component(
        project,
        name="Continuum 1",
        points=points,
        record_history=recorded.append,
        history_scope=_history_scope,
    )

    assert result.impact.changed is True
    assert result.component in project.model.components
    assert result.component.continuum_points == points
    assert recorded == [result.component]
    assert all(
        state.current_revision == AnalysisRevision(1) for state in project.region_analysis_states()
    )
    assert all(line.needs_optimization for line in project.absorption_lines.values())


def test_add_component_history_failure_removes_component_and_restores_freshness() -> None:
    """A history failure must not leave an auto-created continuum behind."""
    project = _project()
    modified_before = project.modified

    def fail_history(_component: ContinuumComponent) -> None:
        raise RuntimeError("injected continuum component history failure")

    with pytest.raises(RuntimeError, match="injected continuum component history failure"):
        ContinuumComponentMutationUseCase().add_component(
            project,
            name="Continuum 1",
            points=[(4050.0, 1.0)],
            record_history=fail_history,
            history_scope=_history_scope,
        )

    assert not any(
        isinstance(component, ContinuumComponent) for component in project.model.components
    )
    assert all(
        state.current_revision == AnalysisRevision(0) for state in project.region_analysis_states()
    )
    assert all(not line.needs_optimization for line in project.absorption_lines.values())
    assert project.modified == modified_before


def test_add_component_observer_failure_keeps_committed_scientific_state() -> None:
    """An isolated observer failure keeps the commit and reaches later listeners."""
    project = _project()
    recorded: list[ContinuumComponent] = []
    later_events: list[object] = []

    def fail_model_observer(_event: object) -> None:
        raise RuntimeError("injected continuum model observer failure")

    project.model.events.subscribe(fail_model_observer)
    project.model.events.subscribe(later_events.append)

    ContinuumComponentMutationUseCase().add_component(
        project,
        name="Continuum 1",
        points=[(4050.0, 1.0)],
        record_history=recorded.append,
        history_scope=_history_scope,
    )

    created = [
        component
        for component in project.model.components
        if isinstance(component, ContinuumComponent)
    ]
    assert len(created) == 1
    assert recorded == created
    assert len(later_events) == 1
    assert all(
        state.current_revision == AnalysisRevision(1) for state in project.region_analysis_states()
    )


def test_add_component_derived_model_failure_rolls_back_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A derived model calculation failure remains inside the scientific rollback boundary."""
    project = _project()
    modified_before = project.modified

    def fail_calculation(_component: ContinuumComponent, _wavelength: np.ndarray) -> np.ndarray:
        raise RuntimeError("injected continuum derived model failure")

    monkeypatch.setattr(ContinuumComponent, "calculate", fail_calculation)

    with pytest.raises(RuntimeError, match="injected continuum derived model failure"):
        ContinuumComponentMutationUseCase().add_component(
            project,
            name="Continuum 1",
            points=[(4050.0, 1.0)],
            record_history=lambda _component: None,
            history_scope=_history_scope,
        )

    assert not any(
        isinstance(component, ContinuumComponent) for component in project.model.components
    )
    assert all(
        state.current_revision == AnalysisRevision(0) for state in project.region_analysis_states()
    )
    assert all(not line.needs_optimization for line in project.absorption_lines.values())
    assert project.modified == modified_before
