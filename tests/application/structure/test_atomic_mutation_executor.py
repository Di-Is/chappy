"""Pure contract tests for the atomic scientific structure executor."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast

import pytest

from chappy.application.structure import (
    AtomicStructureMutationExecution,
    AtomicStructureMutationExecutor,
    AtomicStructureProjectPort,
    StructureInvalidationScope,
    StructureMutationOutcome,
    StructureMutationResult,
    StructureRegionDelta,
)
from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.analysis import (
    AnalysisArtifact,
    AnalysisRevision,
    FitSummary,
    RegionAnalysisState,
)
from chappy.core.change_set import ChangeSet
from chappy.core.events import ModelInvalidated, RegionTopologyChanged
from chappy.core.masking import MaskDefinition

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True, slots=True)
class _DerivedSnapshot:
    """Exact derived-cache value owned by the fake model."""

    value: int


class _Model:
    """Failure-injectable derived model with a notification suppression scope."""

    def __init__(self) -> None:
        self.components: list[object] = []
        self.mask_definitions: tuple[MaskDefinition, ...] = ()
        self.derived_value = 7
        self.suppression_depth = 0
        self.scope_entry_count = 0
        self.fail_scope_entry_calls: set[int] = set()
        self.fail_scope_exit_calls: set[int] = set()
        self.published_notifications: list[str] = []

    def snapshot_derived_state_for_transaction(self) -> _DerivedSnapshot:
        """Capture current derived state."""
        return _DerivedSnapshot(self.derived_value)

    def restore_derived_state_for_transaction(self, snapshot: _DerivedSnapshot) -> None:
        """Restore current derived state."""
        self.derived_value = snapshot.value

    @contextmanager
    def suppress_notifications(self) -> Iterator[None]:
        """Record that scientific notifications are suppressed."""
        self.scope_entry_count += 1
        entry = self.scope_entry_count
        if entry in self.fail_scope_entry_calls:
            raise RuntimeError(f"injected notification scope entry failure {entry}")
        self.suppression_depth += 1
        try:
            yield
        finally:
            self.suppression_depth -= 1
            if entry in self.fail_scope_exit_calls:
                raise RuntimeError(f"injected notification scope exit failure {entry}")

    def publish(self, notification: str) -> None:
        """Publish only notifications emitted outside a suppression scope."""
        if self.suppression_depth == 0:
            self.published_notifications.append(notification)


class _Project:
    """Minimal scientific project implementation for executor contract tests."""

    def __init__(self, regions: dict[str, tuple[str, ...]]) -> None:
        self.absorption_regions: dict[str, AbsorptionRegion] = {}
        self.absorption_lines: dict[str, AbsorptionLine] = {}
        for region_id, line_ids in regions.items():
            self.absorption_regions[region_id] = AbsorptionRegion(
                region_id=region_id, line_ids=list(line_ids)
            )
            for line_id in line_ids:
                self.absorption_lines[line_id] = _line(line_id, region_id)
        self.model = _Model()
        self.modified = datetime(2020, 1, 1, tzinfo=UTC)
        self.committed_modified = self.modified + timedelta(days=1)
        self._states = {
            region_id: _analysis_state(region_id, revision=1)
            for region_id in self.absorption_regions
        }
        self.fail_stage: str | None = None
        self.needs_calls = 0

    def region_analysis_state(self, region_id: str) -> RegionAnalysisState | None:
        """Return explicit or implicit analysis state for a current region."""
        if region_id not in self.absorption_regions:
            return None
        return self._states.get(
            region_id,
            RegionAnalysisState(region_id=region_id, current_revision=AnalysisRevision()),
        )

    def stored_region_analysis_states_for_transaction(self) -> tuple[RegionAnalysisState, ...]:
        """Return explicitly stored analysis state."""
        return tuple(self._states.values())

    def set_region_analysis_states(self, states: Iterable[RegionAnalysisState]) -> None:
        """Apply revision replacements atomically, then optionally fail."""
        replacements = {state.region_id: state for state in states}
        self._states.update(replacements)
        self._fail_after("revision")

    def replace_region_analysis_states_for_transaction(
        self, states: Iterable[RegionAnalysisState]
    ) -> None:
        """Restore exact explicit state."""
        self._states = {state.region_id: state for state in states}

    def prune_region_analysis_states_for_transaction(self) -> None:
        """Prune removed region state, then optionally fail."""
        self._states = {
            region_id: state
            for region_id, state in self._states.items()
            if region_id in self.absorption_regions
        }
        self._fail_after("prune")

    def reset_region_analysis_states_for_transaction(self, region_ids: Iterable[str]) -> None:
        """Reset created region state, then optionally fail."""
        for region_id in region_ids:
            self._states.pop(region_id, None)
        self._fail_after("reset")

    def is_region_analysis_capable(self, region_id: str) -> bool:
        """Return whether all current region lines exist and point back to it."""
        region = self.absorption_regions.get(region_id)
        if region is None or not region.line_ids:
            return False
        return all(
            line_id in self.absorption_lines
            and self.absorption_lines[line_id].region_id == region_id
            for line_id in region.line_ids
        )

    def mark_region_needs_optimization(self, region_id: str) -> int:
        """Mark current region lines, then optionally fail on the first call."""
        self.needs_calls += 1
        changed = 0
        for line_id in self.absorption_regions[region_id].line_ids:
            line = self.absorption_lines[line_id]
            if not line.needs_optimization:
                line.needs_optimization = True
                changed += 1
        if self.needs_calls == 1:
            self._fail_after("needs")
        return changed

    def mark_scientific_modified(self) -> None:
        """Set a deterministic modified value, then optionally fail."""
        self.modified = self.committed_modified
        self._fail_after("modified")

    def _fail_after(self, stage: str) -> None:
        """Raise after the selected stage changed state."""
        if self.fail_stage == stage:
            raise RuntimeError(f"injected {stage} failure")


@dataclass(frozen=True, slots=True)
class _RuntimeSnapshot:
    """Exact fake region and line topology used for rollback."""

    regions: dict[str, AbsorptionRegion]
    lines: dict[str, AbsorptionLine]


class _History:
    """Atomic history list used to verify cross-owner rollback."""

    def __init__(self) -> None:
        self.entries = ["existing"]
        self.fail_on_success_exit = False

    @contextmanager
    def atomic(self) -> Iterator[None]:
        """Restore exact entries after any transaction failure."""
        snapshot = list(self.entries)
        try:
            yield
        except Exception:
            self.entries = snapshot
            raise
        if self.fail_on_success_exit:
            self.entries = snapshot
            raise RuntimeError("injected history exit failure")


@dataclass(frozen=True, slots=True)
class _MatrixCase:
    """One before/after revision-matrix row."""

    name: str
    before: dict[str, tuple[str, ...]]
    after: dict[str, tuple[str, ...]]
    delta: StructureRegionDelta
    expected_affected: tuple[str, ...]
    before_links: dict[str, tuple[str, ...]] = field(default_factory=dict)
    after_links: dict[str, tuple[str, ...]] = field(default_factory=dict)


def _line(line_id: str, region_id: str) -> AbsorptionLine:
    """Build one valid absorption line."""
    return AbsorptionLine(
        line_id=line_id,
        species="C IV",
        rest_wavelength=1548.2,
        center_z=2.0,
        window_kms=200.0,
        multiplet_label="C IV",
        transition_name="1548",
        oscillator_strength=0.19,
        gamma_value=2.64e8,
        region_id=region_id,
        needs_optimization=False,
    )


def _analysis_state(region_id: str, *, revision: int) -> RegionAnalysisState:
    """Build one analyzed region state."""
    source_revision = AnalysisRevision(revision)
    artifact = AnalysisArtifact(
        region_id=region_id,
        source_revision=source_revision,
        fit_summary=FitSummary(chi_squared=float(revision)),
    )
    return RegionAnalysisState(
        region_id=region_id, current_revision=source_revision, artifact=artifact
    )


def _capture_runtime(project: _Project) -> _RuntimeSnapshot:
    """Capture exact fake runtime structure."""
    return _RuntimeSnapshot(
        regions=deepcopy(project.absorption_regions), lines=deepcopy(project.absorption_lines)
    )


def _restore_runtime(project: _Project, snapshot: _RuntimeSnapshot) -> None:
    """Restore exact fake runtime structure."""
    project.absorption_regions = deepcopy(snapshot.regions)
    project.absorption_lines = deepcopy(snapshot.lines)
    project.model.publish("runtime-restored")


def _replace_topology(project: _Project, regions: dict[str, tuple[str, ...]]) -> None:
    """Replace fake topology while retaining surviving line objects."""
    previous_lines = project.absorption_lines
    next_regions: dict[str, AbsorptionRegion] = {}
    next_lines: dict[str, AbsorptionLine] = {}
    for region_id, line_ids in regions.items():
        next_regions[region_id] = AbsorptionRegion(region_id=region_id, line_ids=list(line_ids))
        for line_id in line_ids:
            line = previous_lines.get(line_id, _line(line_id, region_id))
            line.region_id = region_id
            next_lines[line_id] = line
    project.absorption_regions = next_regions
    project.absorption_lines = next_lines


def _execute_case(
    project: _Project,
    case: _MatrixCase,
    *,
    history: _History | None = None,
    mutate_override: Callable[[], StructureMutationResult[str]] | None = None,
) -> AtomicStructureMutationExecution[str]:
    """Execute one matrix transition through the common executor."""
    history = history or _History()

    def mutate() -> StructureMutationResult[str]:
        if mutate_override is not None:
            return mutate_override()
        assert project.model.suppression_depth == 1
        _replace_topology(project, case.after)
        for line_id, links in case.after_links.items():
            project.absorption_lines[line_id].multiplet_ids = list(links)
        return StructureMutationResult.changed_result(case.name, case.delta)

    def rebuild() -> ChangeSet:
        assert project.model.suppression_depth == 1
        project.model.derived_value += 1
        project._fail_after("derived")
        return ChangeSet.of(ModelInvalidated())

    def record(result: StructureMutationResult[str]) -> None:
        assert result.value == case.name
        history.entries.append(case.name)
        project._fail_after("history")

    return AtomicStructureMutationExecutor().execute(
        cast("AtomicStructureProjectPort", project),
        preflight=lambda: StructureMutationOutcome.CHANGED,
        capture_runtime=lambda: _capture_runtime(project),
        mutate=mutate,
        restore_runtime=lambda snapshot: _restore_runtime(project, snapshot),
        notification_scope=project.model.suppress_notifications,
        rebuild_derived=rebuild,
        record_history=record,
        history_scope=history.atomic,
    )


_MATRIX_CASES = (
    _MatrixCase(
        name="reorder-lines",
        before={"region": ("line-1", "line-2")},
        after={"region": ("line-2", "line-1")},
        delta=StructureRegionDelta(
            invalidation_scope=StructureInvalidationScope.LOCAL_SURVIVORS,
            affected_surviving_region_ids=("region",),
        ),
        expected_affected=("region",),
    ),
    _MatrixCase(
        name="move-existing",
        before={"source": ("line-1", "line-2"), "target": ("line-3",)},
        after={"source": ("line-2",), "target": ("line-3", "line-1")},
        delta=StructureRegionDelta(
            invalidation_scope=StructureInvalidationScope.LOCAL_SURVIVORS,
            affected_surviving_region_ids=("source", "target"),
        ),
        expected_affected=("source", "target"),
    ),
    _MatrixCase(
        name="move-new-and-remove-source",
        before={"source": ("line-1",), "other": ("line-2",)},
        after={"new": ("line-1",), "other": ("line-2",)},
        delta=StructureRegionDelta(
            invalidation_scope=StructureInvalidationScope.LOCAL_SURVIVORS,
            created_region_ids=("new",),
            removed_region_ids=("source",),
        ),
        expected_affected=(),
    ),
    _MatrixCase(
        name="split",
        before={"source": ("line-1", "line-2")},
        after={"source": ("line-2",), "new": ("line-1",)},
        delta=StructureRegionDelta(
            invalidation_scope=StructureInvalidationScope.LOCAL_SURVIVORS,
            affected_surviving_region_ids=("source",),
            created_region_ids=("new",),
        ),
        expected_affected=("source",),
    ),
    _MatrixCase(
        name="merge",
        before={"primary": ("line-1",), "secondary": ("line-2",)},
        after={"primary": ("line-1", "line-2")},
        delta=StructureRegionDelta(
            invalidation_scope=StructureInvalidationScope.LOCAL_SURVIVORS,
            affected_surviving_region_ids=("primary",),
            removed_region_ids=("secondary",),
        ),
        expected_affected=("primary",),
    ),
    _MatrixCase(
        name="delete-local",
        before={"source": ("line-1", "line-2"), "other": ("line-3",)},
        after={"source": ("line-2",), "other": ("line-3",)},
        delta=StructureRegionDelta(
            invalidation_scope=StructureInvalidationScope.LOCAL_SURVIVORS,
            affected_surviving_region_ids=("source",),
        ),
        expected_affected=("source",),
    ),
    _MatrixCase(
        name="unlink",
        before={"first": ("line-1",), "second": ("line-2",)},
        after={"first": ("line-1",), "second": ("line-2",)},
        delta=StructureRegionDelta(
            invalidation_scope=StructureInvalidationScope.LOCAL_SURVIVORS,
            affected_surviving_region_ids=("first", "second", "first"),
            changed_surviving_line_ids=("line-1", "line-2"),
        ),
        expected_affected=("first", "second"),
        before_links={"line-1": ("line-2",), "line-2": ("line-1",)},
        after_links={"line-1": (), "line-2": ()},
    ),
    _MatrixCase(
        name="delete-region",
        before={"deleted": ("line-1",), "survivor": ("line-2",)},
        after={"survivor": ("line-2",)},
        delta=StructureRegionDelta(
            invalidation_scope=StructureInvalidationScope.LOCAL_SURVIVORS,
            removed_region_ids=("deleted",),
        ),
        expected_affected=(),
    ),
    _MatrixCase(
        name="identify-existing-and-new",
        before={"existing": ("line-1",), "other": ("line-2",)},
        after={"existing": ("line-1", "line-3"), "new": ("line-4",), "other": ("line-2",)},
        delta=StructureRegionDelta(
            invalidation_scope=StructureInvalidationScope.LOCAL_SURVIVORS,
            affected_surviving_region_ids=("existing",),
            created_region_ids=("new",),
        ),
        expected_affected=("existing",),
    ),
    _MatrixCase(
        name="delete-model-global",
        before={"first": ("line-1",), "removed": ("line-2",)},
        after={"first": ("line-1",), "new": ("line-3",)},
        delta=StructureRegionDelta(
            invalidation_scope=StructureInvalidationScope.ALL_ANALYSIS_CAPABLE_SURVIVORS,
            created_region_ids=("new",),
            removed_region_ids=("removed",),
        ),
        expected_affected=("first",),
    ),
)


@pytest.mark.parametrize("case", _MATRIX_CASES, ids=lambda case: case.name)
def test_revision_matrix(case: _MatrixCase) -> None:
    """Every structure operation should obey the accepted revision matrix."""
    project = _Project(case.before)
    for line_id, links in case.before_links.items():
        project.absorption_lines[line_id].multiplet_ids = list(links)
    artifacts_before = {
        region_id: project.region_analysis_state(region_id).artifact  # type: ignore[union-attr]
        for region_id in case.before
    }

    execution = _execute_case(project, case)

    assert execution.result.changed
    assert execution.result.delta is not None
    assert execution.result.delta.affected_surviving_region_ids == case.expected_affected
    assert execution.postcommit_changes.contains(ModelInvalidated)
    for region_id in case.expected_affected:
        state = project.region_analysis_state(region_id)
        assert state is not None
        assert state.current_revision == AnalysisRevision(2)
        assert state.artifact is artifacts_before[region_id]
    for region_id in case.delta.created_region_ids:
        state = project.region_analysis_state(region_id)
        assert state is not None
        assert state.current_revision == AnalysisRevision()
        assert state.artifact is None
    for region_id in case.delta.removed_region_ids:
        assert project.region_analysis_state(region_id) is None
    stale_region_ids = set(case.expected_affected) | set(case.delta.created_region_ids)
    for region_id, region in project.absorption_regions.items():
        expected_needs = region_id in stale_region_ids
        assert all(
            project.absorption_lines[line_id].needs_optimization is expected_needs
            for line_id in region.line_ids
        )
    assert project.modified == project.committed_modified
    assert project.model.suppression_depth == 0


def test_changed_commit_appends_one_verified_topology_event() -> None:
    """A changed transaction should expose one topology event as its final change."""
    case = next(case for case in _MATRIX_CASES if case.name == "merge")
    project = _Project(case.before)

    execution = _execute_case(project, case)

    assert execution.postcommit_changes.events[-1] == RegionTopologyChanged(
        created_region_ids=case.delta.created_region_ids,
        removed_region_ids=case.delta.removed_region_ids,
        impacted_surviving_region_ids=case.expected_affected,
        changed_surviving_line_ids=case.delta.changed_surviving_line_ids,
    )
    assert len(execution.postcommit_changes.filter(RegionTopologyChanged)) == 1


def test_no_change_is_completely_inert() -> None:
    """NoChange should skip all snapshots, mutation, scopes, rebuild, and history."""
    project = _Project({"region": ("line-1",)})
    calls: list[str] = []

    def unexpected_mutate() -> StructureMutationResult[None]:
        calls.append("mutate")
        return StructureMutationResult.no_change()

    def unexpected_rebuild() -> ChangeSet:
        calls.append("rebuild")
        return ChangeSet.empty()

    execution: AtomicStructureMutationExecution[None] = AtomicStructureMutationExecutor().execute(
        cast("AtomicStructureProjectPort", project),
        preflight=lambda: StructureMutationOutcome.NO_CHANGE,
        capture_runtime=lambda: calls.append("capture"),
        mutate=unexpected_mutate,
        restore_runtime=lambda _snapshot: calls.append("restore"),
        notification_scope=project.model.suppress_notifications,
        rebuild_derived=unexpected_rebuild,
        record_history=lambda _result: calls.append("history"),
        history_scope=lambda: null_history_scope(calls),
    )

    assert not execution.result.changed
    assert not execution.postcommit_changes
    assert not execution.postcommit_changes.contains(RegionTopologyChanged)
    assert calls == []
    assert project.modified == datetime(2020, 1, 1, tzinfo=UTC)


@contextmanager
def null_history_scope(calls: list[str]) -> Iterator[None]:
    """Record entry if a no-change execution incorrectly opens history."""
    calls.append("history-scope")
    yield


@pytest.mark.parametrize(
    "stage",
    [
        "mutation",
        "topology",
        "derived",
        "prune",
        "revision",
        "reset",
        "needs",
        "modified",
        "history",
    ],
)
def test_failure_at_each_stage_restores_project_cache_and_history(stage: str) -> None:
    """Every fallible stage should restore all executor-owned and runtime facts."""
    case = _MatrixCase(
        name="failure-case",
        before={"affected": ("line-1", "line-4"), "removed": ("line-2",)},
        after={"affected": ("line-1",), "created": ("line-3", "line-4")},
        delta=StructureRegionDelta(
            invalidation_scope=StructureInvalidationScope.LOCAL_SURVIVORS,
            affected_surviving_region_ids=("affected",),
            created_region_ids=("created",),
            removed_region_ids=("removed",),
        ),
        expected_affected=("affected",),
    )
    project = _Project(case.before)
    history = _History()
    before = (
        _capture_runtime(project),
        project.stored_region_analysis_states_for_transaction(),
        project.modified,
        project.model.derived_value,
        tuple(history.entries),
    )
    project.fail_stage = stage

    def mutate_override() -> StructureMutationResult[str]:
        _replace_topology(project, case.after)
        if stage == "mutation":
            raise RuntimeError("injected mutation failure")
        delta = case.delta
        if stage == "topology":
            delta = StructureRegionDelta(
                invalidation_scope=StructureInvalidationScope.LOCAL_SURVIVORS,
                affected_surviving_region_ids=("affected",),
            )
        return StructureMutationResult.changed_result(case.name, delta)

    with pytest.raises((RuntimeError, ValueError), match="injected|topology"):
        _execute_case(project, case, history=history, mutate_override=mutate_override)

    after = (
        _capture_runtime(project),
        project.stored_region_analysis_states_for_transaction(),
        project.modified,
        project.model.derived_value,
        tuple(history.entries),
    )
    assert after == before
    assert project.model.suppression_depth == 0
    assert project.model.published_notifications == []


def test_topology_postcondition_failure_restores_every_transaction_owner() -> None:
    """New cross-reference corruption rolls back runtime, evidence, cache, and history."""
    case = _MATRIX_CASES[0]
    project = _Project(case.before)
    history = _History()
    artifact_before = project.region_analysis_state("region")
    assert artifact_before is not None
    artifact_identity = artifact_before.artifact
    before = (
        _capture_runtime(project),
        project.stored_region_analysis_states_for_transaction(),
        project.modified,
        project.model.derived_value,
        tuple(history.entries),
    )

    def corrupt() -> StructureMutationResult[str]:
        _replace_topology(project, case.after)
        project.absorption_lines["line-1"].multiplet_ids.append("missing-line")
        project.absorption_lines["line-1"].needs_optimization = True
        project._states["region"] = _analysis_state("region", revision=99)
        project.modified = project.committed_modified
        project.model.derived_value = 99
        history.entries.append("corrupt")
        project.model.publish("corrupt")
        return StructureMutationResult.changed_result(case.name, case.delta)

    with pytest.raises(ValueError, match="introduced topology violations"):
        _execute_case(project, case, history=history, mutate_override=corrupt)

    after = (
        _capture_runtime(project),
        project.stored_region_analysis_states_for_transaction(),
        project.modified,
        project.model.derived_value,
        tuple(history.entries),
    )
    restored_state = project.region_analysis_state("region")
    assert restored_state is not None
    assert after == before
    assert restored_state.artifact is artifact_identity
    assert project.model.suppression_depth == 0
    assert project.model.published_notifications == []


def test_executor_allows_unchanged_legacy_topology_violation() -> None:
    """A valid unrelated mutation can preserve a pre-existing missing reference."""
    case = _MATRIX_CASES[0]
    project = _Project(case.before)
    project.absorption_lines["line-1"].multiplet_ids.append("legacy-missing-line")

    execution = _execute_case(project, case)

    assert execution.result.changed
    assert project.absorption_lines["line-1"].multiplet_ids == ["legacy-missing-line"]


def test_history_success_exit_failure_restores_all_scientific_state() -> None:
    """A history-scope exit failure is still part of the atomic transaction."""
    case = _MATRIX_CASES[0]
    project = _Project(case.before)
    history = _History()
    history.fail_on_success_exit = True
    before = (
        _capture_runtime(project),
        project.stored_region_analysis_states_for_transaction(),
        project.modified,
        project.model.derived_value,
        tuple(history.entries),
    )

    with pytest.raises(RuntimeError, match="history exit"):
        _execute_case(project, case, history=history)

    after = (
        _capture_runtime(project),
        project.stored_region_analysis_states_for_transaction(),
        project.modified,
        project.model.derived_value,
        tuple(history.entries),
    )
    assert after == before
    assert project.model.suppression_depth == 0
    assert project.model.published_notifications == []


def test_notification_scope_success_exit_failure_rolls_back_silently() -> None:
    """A transaction-scope exit failure still restores state without observer leaks."""
    case = _MATRIX_CASES[0]
    project = _Project(case.before)
    history = _History()
    project.model.fail_scope_exit_calls.add(1)
    before = (
        _capture_runtime(project),
        project.stored_region_analysis_states_for_transaction(),
        project.modified,
        project.model.derived_value,
        tuple(history.entries),
    )

    with pytest.raises(RuntimeError, match="notification scope exit failure 1"):
        _execute_case(project, case, history=history)

    after = (
        _capture_runtime(project),
        project.stored_region_analysis_states_for_transaction(),
        project.modified,
        project.model.derived_value,
        tuple(history.entries),
    )
    assert after == before
    assert project.model.suppression_depth == 0
    assert project.model.published_notifications == []


@pytest.mark.parametrize("stage", ["mutation", "rebuild", "history", "scope-exit"])
def test_failed_transaction_never_reaches_caller_publish_boundary(stage: str) -> None:
    """No fallible transaction stage may return a change set for publication."""
    case = next(case for case in _MATRIX_CASES if case.name == "merge")
    project = _Project(case.before)
    if stage == "rebuild":
        project.fail_stage = "derived"
    elif stage == "history":
        project.fail_stage = "history"
    elif stage == "scope-exit":
        project.model.fail_scope_exit_calls.add(1)

    def mutate() -> StructureMutationResult[str]:
        _replace_topology(project, case.after)
        if stage == "mutation":
            raise RuntimeError("injected mutation failure")
        return StructureMutationResult.changed_result(case.name, case.delta)

    published: list[ChangeSet] = []
    with pytest.raises(RuntimeError, match="injected"):
        execution = _execute_case(project, case, mutate_override=mutate)
        published.append(execution.postcommit_changes)

    assert published == []


def test_rollback_scope_exit_failure_keeps_original_error_and_restored_state() -> None:
    """Rollback-scope exit failure is a note, not a replacement exception."""
    case = _MATRIX_CASES[0]
    project = _Project(case.before)
    project.model.fail_scope_exit_calls.add(2)
    before = (
        _capture_runtime(project),
        project.stored_region_analysis_states_for_transaction(),
        project.modified,
        project.model.derived_value,
    )

    def mutate() -> StructureMutationResult[str]:
        _replace_topology(project, case.after)
        raise RuntimeError("injected mutation failure")

    with pytest.raises(RuntimeError, match="injected mutation failure") as captured:
        _execute_case(project, case, mutate_override=mutate)

    after = (
        _capture_runtime(project),
        project.stored_region_analysis_states_for_transaction(),
        project.modified,
        project.model.derived_value,
    )
    assert after == before
    assert any(
        "notification-suppressed structure transaction rollback" in note
        and "notification scope exit failure 2" in note
        for note in captured.value.__notes__
    )
    assert project.model.suppression_depth == 0
    assert project.model.published_notifications == []


def test_rollback_scope_entry_failure_keeps_original_error_with_note() -> None:
    """A rollback suppression re-entry failure cannot replace the mutation error."""
    case = _MATRIX_CASES[0]
    project = _Project(case.before)
    project.model.fail_scope_entry_calls.add(2)

    def mutate() -> StructureMutationResult[str]:
        _replace_topology(project, case.after)
        raise RuntimeError("injected mutation failure")

    with pytest.raises(RuntimeError, match="injected mutation failure") as captured:
        _execute_case(project, case, mutate_override=mutate)

    assert any(
        "notification-suppressed structure transaction rollback" in note
        and "notification scope entry failure 2" in note
        for note in captured.value.__notes__
    )
    assert project.model.suppression_depth == 0
    assert project.model.published_notifications == []


def test_mutation_cannot_reorder_surviving_explicit_analysis_states() -> None:
    """Executor-owned state snapshots include exact insertion order."""
    case = _MatrixCase(
        name="state-reorder",
        before={"source": ("line-1", "line-2"), "target": ("line-3",), "other": ("line-4",)},
        after={"source": ("line-2",), "target": ("line-3", "line-1"), "other": ("line-4",)},
        delta=StructureRegionDelta(
            invalidation_scope=StructureInvalidationScope.LOCAL_SURVIVORS,
            affected_surviving_region_ids=("source", "target"),
        ),
        expected_affected=(),
    )
    project = _Project(case.before)
    before_states = project.stored_region_analysis_states_for_transaction()

    def mutate() -> StructureMutationResult[str]:
        _replace_topology(project, case.after)
        project._states = dict(reversed(tuple(project._states.items())))
        return StructureMutationResult.changed_result(case.name, case.delta)

    with pytest.raises(ValueError, match="analysis state outside the executor"):
        _execute_case(project, case, mutate_override=mutate)

    assert project.stored_region_analysis_states_for_transaction() == before_states


@pytest.mark.parametrize(
    "corrupt",
    [
        lambda project: project.absorption_regions["target"].line_ids.append("line-1"),
        lambda project: project.absorption_regions["target"].line_ids.append("missing"),
        lambda project: setattr(project.absorption_lines["line-1"], "region_id", "source"),
        lambda project: project.absorption_regions["source"].line_ids.append("line-1"),
        lambda project: project.absorption_lines.__setitem__("orphan", _line("orphan", "target")),
        lambda project: setattr(project.absorption_regions["target"], "region_id", "wrong"),
        lambda project: setattr(project.absorption_lines["line-1"], "line_id", "wrong"),
    ],
    ids=[
        "duplicate-in-region",
        "missing-line-reference",
        "mismatched-line-region",
        "line-in-multiple-regions",
        "unlisted-line",
        "region-mapping-key-mismatch",
        "line-mapping-key-mismatch",
    ],
)
def test_invalid_after_topology_rolls_back(corrupt: Callable[[_Project], object]) -> None:
    """All line-to-region assignment invariants are checked before commit."""
    case = next(case for case in _MATRIX_CASES if case.name == "move-existing")
    project = _Project(case.before)
    before = _capture_runtime(project)

    def mutate() -> StructureMutationResult[str]:
        _replace_topology(project, case.after)
        corrupt(project)
        return StructureMutationResult.changed_result(case.name, case.delta)

    with pytest.raises(ValueError):
        _execute_case(project, case, mutate_override=mutate)

    assert _capture_runtime(project) == before


@pytest.mark.parametrize(
    "declared_affected",
    [("source",), ("source", "target", "unrelated")],
    ids=["omits-changed-survivor", "adds-unchanged-survivor"],
)
def test_local_scope_requires_exact_membership_changed_survivors(
    declared_affected: tuple[str, ...],
) -> None:
    """Local callers can neither omit changed survivors nor add unchanged ones."""
    case = _MatrixCase(
        name="invalid-local-membership",
        before={"source": ("line-1", "line-2"), "target": ("line-3",), "unrelated": ("line-4",)},
        after={"source": ("line-2",), "target": ("line-3", "line-1"), "unrelated": ("line-4",)},
        delta=StructureRegionDelta(
            invalidation_scope=StructureInvalidationScope.LOCAL_SURVIVORS,
            affected_surviving_region_ids=declared_affected,
        ),
        expected_affected=(),
    )
    project = _Project(case.before)
    before = _capture_runtime(project)

    with pytest.raises(ValueError, match="line-membership changes"):
        _execute_case(project, case)

    assert _capture_runtime(project) == before


def test_changed_result_accepts_exact_line_order_mutation() -> None:
    """Line ordering is part of the exact scientific structure state."""
    case = _MatrixCase(
        name="display-order-only",
        before={"region": ("line-1", "line-2")},
        after={"region": ("line-2", "line-1")},
        delta=StructureRegionDelta(
            invalidation_scope=StructureInvalidationScope.LOCAL_SURVIVORS,
            affected_surviving_region_ids=("region",),
        ),
        expected_affected=("region",),
    )
    project = _Project(case.before)

    execution = _execute_case(project, case)

    assert execution.result.delta is not None
    assert execution.result.delta.affected_surviving_region_ids == ("region",)
    assert tuple(project.absorption_regions["region"].line_ids) == ("line-2", "line-1")


def test_global_scope_rejects_caller_supplied_affected_regions_and_rolls_back() -> None:
    """Global affected survivors must be derived from actual after topology."""
    case = _MatrixCase(
        name="invalid-global",
        before={"region": ("line-1",)},
        after={"region": ("line-1",)},
        delta=StructureRegionDelta(
            invalidation_scope=StructureInvalidationScope.ALL_ANALYSIS_CAPABLE_SURVIVORS,
            affected_surviving_region_ids=("region",),
        ),
        expected_affected=("region",),
    )
    project = _Project(case.before)
    before = _capture_runtime(project)

    with pytest.raises(ValueError, match="let the executor resolve"):
        _execute_case(project, case)

    assert _capture_runtime(project) == before


def test_history_recording_requires_an_atomic_scope() -> None:
    """A recorder cannot be accepted without a matching history rollback owner."""
    project = _Project({"region": ("line-1",)})
    with pytest.raises(ValueError, match="requires a rollback scope"):
        AtomicStructureMutationExecutor().execute(
            cast("AtomicStructureProjectPort", project),
            preflight=lambda: StructureMutationOutcome.NO_CHANGE,
            capture_runtime=lambda: _capture_runtime(project),
            mutate=lambda: StructureMutationResult[str].no_change(),
            restore_runtime=lambda snapshot: _restore_runtime(project, snapshot),
            notification_scope=project.model.suppress_notifications,
            rebuild_derived=ChangeSet.empty,
            record_history=lambda _result: None,
        )
