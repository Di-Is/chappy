"""Tests for project-owned analysis artifact mutations."""

from __future__ import annotations

import pytest

from chappy.application.analysis_artifacts import (
    AnalysisArtifactStoreUseCase,
    RecordSuccessfulAnalysisUseCase,
)
from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.analysis import AnalysisRevision, FitSummary
from chappy.core.spectroscopy_project import SpectroscopyProject


def _add_region(project: SpectroscopyProject, region_id: str) -> None:
    """Add one analysis-capable region to a project."""
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
    )
    project.absorption_regions[region_id] = AbsorptionRegion(
        region_id=region_id, line_ids=[line_id]
    )


def test_same_region_id_is_isolated_by_project_ownership() -> None:
    """Two projects must never share evidence through an external project key."""
    first = SpectroscopyProject()
    second = SpectroscopyProject()
    _add_region(first, "region-1")
    _add_region(second, "region-1")
    usecase = AnalysisArtifactStoreUseCase()

    usecase.record_artifact(first, "region-1", FitSummary(chi_squared=2.5))

    first_state = first.region_analysis_state("region-1")
    second_state = second.region_analysis_state("region-1")
    assert first_state is not None
    assert second_state is not None
    assert first_state.artifact is not None
    assert second_state.artifact is None


def test_multiple_region_invalidation_is_validated_before_mutation() -> None:
    """A missing affected region must prevent every requested revision change."""
    project = SpectroscopyProject()
    _add_region(project, "region-1")
    _add_region(project, "region-2")
    usecase = AnalysisArtifactStoreUseCase()

    with pytest.raises(ValueError, match="missing"):
        usecase.invalidate_regions(project, ("region-1", "missing", "region-2"))

    states = project.region_analysis_states()
    assert tuple(state.current_revision for state in states) == (
        AnalysisRevision(0),
        AnalysisRevision(0),
    )


def test_all_capable_invalidation_updates_regions_in_one_operation() -> None:
    """Global scientific changes can invalidate every analysis-capable region."""
    project = SpectroscopyProject()
    _add_region(project, "region-1")
    _add_region(project, "region-2")
    project.absorption_regions["empty"] = AbsorptionRegion(region_id="empty")
    usecase = AnalysisArtifactStoreUseCase()

    affected = usecase.invalidate_all_analysis_capable(project)

    assert affected == ("region-1", "region-2")
    states = {state.region_id: state for state in project.region_analysis_states()}
    assert states["region-1"].current_revision == AnalysisRevision(1)
    assert states["region-2"].current_revision == AnalysisRevision(1)
    assert states["empty"].current_revision == AnalysisRevision(0)


def test_successful_fit_commit_rolls_back_artifact_flags_and_modified_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A collaborator failure cannot leave a partially committed successful fit."""
    project = SpectroscopyProject()
    _add_region(project, "region-1")
    before_state = project.region_analysis_state("region-1")
    before_modified = project.modified
    before_flag = project.absorption_lines["line-region-1"].needs_optimization

    def _fail_clear(_region_id: str) -> int:
        raise RuntimeError("injected clear failure")

    monkeypatch.setattr(project, "clear_region_needs_optimization", _fail_clear)

    with pytest.raises(RuntimeError, match="injected"):
        RecordSuccessfulAnalysisUseCase().execute(project, "region-1", FitSummary(chi_squared=1.0))

    assert project.region_analysis_state("region-1") == before_state
    assert project.absorption_lines["line-region-1"].needs_optimization is before_flag
    assert project.modified == before_modified
