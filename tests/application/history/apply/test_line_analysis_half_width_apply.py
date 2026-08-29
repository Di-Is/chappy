"""Tests for atomic line analysis half-width history application."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

import pytest

from chappy.application.history import (
    HistoryApplyError,
    HistoryApplyErrorCode,
    HistoryRefreshTarget,
    LineAnalysisHalfWidthHistoryCommand,
    LineAnalysisHalfWidthStateSnapshot,
)
from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.analysis import (
    AnalysisArtifact,
    AnalysisRevision,
    FitSummary,
    RegionAnalysisState,
)
from chappy.core.constants import LIGHT_SPEED_KMS
from chappy.core.history import CommandHistory, HistoryEvent
from chappy.core.spectroscopy_project import SpectroscopyProject

from history_apply_fakes import FakeHistoryRefreshPort, build_usecase

if TYPE_CHECKING:
    from chappy.application.history.apply.usecase import HistoryApplyUseCase

_ALL_TARGETS = (
    HistoryRefreshTarget.OPTIMIZE_PANEL,
    HistoryRefreshTarget.LINE_OVERLAYS,
    HistoryRefreshTarget.VELOCITY_PLOT,
    HistoryRefreshTarget.OPTIMIZE_WAVELENGTH_MODEL_RESIDUAL,
)


class _Project(SpectroscopyProject):
    """Project with a failure-injectable region recalculation."""

    def __init__(self) -> None:
        """Initialize the failure-injection flag."""
        super().__init__()
        self.fail_region_update = False

    def update_region_analysis_range(self, region_id: str) -> None:
        """Recalculate the region range, optionally injecting a failure."""
        if self.fail_region_update:
            raise RuntimeError("region update failed")
        return super().update_region_analysis_range(region_id)


def _range(line: AbsorptionLine, half_width: float) -> tuple[float, float]:
    """Compute a symmetric wavelength window around one line's observed center."""
    observed = line.observed_wavelength()
    delta = observed * half_width / LIGHT_SPEED_KMS
    return observed - delta, observed + delta


def _fixture(
    *, refresh_port: FakeHistoryRefreshPort | None = None
) -> tuple[_Project, CommandHistory, HistoryApplyUseCase, HistoryEvent]:
    """Build one committed half-width history event ready to Undo/Redo."""
    project = _Project()
    first = AbsorptionLine(
        line_id="line-1",
        species="C IV",
        rest_wavelength=1548.2,
        center_z=1.0,
        window_kms=100.0,
        multiplet_label="C IV",
        transition_name="1548",
        oscillator_strength=0.1,
        gamma_value=1e8,
        region_id="region-1",
    )
    second = AbsorptionLine(
        line_id="line-2",
        species="C IV",
        rest_wavelength=1550.8,
        center_z=1.0,
        window_kms=120.0,
        multiplet_label="C IV",
        transition_name="1550",
        oscillator_strength=0.1,
        gamma_value=1e8,
        region_id="region-1",
    )
    first.lambda_range = _range(first, 100.0)
    second.lambda_range = _range(second, 120.0)
    first.needs_optimization = False
    second.needs_optimization = False
    project.absorption_lines = {first.line_id: first, second.line_id: second}
    project.absorption_regions = {
        "region-1": AbsorptionRegion(
            region_id="region-1",
            line_ids=[first.line_id, second.line_id],
            analysis_range=(first.lambda_range[0], second.lambda_range[1]),
        )
    }
    revision = AnalysisRevision()
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

    history = CommandHistory()
    usecase = build_usecase(
        project_provider=lambda: project, refresh_port=refresh_port or FakeHistoryRefreshPort()
    )
    history.set_applier(usecase)
    event = HistoryEvent(
        command=LineAnalysisHalfWidthHistoryCommand(
            affected_line_ids=(first.line_id,),
            before=(
                LineAnalysisHalfWidthStateSnapshot(
                    line_id=first.line_id, half_width_kms=150.0, lambda_range=_range(first, 150.0)
                ),
            ),
            after=(
                LineAnalysisHalfWidthStateSnapshot(
                    line_id=first.line_id, half_width_kms=100.0, lambda_range=_range(first, 100.0)
                ),
            ),
            region_id="region-1",
        )
    )
    assert history.push(event)
    return project, history, usecase, event


def _scientific_state(project: _Project) -> tuple[object, ...]:
    """Capture every scientific fact one half-width history apply may touch."""
    region = project.absorption_regions["region-1"]
    return (
        tuple(
            (line.line_id, line.window_kms, line.lambda_range, line.needs_optimization)
            for line in project.absorption_lines.values()
        ),
        region.analysis_range,
        project.region_analysis_state("region-1"),
        project.modified,
    )


def test_line_analysis_history_applies_undo_and_redo_and_keeps_region_stale() -> None:
    """Undo and Redo restore widths while preserving the stale-region contract."""
    refresh_port = FakeHistoryRefreshPort()
    project, history, _usecase, _event = _fixture(refresh_port=refresh_port)

    with (
        patch.object(project.model, "invalidate_model") as invalidate_model,
        patch.object(project.model, "update_model") as update_model,
    ):
        assert history.undo().success
        assert project.absorption_lines["line-1"].window_kms == 150.0
        assert all(line.needs_optimization for line in project.absorption_lines.values())
        assert history.can_redo
        assert history.redo().success

    invalidate_model.assert_not_called()
    update_model.assert_not_called()
    assert project.absorption_lines["line-1"].window_kms == 100.0
    assert all(line.needs_optimization for line in project.absorption_lines.values())
    assert history.can_undo
    assert not history.can_redo
    assert refresh_port.targets() == _ALL_TARGETS * 2
    analysis_state = project.region_analysis_state("region-1")
    assert analysis_state is not None
    assert analysis_state.current_revision == AnalysisRevision(2)
    assert analysis_state.artifact is not None
    assert analysis_state.artifact.source_revision == AnalysisRevision()


