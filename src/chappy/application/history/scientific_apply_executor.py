"""Atomic scientific storage transitions for successful Undo and Redo."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from chappy.application.analysis_artifacts import (
    AnalysisArtifactStorePort,
    AnalysisArtifactStoreUseCase,
    AnalysisMutationImpact,
    AnalysisMutationOutcome,
)
from chappy.core.change_set import ChangeSet as DomainChangeSet

from .models import HistoryApplyError, HistoryApplyErrorCode, HistoryApplyResult

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager
    from datetime import datetime

    from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
    from chappy.core.analysis import RegionAnalysisState


class ScientificHistoryScopeKind(StrEnum):
    """How a scientific history command selects affected analysis regions."""

    ALL_ANALYSIS_CAPABLE = "all_analysis_capable"
    REGIONS = "regions"


@dataclass(frozen=True, slots=True)
class ScientificHistoryScope:
    """Typed affected-region scope for one scientific Undo or Redo."""

    kind: ScientificHistoryScopeKind
    region_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Normalize local identities and reject contradictory scopes."""
        normalized = tuple(dict.fromkeys(self.region_ids))
        object.__setattr__(self, "region_ids", normalized)
        if self.kind is ScientificHistoryScopeKind.ALL_ANALYSIS_CAPABLE and normalized:
            msg = "A global scientific history scope cannot name individual regions."
            raise ValueError(msg)
        if self.kind is ScientificHistoryScopeKind.REGIONS and (
            not normalized or any(not region_id for region_id in normalized)
        ):
            msg = "A region scientific history scope requires non-empty region identities."
            raise ValueError(msg)

    @classmethod
    def all_analysis_capable(cls) -> ScientificHistoryScope:
        """Build a scope covering every currently analysis-capable region."""
        return cls(kind=ScientificHistoryScopeKind.ALL_ANALYSIS_CAPABLE)

    @classmethod
    def regions(cls, *region_ids: str) -> ScientificHistoryScope:
        """Build a scope covering specified surviving regions."""
        return cls(kind=ScientificHistoryScopeKind.REGIONS, region_ids=region_ids)


class ScientificHistoryProjectPort(AnalysisArtifactStorePort, Protocol):
    """Project facts owned by an atomic scientific history application."""

    modified: datetime
    absorption_lines: dict[str, AbsorptionLine]
    absorption_regions: dict[str, AbsorptionRegion]

    def mark_region_needs_optimization(self, region_id: str) -> int:
        """Mark every line in one region as requiring another analysis."""
        ...

    def mark_scientific_modified(self) -> None:
        """Record a committed scientific storage mutation."""
        ...

    def stored_region_analysis_states_for_transaction(self) -> tuple[RegionAnalysisState, ...]:
        """Return exact explicitly stored analysis state and order."""
        ...

    def replace_region_analysis_states_for_transaction(
        self, states: tuple[RegionAnalysisState, ...]
    ) -> None:
        """Restore exact explicitly stored analysis state and order."""
        ...


@dataclass(frozen=True, slots=True)
class ScientificHistoryApplyExecution:
    """Committed scientific history result and post-commit domain changes."""

    result: HistoryApplyResult
    impact: AnalysisMutationImpact
    domain_changes: DomainChangeSet


@dataclass(frozen=True, slots=True)
class _ScientificHistoryProjectSnapshot:
    """Exact project-owned facts restored after an executor failure."""

    modified: datetime
    analysis_states: tuple[RegionAnalysisState, ...]
    optimization_flags: tuple[tuple[str, bool], ...]


