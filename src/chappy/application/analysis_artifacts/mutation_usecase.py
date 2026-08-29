"""Atomic analysis invalidation for scientific project mutations."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Protocol

from chappy.application.analysis_artifacts.ports import AnalysisArtifactStorePort
from chappy.application.analysis_artifacts.postcommit import run_postcommit_actions_isolated
from chappy.application.analysis_artifacts.store_usecase import AnalysisArtifactStoreUseCase
from chappy.core.change_set import ChangeSet
from chappy.core.events import ModelInvalidated, ModelUpdated

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from contextlib import AbstractContextManager
    from datetime import datetime

    from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
    from chappy.core.analysis import RegionAnalysisState
    from chappy.core.spectrum_model import SpectrumModel


class AnalysisMutationOutcome(Enum):
    """Whether a scientific command changed project analysis inputs."""

    CHANGED = "changed"
    NO_CHANGE = "no_change"


@dataclass(frozen=True, slots=True)
class AnalysisMutationImpact:
    """Region identities affected by one atomic scientific command."""

    outcome: AnalysisMutationOutcome
    affected_region_ids: tuple[str, ...] = ()
    created_region_ids: tuple[str, ...] = ()
    removed_region_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Normalize identity sets while preserving their first-seen order."""
        object.__setattr__(
            self, "affected_region_ids", tuple(dict.fromkeys(self.affected_region_ids))
        )
        object.__setattr__(
            self, "created_region_ids", tuple(dict.fromkeys(self.created_region_ids))
        )
        object.__setattr__(
            self, "removed_region_ids", tuple(dict.fromkeys(self.removed_region_ids))
        )
        if self.outcome is AnalysisMutationOutcome.NO_CHANGE and (
            self.affected_region_ids or self.created_region_ids or self.removed_region_ids
        ):
            msg = "A no-change analysis mutation cannot affect region identities."
            raise ValueError(msg)

    @property
    def changed(self) -> bool:
        """Return whether the command changed scientific inputs."""
        return self.outcome is AnalysisMutationOutcome.CHANGED

    @classmethod
    def no_change(cls) -> AnalysisMutationImpact:
        """Build an impact for a command rejected before scientific mutation."""
        return cls(outcome=AnalysisMutationOutcome.NO_CHANGE)

    @classmethod
    def changed_regions(
        cls,
        *,
        affected_region_ids: tuple[str, ...] = (),
        created_region_ids: tuple[str, ...] = (),
        removed_region_ids: tuple[str, ...] = (),
    ) -> AnalysisMutationImpact:
        """Build a normalized impact for a successful scientific mutation."""
        return cls(
            outcome=AnalysisMutationOutcome.CHANGED,
            affected_region_ids=affected_region_ids,
            created_region_ids=created_region_ids,
            removed_region_ids=removed_region_ids,
        )


class GlobalAnalysisMutationProjectPort(AnalysisArtifactStorePort, Protocol):
    """Project state required by a global scientific mutation transaction."""

    modified: datetime
    absorption_lines: dict[str, AbsorptionLine]
    model: SpectrumModel

    def mark_region_needs_optimization(self, region_id: str) -> int:
        """Mark every line in one affected region as requiring analysis."""
        ...

    def mark_scientific_modified(self) -> None:
        """Record a committed scientific mutation even without capable regions."""
        ...

    def stored_region_analysis_states_for_transaction(self) -> tuple[RegionAnalysisState, ...]:
        """Return the exact explicitly stored analysis-state sequence."""
        ...

    def replace_region_analysis_states_for_transaction(
        self, states: Iterable[RegionAnalysisState]
    ) -> None:
        """Replace the exact explicitly stored analysis-state sequence."""
        ...


