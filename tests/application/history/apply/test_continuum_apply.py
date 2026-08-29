"""Tests for continuum history application."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import patch

import numpy as np
import pytest

from chappy.application.history import (
    ContinuumAddComponentCommand,
    ContinuumAddPointCommand,
    ContinuumComponentSnapshot,
    ContinuumDeletePointCommand,
    ContinuumMovePointCommand,
    ContinuumPointSnapshot,
    ContinuumResetCommand,
    HistoryApplyError,
    HistoryApplyErrorCode,
)
from chappy.application.history.snapshot_builders import continuum_component_snapshot
from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.analysis import (
    AnalysisArtifact,
    AnalysisRevision,
    FitSummary,
    RegionAnalysisState,
)
from chappy.core.components.continuum import ContinuumComponent
from chappy.core.history import CommandHistory, HistoryEvent
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.core.spectrum import Spectrum

from history_apply_fakes import build_usecase

if TYPE_CHECKING:
    from chappy.application.history.apply.usecase import HistoryApplyUseCase


def _history(project: SpectroscopyProject) -> tuple[CommandHistory, HistoryApplyUseCase]:
    """Connect a real history stack to the continuum history handler."""
    history = CommandHistory()
    usecase = build_usecase(project_provider=lambda: project)
    history.set_applier(usecase)
    return history, usecase


def _point(wavelength: float = 1215.67, flux: float = 1.0) -> ContinuumPointSnapshot:
    """Create one continuum point snapshot."""
    return ContinuumPointSnapshot(wavelength=wavelength, flux=flux)


def _scientific_project(
    points: tuple[ContinuumPointSnapshot, ...],
) -> tuple[SpectroscopyProject, ContinuumComponent]:
    """Build a continuum plus two globally analysis-capable regions."""
    project = SpectroscopyProject()
    wavelength = np.linspace(1000.0, 1500.0, 80, dtype=np.float64)
    project.model.set_observed_spectrum(
        Spectrum(wavelength=wavelength, flux=np.ones_like(wavelength), error=None, header={})
    )
    continuum = ContinuumComponent("Continuum")
    continuum.id = "continuum-1"
    continuum.continuum_points = [point.as_position() for point in points]
    project.model.add_component_storage(continuum)
    project.model.rebuild_model_storage()
    for index in (1, 2):
        region_id = f"region-{index}"
        line_id = f"line-{index}"
        line = AbsorptionLine(
            line_id=line_id,
            species="C IV",
            rest_wavelength=1548.2,
            center_z=1.0,
            window_kms=100.0,
            multiplet_label="C IV",
            transition_name="1548",
            oscillator_strength=0.1,
            gamma_value=1e8,
            region_id=region_id,
            needs_optimization=False,
        )
        project.absorption_lines[line_id] = line
        project.absorption_regions[region_id] = AbsorptionRegion(
            region_id=region_id, line_ids=[line_id]
        )
        revision = AnalysisRevision(1)
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
    return project, continuum


def _assert_freshness(
    project: SpectroscopyProject, artifacts: dict[str, AnalysisArtifact | None], *, revision: int
) -> None:
    """Assert one successful global history transition."""
    for region_id in ("region-1", "region-2"):
        state = project.region_analysis_state(region_id)
        assert state is not None and state.current_revision == AnalysisRevision(revision)
        assert state.artifact is artifacts[region_id]
        assert state.artifact is not None
        assert state.artifact.source_revision == AnalysisRevision(1)
    assert all(line.needs_optimization for line in project.absorption_lines.values())
    assert project.modified > datetime(2020, 1, 1, tzinfo=UTC)


def test_continuum_history_resolves_current_project_without_editor() -> None:
    """Point application uses the project model rather than editor selection."""
    project = SpectroscopyProject()
    continuum = ContinuumComponent("Project continuum")
    continuum.id = "continuum-1"
    project.model.add_component_storage(continuum)
    _history_stack, usecase = _history(project)

    change = usecase._continuum_applier.replace_continuum_points("continuum-1", (_point(),))

    assert continuum.get_continuum_points() == [(1215.67, 1.0)]
    assert change.changed_continuum_ids == ("continuum-1",)


def test_continuum_history_stale_project_target_remains_typed_apply_error() -> None:
    """A missing project component reports a typed target failure."""
    _history_stack, usecase = _history(SpectroscopyProject())

    with pytest.raises(HistoryApplyError) as exc_info:
        usecase._continuum_applier.replace_continuum_points("continuum-1", (_point(),))

    assert exc_info.value.error_code is HistoryApplyErrorCode.TARGET_NOT_FOUND


def test_continuum_component_restore_api_does_not_record_new_history() -> None:
    """The explicit history-apply API recreates state without recursive recording."""
    project = SpectroscopyProject()
    history, usecase = _history(project)
    snapshot = ContinuumComponentSnapshot(
        component_id="continuum-restored",
        name="Restored Continuum",
        enabled=False,
        is_shared_with_absorption=False,
        points=(_point(),),
    )

    add_change = usecase._continuum_applier.add_continuum_component(snapshot, index=0)

    component = project.model.get_component_by_id(snapshot.component_id)
    assert isinstance(component, ContinuumComponent)
    assert component.name == snapshot.name
    assert component.enabled is False
    assert component.is_shared_with_absorption is False
    assert component.get_continuum_points() == [(1215.67, 1.0)]
    assert add_change.changed_continuum_ids == (snapshot.component_id,)
    assert history.can_undo is False

    remove_change = usecase._continuum_applier.remove_continuum_component(snapshot.component_id)

    assert project.model.get_component_by_id(snapshot.component_id) is None
    assert remove_change.changed_continuum_ids == (snapshot.component_id,)
    assert history.can_undo is False


def test_continuum_component_add_undo_redo_restores_model_order_and_freshness() -> None:
    """Component creation history preserves its exact insertion position globally."""
    base_points = (_point(1000.0), _point(1250.0), _point(1500.0))
    project, first = _scientific_project(base_points)
    target = ContinuumComponent("Target")
    target.id = "continuum-target"
    target.continuum_points = [point.as_position() for point in base_points]
    project.model.add_component_storage(target)
    history, _usecase = _history(project)
    artifacts = {state.region_id: state.artifact for state in project.region_analysis_states()}
    assert history.push(
        HistoryEvent(
            command=ContinuumAddComponentCommand(
                snapshot=continuum_component_snapshot(target), component_index=1
            )
        )
    )

    assert history.undo().success
    assert project.model.components == [first]
    _assert_freshness(project, artifacts, revision=2)

    assert history.redo().success
    assert tuple(component.id for component in project.model.components) == (first.id, target.id)
    _assert_freshness(project, artifacts, revision=3)


@pytest.mark.parametrize(
    ("command_type", "before", "after"),
    (
        (
            ContinuumAddPointCommand,
            (_point(1000.0), _point(1250.0), _point(1500.0)),
            (_point(1000.0), _point(1200.0, 0.9), _point(1250.0), _point(1500.0)),
        ),
        (
            ContinuumDeletePointCommand,
            (_point(1000.0), _point(1200.0), _point(1250.0), _point(1500.0)),
            (_point(1000.0), _point(1250.0), _point(1500.0)),
        ),
        (
            ContinuumMovePointCommand,
            (_point(1000.0), _point(1250.0), _point(1500.0)),
            (_point(1000.0), _point(1300.0, 0.8), _point(1500.0)),
        ),
        (
            ContinuumResetCommand,
            (_point(1000.0), _point(1250.0), _point(1500.0)),
            (_point(1050.0, 0.9), _point(1300.0, 1.1), _point(1450.0, 0.95)),
        ),
    ),
)
def test_continuum_point_commands_undo_redo_exact_order_and_global_freshness(
    command_type: type[
        ContinuumAddPointCommand
        | ContinuumDeletePointCommand
        | ContinuumMovePointCommand
        | ContinuumResetCommand
    ],
    before: tuple[ContinuumPointSnapshot, ...],
    after: tuple[ContinuumPointSnapshot, ...],
) -> None:
    """Every point command restores complete order and stales all regions per direction."""
    project, continuum = _scientific_project(after)
    history, _usecase = _history(project)
    artifacts = {state.region_id: state.artifact for state in project.region_analysis_states()}
    command = command_type(continuum_id=continuum.id, before=before, after=after)
    assert history.push(HistoryEvent(command=command))

    assert history.undo().success
    assert continuum.get_continuum_points() == [point.as_position() for point in before]
    _assert_freshness(project, artifacts, revision=2)

    assert history.redo().success
    assert continuum.get_continuum_points() == [point.as_position() for point in after]
    _assert_freshness(project, artifacts, revision=3)


def test_continuum_exact_target_no_change_is_fully_inert() -> None:
    """An already-restored complete point target advances only the history stack."""
    before = (_point(1000.0), _point(1250.0), _point(1500.0))
    after = (_point(1000.0), _point(1300.0), _point(1500.0))
    project, continuum = _scientific_project(before)
    history, _usecase = _history(project)
    states_before = project.region_analysis_states()
    modified_before = project.modified
    assert history.push(
        HistoryEvent(
            command=ContinuumMovePointCommand(
                continuum_id=continuum.id, before=before, after=after
            )
        )
    )

    assert history.undo().success

    assert project.region_analysis_states() == states_before
    assert project.modified == modified_before
    assert not any(line.needs_optimization for line in project.absorption_lines.values())


def test_continuum_missing_and_corrupt_sources_keep_undo_stack() -> None:
    """Missing targets are recoverable while corrupt point sources fail before mutation.

    A missing continuum target still raises ``HistoryApplyError`` through
    ``CommandHistory.undo()`` at this Qt-free layer: only ``HistoryBridge``'s
    public boundary converts a ``TARGET_NOT_FOUND`` failure into a
    ``(False, reason)`` tuple for GUI callers.
    """
    before = (_point(1000.0), _point(1250.0), _point(1500.0))
    after = (_point(1000.0), _point(1300.0), _point(1500.0))
    project, continuum = _scientific_project(after)
    history, _usecase = _history(project)
    command = ContinuumMovePointCommand(continuum_id=continuum.id, before=before, after=after)
    assert history.push(HistoryEvent(command=command))
    project.model.remove_component_storage(continuum)

    with pytest.raises(HistoryApplyError, match="Continuum not found"):
        history.undo()
    assert history.can_undo and not history.can_redo

    project.model.add_component_storage(continuum)
    continuum.continuum_points = [point.as_position() for point in (_point(1100.0),)]
    with pytest.raises(HistoryApplyError, match="source does not match"):
        history.undo()
    assert history.can_undo and not history.can_redo


def test_continuum_rebuild_failure_restores_identity_cache_freshness_and_stack() -> None:
    """A derived rebuild failure restores every point transaction fact exactly."""
    before = (_point(1000.0), _point(1250.0), _point(1500.0))
    after = (_point(1000.0), _point(1300.0, 0.8), _point(1500.0))
    project, continuum = _scientific_project(after)
    history, _usecase = _history(project)
    command = ContinuumMovePointCommand(continuum_id=continuum.id, before=before, after=after)
    assert history.push(HistoryEvent(command=command))
    order_before = tuple(project.model.components)
    derived_before = project.model.snapshot_derived_state_for_transaction()
    states_before = project.stored_region_analysis_states_for_transaction()
    modified_before = project.modified
    history_before = history.get_state()

    with (
        patch.object(
            project.model,
            "rebuild_model_storage",
            side_effect=RuntimeError("continuum rebuild failed"),
        ),
        pytest.raises(RuntimeError, match="continuum rebuild failed"),
    ):
        history.undo()

    assert tuple(project.model.components) == order_before
    assert project.model.get_component_by_id(continuum.id) is continuum
    assert continuum.get_continuum_points() == [point.as_position() for point in after]
    derived_after = project.model.snapshot_derived_state_for_transaction()
    assert derived_before.model_valid is derived_after.model_valid
    assert derived_before.model_flux is not None and derived_after.model_flux is not None
    np.testing.assert_array_equal(derived_after.model_flux, derived_before.model_flux)
    assert project.stored_region_analysis_states_for_transaction() == states_before
    assert not any(line.needs_optimization for line in project.absorption_lines.values())
    assert project.modified == modified_before
    assert history.get_state() == history_before