def test_half_width_undo_has_one_executor_owned_invalidation_and_read_only_refresh() -> None:
    """One production-shaped Undo must advance revision once and dispatch every refresh once."""
    refresh_port = FakeHistoryRefreshPort()
    project, history, _usecase, _event = _fixture(refresh_port=refresh_port)
    state_before = project.region_analysis_state("region-1")
    assert state_before is not None and state_before.artifact is not None
    artifact = state_before.artifact
    modified_before = project.modified

    assert history.undo().success

    state = project.region_analysis_state("region-1")
    assert state is not None
    assert state.current_revision == AnalysisRevision(1)
    assert state.artifact is artifact
    assert state.artifact.source_revision == AnalysisRevision(0)
    assert all(line.needs_optimization for line in project.absorption_lines.values())
    assert project.modified > modified_before
    assert refresh_port.targets() == _ALL_TARGETS


def test_region_recalculation_failure_restores_project_and_history_stack() -> None:
    """A failed derived-range recalculation must leave no partial scientific apply."""
    project, history, _usecase, _event = _fixture()
    before_project = _scientific_state(project)
    before_history = history.get_state()
    project.fail_region_update = True

    with pytest.raises(RuntimeError, match="region update failed"):
        history.undo()

    assert _scientific_state(project) == before_project
    assert history.get_state() == before_history


def test_gui_refresh_failure_keeps_science_and_history_committed() -> None:
    """A failed post-commit refresh must not revert science or stack transfer.

    The isolated failure is on the velocity-plot target only; every other
    declared target must still reach the refresh port despite it, matching
    ``run_postcommit_actions_isolated``'s per-target isolation guarantee.
    """
    refresh_port = FakeHistoryRefreshPort(
        fail_targets=frozenset({HistoryRefreshTarget.VELOCITY_PLOT})
    )
    project, history, _usecase, _event = _fixture(refresh_port=refresh_port)
    before_project = _scientific_state(project)

    assert history.undo().success

    assert _scientific_state(project) != before_project
    assert project.absorption_lines["line-1"].window_kms == 150.0
    assert history.can_redo
    assert not history.can_undo
    assert refresh_port.targets() == _ALL_TARGETS


def test_missing_region_line_is_rejected_before_any_mutation() -> None:
    """Every region line must exist before a scientific history apply begins."""
    project, history, _usecase, _event = _fixture()
    project.absorption_lines.pop("line-2")
    before_project = _scientific_state(project)
    before_history = history.get_state()

    with pytest.raises(HistoryApplyError, match="missing lines"):
        history.undo()

    assert _scientific_state(project) == before_project
    assert history.get_state() == before_history


def test_already_restored_half_width_is_no_change_without_invalidation() -> None:
    """An Undo target already present in storage must not stale the region again."""
    refresh_port = FakeHistoryRefreshPort()
    project, history, _usecase, _event = _fixture(refresh_port=refresh_port)
    line = project.absorption_lines["line-1"]
    line.window_kms = 150.0
    line.lambda_range = _range(line, 150.0)
    project.update_region_analysis_range("region-1")
    before_state = project.region_analysis_state("region-1")
    before_modified = project.modified

    assert history.undo().success

    assert project.region_analysis_state("region-1") == before_state
    assert project.modified == before_modified
    assert not any(line.needs_optimization for line in project.absorption_lines.values())
    assert refresh_port.calls == []


@pytest.mark.parametrize(
    "invalid_shape",
    (
        "empty-affected",
        "empty-before",
        "empty-after",
        "duplicate-affected",
        "duplicate-before",
        "duplicate-after",
        "mismatched-sets",
    ),
)
def test_half_width_history_rejects_incomplete_or_duplicate_identity_sets(
    invalid_shape: str,
) -> None:
    """All three command identity collections must be non-empty unique equal sets."""
    project, history, _usecase, event = _fixture()
    command = cast("LineAnalysisHalfWidthHistoryCommand", event.command)
    first_before = command.before[0]
    first_after = command.after[0]
    if invalid_shape == "empty-affected":
        invalid = replace(command, affected_line_ids=())
    elif invalid_shape == "empty-before":
        invalid = replace(command, before=())
    elif invalid_shape == "empty-after":
        invalid = replace(command, after=())
    elif invalid_shape == "duplicate-affected":
        invalid = replace(command, affected_line_ids=(first_before.line_id, first_before.line_id))
    elif invalid_shape == "duplicate-before":
        invalid = replace(command, before=(first_before, first_before))
    elif invalid_shape == "duplicate-after":
        invalid = replace(command, after=(first_after, first_after))
    else:
        invalid = replace(command, affected_line_ids=(first_before.line_id, "line-2"))

    history.clear()
    assert history.push(HistoryEvent(command=invalid))
    before_project = _scientific_state(project)
    before_history = history.get_state()

    with pytest.raises(HistoryApplyError) as exc_info:
        history.undo()

    assert exc_info.value.error_code is HistoryApplyErrorCode.INVALID_STATE
    assert _scientific_state(project) == before_project
    assert history.get_state() == before_history