class RegionLocalMutationProjectPort(AnalysisArtifactStorePort, Protocol):
    """Project state required by a region-local scientific transaction."""

    modified: datetime
    absorption_lines: dict[str, AbsorptionLine]
    absorption_regions: dict[str, AbsorptionRegion]

    def mark_region_needs_optimization(self, region_id: str) -> int:
        """Mark every line in one affected region as requiring analysis."""
        ...

    def stored_region_analysis_states_for_transaction(self) -> tuple[RegionAnalysisState, ...]:
        """Return the exact explicitly stored analysis-state sequence."""
        ...

    def replace_region_analysis_states_for_transaction(
        self, states: Iterable[RegionAnalysisState]
    ) -> None:
        """Replace the exact explicitly stored analysis-state sequence."""
        ...


@dataclass(frozen=True, slots=True)
class RegionLocalMutationRequest:
    """Stable region identities affected by one local scientific mutation."""

    affected_region_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        """Deduplicate identities while rejecting an empty transaction scope."""
        normalized = tuple(dict.fromkeys(self.affected_region_ids))
        if not normalized or any(not region_id for region_id in normalized):
            msg = "A region-local mutation requires at least one region identity."
            raise ValueError(msg)
        object.__setattr__(self, "affected_region_ids", normalized)


@dataclass(frozen=True, slots=True)
class RegionLocalMutationResult:
    """Typed outcome of one region-local scientific transaction."""

    impact: AnalysisMutationImpact

    @property
    def changed(self) -> bool:
        """Return whether scientific state committed."""
        return self.impact.changed


@dataclass(frozen=True, slots=True)
class _RegionLocalMutationSnapshot:
    """Exact project state restored if a local transaction fails."""

    modified: datetime
    analysis_states: tuple[RegionAnalysisState, ...]
    optimization_flags: tuple[tuple[str, bool], ...]