class ScientificHistoryApplyExecutor:
    """Apply mutation, derived state, and freshness invalidation atomically.

    Runtime snapshots are command-specific callbacks. GUI refresh and domain
    observer dispatch are intentionally excluded and run only after commit.
    """

    def __init__(self, *, artifacts: AnalysisArtifactStoreUseCase | None = None) -> None:
        """Initialize with the canonical project-owned artifact transitions."""
        self._artifacts = artifacts or AnalysisArtifactStoreUseCase()

    def execute[TRuntime](
        self,
        project: ScientificHistoryProjectPort,
        scope: ScientificHistoryScope,
        *,
        preflight: Callable[[], AnalysisMutationOutcome],
        capture_runtime: Callable[[], TRuntime],
        mutate: Callable[[], HistoryApplyResult],
        restore_runtime: Callable[[TRuntime], None],
        rebuild_derived: Callable[[], DomainChangeSet] | None = None,
        notification_scope: Callable[[], AbstractContextManager[None]] | None = None,
    ) -> ScientificHistoryApplyExecution:
        """Execute one scientific Undo/Redo with exact failure rollback."""
        outcome = preflight()
        region_ids = self._resolve_region_ids(project, scope)
        if outcome is AnalysisMutationOutcome.NO_CHANGE:
            return ScientificHistoryApplyExecution(
                result=HistoryApplyResult.ok(),
                impact=AnalysisMutationImpact.no_change(),
                domain_changes=DomainChangeSet.empty(),
            )

        project_snapshot = self._snapshot_project(project)
        runtime_snapshot = capture_runtime()
        notification_context = notification_scope or nullcontext
        try:
            with notification_context():
                result = self._require_success(mutate())
                domain_changes = (
                    rebuild_derived() if rebuild_derived is not None else DomainChangeSet.empty()
                )
                self._artifacts.invalidate_regions(project, region_ids)
                for region_id in region_ids:
                    project.mark_region_needs_optimization(region_id)
                project.mark_scientific_modified()
        except Exception as original_error:
            failure = original_error

            def rollback() -> None:
                with notification_context():
                    self._attempt_restore(
                        failure, "command runtime state", lambda: restore_runtime(runtime_snapshot)
                    )
                    self._attempt_restore(
                        failure,
                        "analysis revisions and artifacts",
                        lambda: project.replace_region_analysis_states_for_transaction(
                            project_snapshot.analysis_states
                        ),
                    )
                    self._attempt_restore(
                        failure,
                        "line optimization flags",
                        lambda: self._restore_optimization_flags(
                            project, project_snapshot.optimization_flags
                        ),
                    )
                    self._attempt_restore(
                        failure,
                        "project modified timestamp",
                        lambda: setattr(project, "modified", project_snapshot.modified),
                    )

            self._attempt_restore(
                failure, "notification-suppressed transaction rollback", rollback
            )
            raise

        return ScientificHistoryApplyExecution(
            result=result,
            impact=AnalysisMutationImpact.changed_regions(affected_region_ids=region_ids),
            domain_changes=domain_changes,
        )

    @staticmethod
    def _require_success(result: HistoryApplyResult) -> HistoryApplyResult:
        """Return a successful mutation result or raise its typed failure."""
        if not result.success:
            error_code = result.error_code or HistoryApplyErrorCode.INVALID_STATE
            raise HistoryApplyError(
                error_code, f"Scientific history mutation failed: {error_code}"
            )
        return result

    @staticmethod
    def _resolve_region_ids(
        project: ScientificHistoryProjectPort, scope: ScientificHistoryScope
    ) -> tuple[str, ...]:
        """Resolve and preflight every affected region before mutation."""
        if scope.kind is ScientificHistoryScopeKind.ALL_ANALYSIS_CAPABLE:
            return tuple(
                state.region_id
                for state in project.region_analysis_states()
                if project.is_region_analysis_capable(state.region_id)
            )

        for region_id in scope.region_ids:
            if project.region_analysis_state(region_id) is None:
                raise HistoryApplyError(
                    HistoryApplyErrorCode.TARGET_NOT_FOUND,
                    f"Scientific history region not found: {region_id}",
                )
            if not project.is_region_analysis_capable(region_id):
                raise HistoryApplyError(
                    HistoryApplyErrorCode.INVALID_STATE,
                    f"Scientific history region is not analysis-capable: {region_id}",
                )
        return scope.region_ids

    @staticmethod
    def _snapshot_project(
        project: ScientificHistoryProjectPort,
    ) -> _ScientificHistoryProjectSnapshot:
        """Capture every project-owned freshness fact before mutation."""
        return _ScientificHistoryProjectSnapshot(
            modified=project.modified,
            analysis_states=project.stored_region_analysis_states_for_transaction(),
            optimization_flags=tuple(
                (line_id, line.needs_optimization)
                for line_id, line in project.absorption_lines.items()
            ),
        )

    @staticmethod
    def _restore_optimization_flags(
        project: ScientificHistoryProjectPort, flags: tuple[tuple[str, bool], ...]
    ) -> None:
        """Restore every snapshotted line flag exactly."""
        for line_id, needs_optimization in flags:
            line = project.absorption_lines.get(line_id)
            if line is None:
                msg = f"History rollback line not found: {line_id}"
                raise RuntimeError(msg)
            line.needs_optimization = needs_optimization

    @staticmethod
    def _attempt_restore(
        original_error: Exception, label: str, restore: Callable[[], None]
    ) -> None:
        """Attempt one rollback stage without replacing the triggering error."""
        try:
            restore()
        except Exception as rollback_error:  # noqa: BLE001 - preserve original failure
            original_error.add_note(
                f"Failed to restore {label}: {type(rollback_error).__name__}: {rollback_error}"
            )


__all__ = [
    "ScientificHistoryApplyExecution",
    "ScientificHistoryApplyExecutor",
    "ScientificHistoryProjectPort",
    "ScientificHistoryScope",
    "ScientificHistoryScopeKind",
]
