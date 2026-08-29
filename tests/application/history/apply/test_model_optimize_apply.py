"""Tests for scientific fit-result history application."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from chappy.application.history import (
    HistoryRefreshTarget,
    LineOptimizationStateSnapshot,
    ModelOptimizeApplyCommand,
    component_parameter_state,
)
from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.analysis import (
    AnalysisArtifact,
    AnalysisRevision,
    FitSummary,
    RegionAnalysisState,
)
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.history import CommandHistory, HistoryEvent
from chappy.core.spectroscopy_project import SpectroscopyProject

from history_apply_fakes import FakeHistoryRefreshPort, build_usecase


def _line(line_id: str, region_id: str) -> AbsorptionLine:
    return AbsorptionLine(
        line_id=line_id,
        species="C IV",
        rest_wavelength=1548.2,
        center_z=2.0,
        window_kms=100.0,
        multiplet_label="C IV",
        transition_name=line_id,
        oscillator_strength=0.1,
        gamma_value=1e8,
        region_id=region_id,
        needs_optimization=False,
    )


def _fixture(
    *, equal_parameters: bool = False
) -> tuple[SpectroscopyProject, CommandHistory, FakeHistoryRefreshPort]:
    project = SpectroscopyProject()
    component = AbsorberComponent(component_id="component-1", redshift=1.0)
    before = (component_parameter_state(component),)
    if not equal_parameters:
        component.parameters["redshift"].set_value(2.0)
    after = (component_parameter_state(component),)
    project.model.add_component_storage(component)
    for index in (1, 2):
        region_id = f"region-{index}"
        line = _line(f"line-{index}", region_id)
        project.absorption_lines[line.line_id] = line
        project.absorption_regions[region_id] = AbsorptionRegion(
            region_id=region_id, line_ids=[line.line_id]
        )
        revision = AnalysisRevision(3)
        project.set_region_analysis_state(
            RegionAnalysisState(
                region_id=region_id,
                current_revision=revision,
                artifact=AnalysisArtifact(
                    region_id=region_id,
                    source_revision=revision,
                    fit_summary=FitSummary(chi_squared=1.0),
                ),
            )
        )
    project.modified = datetime(2020, 1, 1, tzinfo=UTC)
    history = CommandHistory()
    refresh_port = FakeHistoryRefreshPort()
    usecase = build_usecase(project_provider=lambda: project, refresh_port=refresh_port)
    history.set_applier(usecase)
    assert history.push(
        HistoryEvent(
            command=ModelOptimizeApplyCommand(
                component_ids=(component.id,),
                before=before,
                after=after,
                region_id="region-1",
                needs_optimization_before=(LineOptimizationStateSnapshot("line-1", True),),
            )
        )
    )
    return project, history, refresh_port


def test_fit_apply_undo_redo_never_revives_freshness() -> None:
    """Both directions stale every capable region and retain the old artifacts."""
    project, history, refresh_port = _fixture()
    artifacts = {state.region_id: state.artifact for state in project.region_analysis_states()}

    assert history.undo().success
    assert project.require_absorber_component("component-1").parameters["redshift"].value == 1.0
    assert history.redo().success
    assert project.require_absorber_component("component-1").parameters["redshift"].value == 2.0

    for state in project.region_analysis_states():
        assert state.current_revision == AnalysisRevision(5)
        assert state.artifact is artifacts[state.region_id]
        assert state.artifact is not None
        assert state.artifact.source_revision == AnalysisRevision(3)
    assert all(line.needs_optimization for line in project.absorption_lines.values())
    assert refresh_port.region_ids_for(HistoryRefreshTarget.OPTIMIZE_PANEL) == [None, None]


def test_fit_entry_with_equal_parameters_remains_changed_in_both_directions() -> None:
    """A fit entry that only changed freshness must still invalidate on Undo and Redo."""
    project, history, _refresh_port = _fixture(equal_parameters=True)

    assert history.undo().success
    assert history.redo().success

    assert tuple(state.current_revision for state in project.region_analysis_states()) == (
        AnalysisRevision(5),
        AnalysisRevision(5),
    )
    assert all(line.needs_optimization for line in project.absorption_lines.values())


def test_fit_apply_rebuild_failure_restores_project_and_history_exactly() -> None:
    """A derived-cache failure rolls back parameters, freshness, modified, and stack."""
    project, history, _refresh_port = _fixture()
    states_before = project.region_analysis_states()
    modified_before = project.modified
    history_before = history.get_state()
    parameter = project.require_absorber_component("component-1").parameters["redshift"]

    with (
        patch.object(
            project.model, "rebuild_model_storage", side_effect=RuntimeError("fit derived failure")
        ),
        pytest.raises(RuntimeError, match="fit derived failure"),
    ):
        history.undo()

    assert parameter.value == 2.0
    assert project.region_analysis_states() == states_before
    assert not any(line.needs_optimization for line in project.absorption_lines.values())
    assert project.modified == modified_before
    assert history.get_state() == history_before