class RegionLocalAtomicMutationUseCase:
    """Commit one local mutation, invalidation, and history atomically."""

    def __init__(self, *, artifacts: AnalysisArtifactStoreUseCase | None = None) -> None:
        """Initialize with the canonical project-owned artifact service."""
        self._artifacts = artifacts or AnalysisArtifactStoreUseCase()

    def execute(
        self,
        project: RegionLocalMutationProjectPort,
        request: RegionLocalMutationRequest,
        *,
        mutate: Callable[[], bool],
        rollback: Callable[[], None],
        record_history: Callable[[], None] | None = None,
        history_scope: Callable[[], AbstractContextManager[None]] | None = None,
    ) -> RegionLocalMutationResult:
        """Apply one local scientific mutation inside an exact rollback boundary.

        Notifications and view refreshes are deliberately excluded. Callers emit
        them only after this method returns so observer failures cannot revert an
        accepted scientific mutation.
        """
        if record_history is not None and history_scope is None:
            msg = "Region-local history recording requires a rollback scope."
            raise ValueError(msg)

        region_ids = request.affected_region_ids
        self._validate_regions(project, region_ids)
        snapshot = self._snapshot(project, region_ids)
        mutation_started = False
        try:
            mutation_started = True
            if not mutate():
                return RegionLocalMutationResult(impact=AnalysisMutationImpact.no_change())

            def commit_analysis_and_history() -> None:
                self._artifacts.invalidate_regions(project, region_ids)
                for region_id in region_ids:
                    project.mark_region_needs_optimization(region_id)
                if record_history is not None:
                    record_history()

            if history_scope is None:
                commit_analysis_and_history()
            else:
                with history_scope():
                    commit_analysis_and_history()
        except Exception as original_error:
            if mutation_started:
                self._attempt_restore(original_error, "scientific mutation", rollback)
            self._attempt_restore(
                original_error,
                "analysis revisions and artifacts",
                lambda: project.replace_region_analysis_states_for_transaction(
                    snapshot.analysis_states
                ),
            )
            self._attempt_restore(
                original_error,
                "line optimization flags",
                lambda: self._restore_optimization_flags(project, snapshot.optimization_flags),
            )
            self._attempt_restore(
                original_error,
                "project modified timestamp",
                lambda: setattr(project, "modified", snapshot.modified),
            )
            raise

        return RegionLocalMutationResult(
            impact=AnalysisMutationImpact.changed_regions(affected_region_ids=region_ids)
        )

    @staticmethod
    def _validate_regions(
        project: RegionLocalMutationProjectPort, region_ids: tuple[str, ...]
    ) -> None:
        """Reject missing or scientifically incomplete regions before mutation."""
        for region_id in region_ids:
            if region_id not in project.absorption_regions:
                msg = f"Analysis region not found: {region_id}"
                raise ValueError(msg)
            if not project.is_region_analysis_capable(region_id):
                msg = f"Analysis region is not capable: {region_id}"
                raise ValueError(msg)

    @staticmethod
    def _snapshot(
        project: RegionLocalMutationProjectPort, region_ids: tuple[str, ...]
    ) -> _RegionLocalMutationSnapshot:
        """Capture every project fact owned by the local transaction."""
        line_ids = tuple(
            dict.fromkeys(
                line_id
                for region_id in region_ids
                for line_id in project.absorption_regions[region_id].line_ids
            )
        )
        return _RegionLocalMutationSnapshot(
            modified=project.modified,
            analysis_states=project.stored_region_analysis_states_for_transaction(),
            optimization_flags=tuple(
                (line_id, project.absorption_lines[line_id].needs_optimization)
                for line_id in line_ids
            ),
        )

    @staticmethod
    def _attempt_restore(
        original_error: Exception, label: str, restore: Callable[[], None]
    ) -> None:
        """Attempt one rollback stage without replacing the triggering failure."""
        try:
            restore()
        except Exception as rollback_error:  # noqa: BLE001 - preserve the original failure
            original_error.add_note(
                f"Failed to restore {label}: {type(rollback_error).__name__}: {rollback_error}"
            )

    @staticmethod
    def _restore_optimization_flags(
        project: RegionLocalMutationProjectPort, flags: tuple[tuple[str, bool], ...]
    ) -> None:
        """Restore every affected-line flag or report invalid topology mutation."""
        missing_line_ids = tuple(
            line_id
            for line_id, _needs_optimization in flags
            if line_id not in project.absorption_lines
        )
        if missing_line_ids:
            missing = ", ".join(missing_line_ids)
            msg = (
                "Cannot restore optimization flags after a non-structure transaction; "
                f"lines disappeared: {missing}"
            )
            raise RuntimeError(msg)
        for line_id, needs_optimization in flags:
            project.absorption_lines[line_id].needs_optimization = needs_optimization


