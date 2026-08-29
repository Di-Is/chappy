"""Tests for atomic Optimize line analysis half-width transactions."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from chappy.application.optimize.models import (
    LineAnalysisHalfWidthLineChange,
    PreparedLineAnalysisHalfWidthChange,
)
from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.constants import LIGHT_SPEED_KMS
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.core.velocity_ranges import LineAnalysisHalfWidth
from chappy.gui.modes.analysis.region_detail.adapters.history_adapter import OptimizeHistoryAdapter
from chappy.gui.modes.analysis.region_detail.adapters.line_analysis_half_width_transaction_adapter import (
    OptimizeLineAnalysisHalfWidthTransactionAdapter,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from chappy.application.history import LineAnalysisHalfWidthStateSnapshot


class _GroupController:
    """Failure-injectable group-session collaborator."""

    def __init__(self, *, fail_invalidation: bool = False) -> None:
        self.ready = True
        self.export_enabled = True
        self.styles_stale = False
        self.fail_invalidation = fail_invalidation

    def refresh_group_analysis_views(self, project: SpectroscopyProject, region_id: str) -> None:
        _ = project
        _ = region_id
        self.ready = False
        self.export_enabled = False
        self.styles_stale = True
        if self.fail_invalidation:
            raise RuntimeError("group refresh failed")


class _History:
    """Failure-injectable history collaborator with an atomic recording scope."""

    def __init__(self, *, fail_recording: bool = False) -> None:
        self.events: list[tuple[str, ...]] = []
        self.fail_recording = fail_recording

    @contextmanager
    def atomic_recording(self) -> Iterator[None]:
        before = list(self.events)
        try:
            yield
        except Exception:
            self.events = before
            raise

    def record_line_analysis_half_width_change(
        self,
        affected_line_ids: tuple[str, ...],
        before_states: tuple[LineAnalysisHalfWidthStateSnapshot, ...],
        after_states: tuple[LineAnalysisHalfWidthStateSnapshot, ...],
        region_id: str,
    ) -> None:
        _ = before_states
        _ = after_states
        _ = region_id
        self.events.append(affected_line_ids)
        if self.fail_recording:
            raise RuntimeError("history recording failed")


def _line_range(line: AbsorptionLine, width: float) -> tuple[float, float]:
    observed = line.observed_wavelength()
    delta = observed * width / LIGHT_SPEED_KMS
    return (observed - delta, observed + delta)


def _fixture() -> tuple[SpectroscopyProject, PreparedLineAnalysisHalfWidthChange]:
    project = SpectroscopyProject()
    line = AbsorptionLine(
        line_id="line-1",
        species="C IV",
        rest_wavelength=1548.2,
        center_z=1.0,
        window_kms=150.0,
        region_id="region-1",
        multiplet_label="C IV",
        transition_name="1548",
        oscillator_strength=0.1,
        gamma_value=1e8,
    )
    before_range = _line_range(line, 150.0)
    after_range = _line_range(line, 100.0)
    line.lambda_range = before_range
    line.needs_optimization = False
    region = AbsorptionRegion(
        region_id="region-1", line_ids=[line.line_id], analysis_range=before_range
    )
    project.absorption_lines[line.line_id] = line
    project.absorption_regions[region.region_id] = region
    project.modified = datetime(2020, 1, 1, tzinfo=UTC)
    change = PreparedLineAnalysisHalfWidthChange(
        seed_line_id=line.line_id,
        region_id=region.region_id,
        line_changes=(
            LineAnalysisHalfWidthLineChange(
                line_id=line.line_id,
                before_half_width=150.0,
                after_half_width=LineAnalysisHalfWidth(100.0),
                before_lambda_range=before_range,
                after_lambda_range=after_range,
            ),
        ),
        region_line_ids=(line.line_id,),
        before_region_analysis_range=before_range,
        after_region_analysis_range=after_range,
    )
    return project, change


def test_history_failure_restores_project_group_and_history() -> None:
    """A history failure restores every scientific transaction fact."""
    project, change = _fixture()
    group = _GroupController()
    history = _History(fail_recording=True)
    before_modified = project.modified
    adapter = OptimizeLineAnalysisHalfWidthTransactionAdapter(
        project_provider=lambda: project,
        group_controller=group,  # type: ignore[arg-type]
        history=history,  # type: ignore[arg-type]
    )

    with pytest.raises(RuntimeError, match="history recording failed"):
        adapter.execute_line_analysis_half_width_change(change)

    line = project.absorption_lines["line-1"]
    assert line.window_kms == 150.0
    assert line.lambda_range == change.line_changes[0].before_lambda_range
    assert line.needs_optimization is False
    assert (
        project.absorption_regions["region-1"].analysis_range
        == change.before_region_analysis_range
    )
    assert project.modified == before_modified
    assert group.ready is True
    assert group.export_enabled is True
    assert group.styles_stale is False
    assert history.events == []


def test_post_commit_group_refresh_failure_keeps_scientific_commit() -> None:
    """A UI/export/style observer failure must not roll back committed science."""
    project, change = _fixture()
    group = _GroupController(fail_invalidation=True)
    history = _History()
    before_modified = project.modified
    adapter = OptimizeLineAnalysisHalfWidthTransactionAdapter(
        project_provider=lambda: project,
        group_controller=group,  # type: ignore[arg-type]
        history=history,  # type: ignore[arg-type]
    )

    adapter.execute_line_analysis_half_width_change(change)

    line = project.absorption_lines["line-1"]
    assert line.window_kms == 100.0
    assert line.lambda_range == change.line_changes[0].after_lambda_range
    assert line.needs_optimization is True
    assert project.modified > before_modified
    assert project.region_analysis_state("region-1").current_revision.value == 1  # type: ignore[union-attr]
    assert history.events == [("line-1",)]


def test_success_commits_project_invalidation_and_one_history_event() -> None:
    """A successful transaction should expose all scientific side effects together."""
    project, change = _fixture()
    group = _GroupController()
    history = _History()
    before_modified = project.modified
    adapter = OptimizeLineAnalysisHalfWidthTransactionAdapter(
        project_provider=lambda: project,
        group_controller=group,  # type: ignore[arg-type]
        history=history,  # type: ignore[arg-type]
    )

    adapter.execute_line_analysis_half_width_change(change)

    line = project.absorption_lines["line-1"]
    assert line.window_kms == 100.0
    assert line.lambda_range == change.line_changes[0].after_lambda_range
    assert line.needs_optimization is True
    assert (
        project.absorption_regions["region-1"].analysis_range == change.after_region_analysis_range
    )
    assert project.modified > before_modified
    assert group.ready is False
    assert group.export_enabled is False
    assert group.styles_stale is True
    assert history.events == [("line-1",)]


def test_success_marks_every_region_line_and_advances_revision_once() -> None:
    """A local half-width edit stales all owning-region lines but only one revision."""
    project, change = _fixture()
    second = AbsorptionLine(
        line_id="line-2",
        species="Si IV",
        rest_wavelength=1393.8,
        center_z=1.0,
        window_kms=80.0,
        multiplet_label="Si IV",
        transition_name="1393",
        oscillator_strength=0.1,
        gamma_value=1e8,
        region_id="region-1",
        needs_optimization=False,
    )
    second.lambda_range = _line_range(second, second.window_kms)
    project.absorption_lines[second.line_id] = second
    project.absorption_regions["region-1"].line_ids.append(second.line_id)
    change = replace(change, region_line_ids=("line-1", "line-2"))
    adapter = OptimizeLineAnalysisHalfWidthTransactionAdapter(
        project_provider=lambda: project,
        group_controller=_GroupController(),  # type: ignore[arg-type]
        history=_History(),  # type: ignore[arg-type]
    )

    adapter.execute_line_analysis_half_width_change(change)

    assert project.absorption_lines["line-1"].needs_optimization
    assert project.absorption_lines["line-2"].needs_optimization
    state = project.region_analysis_state("region-1")
    assert state is not None and state.current_revision.value == 1


def test_missing_history_bridge_fails_before_scientific_mutation() -> None:
    """An edit without a usable Undo path must not mutate project or group state."""
    project, change = _fixture()
    group = _GroupController()
    before_modified = project.modified
    adapter = OptimizeLineAnalysisHalfWidthTransactionAdapter(
        project_provider=lambda: project,
        group_controller=group,  # type: ignore[arg-type]
        history=OptimizeHistoryAdapter(),
    )

    with pytest.raises(RuntimeError, match="connected history recorder"):
        adapter.execute_line_analysis_half_width_change(change)

    line = project.absorption_lines["line-1"]
    assert line.window_kms == 150.0
    assert line.lambda_range == change.line_changes[0].before_lambda_range
    assert line.needs_optimization is False
    assert project.modified == before_modified
    assert group.ready is True
    assert group.export_enabled is True
    assert group.styles_stale is False
