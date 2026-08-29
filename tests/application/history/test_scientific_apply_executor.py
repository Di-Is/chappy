"""Tests for atomic scientific Undo/Redo application transitions."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from chappy.application.analysis_artifacts import AnalysisMutationOutcome
from chappy.application.history import (
    HistoryApplyError,
    HistoryApplyResult,
    ScientificHistoryApplyExecutor,
    ScientificHistoryScope,
)
from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.analysis import (
    AnalysisArtifact,
    AnalysisRevision,
    FitSummary,
    RegionAnalysisState,
)
from chappy.core.spectroscopy_project import SpectroscopyProject

if TYPE_CHECKING:
    from collections.abc import Iterator


def _project() -> SpectroscopyProject:
    """Build two analysis-capable regions with current artifacts."""
    project = SpectroscopyProject()
    lines: dict[str, AbsorptionLine] = {}
    regions: dict[str, AbsorptionRegion] = {}
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
        )
        line.needs_optimization = False
        lines[line_id] = line
        regions[region_id] = AbsorptionRegion(region_id=region_id, line_ids=[line_id])
    project.load_absorption_state(regions=regions, lines=lines)
    for region_id in regions:
        revision = AnalysisRevision(4)
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
    return project


def test_global_success_increments_each_revision_once_and_retains_stale_artifact() -> None:
    """A changed global history apply must stale every capable region exactly once."""
    project = _project()
    artifacts_before = {
        state.region_id: state.artifact for state in project.region_analysis_states()
    }
    runtime = {"value": 2}

    execution = ScientificHistoryApplyExecutor().execute(
        project,
        ScientificHistoryScope.all_analysis_capable(),
        preflight=lambda: AnalysisMutationOutcome.CHANGED,
        capture_runtime=lambda: runtime["value"],
        mutate=lambda: runtime.__setitem__("value", 1) or HistoryApplyResult.ok(),
        restore_runtime=lambda value: runtime.__setitem__("value", value),
    )

    assert execution.impact.affected_region_ids == ("region-1", "region-2")
    assert runtime["value"] == 1
    for state in project.region_analysis_states():
        assert state.current_revision == AnalysisRevision(5)
        assert state.artifact is artifacts_before[state.region_id]
        assert state.artifact is not None
        assert state.artifact.source_revision == AnalysisRevision(4)
    assert all(line.needs_optimization for line in project.absorption_lines.values())


def test_changed_zero_region_project_still_records_scientific_modification() -> None:
    """A changed command remains a project edit without regions or observed data."""
    project = SpectroscopyProject()
    project.modified = datetime(2020, 1, 1, tzinfo=UTC)
    modified_before = project.modified
    runtime = {"value": 2}

    with patch.object(
        project, "mark_scientific_modified", wraps=project.mark_scientific_modified
    ) as mark_modified:
        execution = ScientificHistoryApplyExecutor().execute(
            project,
            ScientificHistoryScope.all_analysis_capable(),
            preflight=lambda: AnalysisMutationOutcome.CHANGED,
            capture_runtime=lambda: runtime["value"],
            mutate=lambda: runtime.__setitem__("value", 1) or HistoryApplyResult.ok(),
            restore_runtime=lambda value: runtime.__setitem__("value", value),
        )

    assert execution.impact.changed
    assert execution.impact.affected_region_ids == ()
    assert runtime["value"] == 1
    assert project.modified > modified_before
    mark_modified.assert_called_once_with()


def test_no_change_skips_runtime_snapshot_mutation_and_invalidation() -> None:
    """NoChange must leave every project fact and callback untouched."""
    project = _project()
    before_states = project.region_analysis_states()
    before_modified = project.modified

    def unexpected() -> object:
        raise AssertionError("NoChange executed a mutation callback")

    execution = ScientificHistoryApplyExecutor().execute(
        project,
        ScientificHistoryScope.all_analysis_capable(),
        preflight=lambda: AnalysisMutationOutcome.NO_CHANGE,
        capture_runtime=unexpected,
        mutate=unexpected,
        restore_runtime=lambda _snapshot: None,
    )

    assert not execution.impact.changed
    assert project.region_analysis_states() == before_states
    assert project.modified == before_modified
    assert not any(line.needs_optimization for line in project.absorption_lines.values())


def test_missing_local_target_is_rejected_before_runtime_mutation() -> None:
    """Local scope preflight must reject missing regions before capture or mutate."""
    project = _project()
    calls: list[str] = []

    with pytest.raises(HistoryApplyError, match="region not found"):
        ScientificHistoryApplyExecutor().execute(
            project,
            ScientificHistoryScope.regions("missing"),
            preflight=lambda: AnalysisMutationOutcome.CHANGED,
            capture_runtime=lambda: calls.append("capture"),
            mutate=lambda: calls.append("mutate") or HistoryApplyResult.ok(),
            restore_runtime=lambda _snapshot: calls.append("restore"),
        )

    assert calls == []


def test_failure_after_partial_freshness_commit_restores_every_owned_fact() -> None:
    """Failure injection after one region invalidates must rollback all storage."""
    project = _project()
    runtime = {"value": 2}
    states_before = project.region_analysis_states()
    flags_before = tuple(
        (line_id, line.needs_optimization) for line_id, line in project.absorption_lines.items()
    )
    modified_before = project.modified
    original_mark = project.mark_region_needs_optimization
    mark_calls = 0

    def fail_second_mark(region_id: str) -> int:
        nonlocal mark_calls
        mark_calls += 1
        if mark_calls == 2:
            raise RuntimeError("mark failure")
        return original_mark(region_id)

    with (
        patch.object(project, "mark_region_needs_optimization", side_effect=fail_second_mark),
        pytest.raises(RuntimeError, match="mark failure"),
    ):
        ScientificHistoryApplyExecutor().execute(
            project,
            ScientificHistoryScope.all_analysis_capable(),
            preflight=lambda: AnalysisMutationOutcome.CHANGED,
            capture_runtime=lambda: runtime["value"],
            mutate=lambda: runtime.__setitem__("value", 1) or HistoryApplyResult.ok(),
            restore_runtime=lambda value: runtime.__setitem__("value", value),
        )

    assert runtime["value"] == 2
    assert project.region_analysis_states() == states_before
    assert (
        tuple(
            (line_id, line.needs_optimization)
            for line_id, line in project.absorption_lines.items()
        )
        == flags_before
    )
    assert project.modified == modified_before


def test_notification_scope_exit_failure_restores_every_transaction_fact() -> None:
    """A failing notification scope exit remains inside the atomic boundary."""
    project = _project()
    runtime = {"value": 2}
    states_before = project.stored_region_analysis_states_for_transaction()
    flags_before = tuple(
        (line_id, line.needs_optimization) for line_id, line in project.absorption_lines.items()
    )
    modified_before = project.modified
    exits = 0

    @contextmanager
    def notification_scope() -> Iterator[None]:
        nonlocal exits
        try:
            yield
        finally:
            exits += 1
            if exits == 1:
                raise RuntimeError("notification scope exit failed")

    with pytest.raises(RuntimeError, match="notification scope exit failed"):
        ScientificHistoryApplyExecutor().execute(
            project,
            ScientificHistoryScope.all_analysis_capable(),
            preflight=lambda: AnalysisMutationOutcome.CHANGED,
            capture_runtime=lambda: runtime["value"],
            mutate=lambda: runtime.__setitem__("value", 1) or HistoryApplyResult.ok(),
            restore_runtime=lambda value: runtime.__setitem__("value", value),
            notification_scope=notification_scope,
        )

    assert exits == 2
    assert runtime["value"] == 2
    assert project.stored_region_analysis_states_for_transaction() == states_before
    assert (
        tuple(
            (line_id, line.needs_optimization)
            for line_id, line in project.absorption_lines.items()
        )
        == flags_before
    )
    assert project.modified == modified_before


def test_failure_restores_implicit_analysis_state_storage_and_order() -> None:
    """Rollback must not materialize implicit region states or reorder explicit ones."""
    project = _project()
    explicit = project.region_analysis_state("region-2")
    assert explicit is not None
    project.replace_region_analysis_states_for_transaction((explicit,))
    stored_before = project.stored_region_analysis_states_for_transaction()
    runtime = {"value": 2}

    with (
        patch.object(
            project,
            "mark_region_needs_optimization",
            side_effect=RuntimeError("implicit state failure"),
        ),
        pytest.raises(RuntimeError, match="implicit state failure"),
    ):
        ScientificHistoryApplyExecutor().execute(
            project,
            ScientificHistoryScope.all_analysis_capable(),
            preflight=lambda: AnalysisMutationOutcome.CHANGED,
            capture_runtime=lambda: runtime["value"],
            mutate=lambda: runtime.__setitem__("value", 1) or HistoryApplyResult.ok(),
            restore_runtime=lambda value: runtime.__setitem__("value", value),
        )

    assert runtime["value"] == 2
    assert project.stored_region_analysis_states_for_transaction() == stored_before
    assert tuple(state.region_id for state in stored_before) == ("region-2",)