class GlobalAnalysisMutationUseCase:
    """Commit a global scientific mutation and invalidate every capable region."""

    def __init__(self, *, artifacts: AnalysisArtifactStoreUseCase | None = None) -> None:
        """Initialize with the canonical project-owned artifact transition service."""
        self._artifacts = artifacts or AnalysisArtifactStoreUseCase()

    def execute(
        self,
        project: GlobalAnalysisMutationProjectPort,
        *,
        mutate: Callable[[], bool],
        rollback: Callable[[], None],
        record_history: Callable[[], None] | None = None,
        history_scope: Callable[[], AbstractContextManager[None]] | None = None,
        postcommit_changes: Callable[[], ChangeSet] | None = None,
    ) -> AnalysisMutationImpact:
        """Apply science, derived state, invalidation, and history atomically.

        Model, component, and tie observers are suppressed until derived state,
        analysis invalidation, modified time, and history have all committed.
        One isolated model change set is published after the rollback boundary.
        """
        if record_history is not None and history_scope is None:
            msg = "Global history recording requires a rollback scope."
            raise ValueError(msg)

        analysis_states_before = project.stored_region_analysis_states_for_transaction()
        optimization_flags_before = tuple(
            (line_id, line.needs_optimization)
            for line_id, line in project.absorption_lines.items()
        )
        modified_before = project.modified
        derived_before = project.model.snapshot_derived_state_for_transaction()
        mutation_started = False
        history_context = history_scope() if history_scope is not None else nullcontext()
        try:
            with history_context, project.model.suppress_scientific_notifications():
                mutation_started = True
                if not mutate():
                    return AnalysisMutationImpact.no_change()

                project.model.rebuild_model_storage()
                affected_region_ids: tuple[str, ...] = ()

                def commit_analysis_and_history() -> None:
                    nonlocal affected_region_ids
                    affected_region_ids = self._artifacts.invalidate_all_analysis_capable(project)
                    for region_id in affected_region_ids:
                        project.mark_region_needs_optimization(region_id)
                    project.mark_scientific_modified()
                    if record_history is not None:
                        record_history()

                commit_analysis_and_history()
        except Exception as original_error:
            transaction_error = original_error

            def rollback_transaction() -> None:
                with project.model.suppress_scientific_notifications():
                    if mutation_started:
                        self._attempt_restore(transaction_error, "scientific mutation", rollback)
                    self._attempt_restore(
                        transaction_error,
                        "analysis revisions and artifacts",
                        lambda: project.replace_region_analysis_states_for_transaction(
                            analysis_states_before
                        ),
                    )
                    self._attempt_restore(
                        transaction_error,
                        "line optimization flags",
                        lambda: self._restore_optimization_flags(
                            project, optimization_flags_before
                        ),
                    )
                    self._attempt_restore(
                        transaction_error,
                        "project modified timestamp",
                        lambda: setattr(project, "modified", modified_before),
                    )
                    self._attempt_restore(
                        transaction_error,
                        "derived model cache",
                        lambda: project.model.restore_derived_state_for_transaction(
                            derived_before
                        ),
                    )

            self._attempt_restore(
                original_error,
                "notification-suppressed transaction rollback",
                rollback_transaction,
            )
            raise

        impact = AnalysisMutationImpact.changed_regions(affected_region_ids=affected_region_ids)

        def publish_postcommit_changes() -> None:
            change_set = (
                postcommit_changes()
                if postcommit_changes is not None
                else ChangeSet.of(ModelInvalidated(), ModelUpdated())
            )
            project.model.publish_storage_changes(change_set)

        run_postcommit_actions_isolated(publish_postcommit_changes)
        return impact

    @staticmethod
    def _attempt_restore(
        original_error: Exception, label: str, restore: Callable[[], None]
    ) -> None:
        """Attempt one rollback stage without replacing the triggering failure."""
        try:
            restore()
        except Exception as rollback_error:  # noqa: BLE001 - rollback must preserve original error
            original_error.add_note(
                f"Failed to restore {label}: {type(rollback_error).__name__}: {rollback_error}"
            )

    @staticmethod
    def _restore_optimization_flags(
        project: GlobalAnalysisMutationProjectPort, flags: tuple[tuple[str, bool], ...]
    ) -> None:
        """Restore every line flag or report invalid topology mutation."""
        missing_line_ids = tuple(
            line_id
            for line_id, _needs_optimization in flags
            if line_id not in project.absorption_lines
        )
        if missing_line_ids:
            missing = ", ".join(missing_line_ids)
            msg = (
                "Cannot restore optimization flags after a non-structure transaction; "
                f"lines disappeared: {missing}"
            )
            raise RuntimeError(msg)
        for line_id, needs_optimization in flags:
            project.absorption_lines[line_id].needs_optimization = needs_optimization


__all__ = [
    "AnalysisMutationImpact",
    "AnalysisMutationOutcome",
    "GlobalAnalysisMutationProjectPort",
    "GlobalAnalysisMutationUseCase",
    "RegionLocalAtomicMutationUseCase",
    "RegionLocalMutationProjectPort",
    "RegionLocalMutationRequest",
    "RegionLocalMutationResult",
]
