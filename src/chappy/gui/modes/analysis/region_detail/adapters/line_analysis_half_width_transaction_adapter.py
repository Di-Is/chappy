"""Optimize adapter for atomic line analysis half-width edits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from chappy.application.analysis_artifacts import (
    RegionLocalAtomicMutationUseCase,
    RegionLocalMutationRequest,
    run_postcommit_actions_isolated,
)
from chappy.application.history import LineAnalysisHalfWidthStateSnapshot

if TYPE_CHECKING:
    from collections.abc import Callable

    from chappy.application.optimize.models import PreparedLineAnalysisHalfWidthChange
    from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
    from chappy.core.components.absorber import AbsorberComponent
    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.modes.analysis.region_detail.adapters.history_adapter import (
        OptimizeHistoryAdapter,
    )
    from chappy.gui.modes.analysis.region_detail.group_selection_controller import (
        OptimizeGroupSelectionController,
    )


@dataclass(frozen=True, slots=True)
class _TransactionSnapshot:
    """State restored if any commit collaborator fails."""

    line_states: tuple[LineAnalysisHalfWidthStateSnapshot, ...]
    region_analysis_range: tuple[float, float] | None


class OptimizeLineAnalysisHalfWidthTransactionAdapter:
    """Read project state and commit one analysis half-width transaction."""

    def __init__(
        self,
        *,
        project_provider: Callable[[], SpectroscopyProject | None],
        group_controller: OptimizeGroupSelectionController,
        history: OptimizeHistoryAdapter,
        transaction: RegionLocalAtomicMutationUseCase | None = None,
    ) -> None:
        """Initialize the adapter with mode-owned collaborators."""
        self._project_provider = project_provider
        self._group_controller = group_controller
        self._history = history
        self._transaction = transaction or RegionLocalAtomicMutationUseCase()

    def analysis_line(self, line_id: str) -> AbsorptionLine | None:
        """Return a current absorption line by identifier."""
        project = self._project_provider()
        return project.absorption_lines.get(line_id) if project is not None else None

    def analysis_region(self, region_id: str) -> AbsorptionRegion | None:
        """Return a current absorption region by identifier."""
        project = self._project_provider()
        return project.absorption_regions.get(region_id) if project is not None else None

    def expand_analysis_multiplet_line_ids(self, seed_line_id: str) -> tuple[str, ...]:
        """Expand linked lines using the canonical project multiplet service."""
        project = self._require_project()
        return tuple(project.expand_multiplet_line_ids([seed_line_id]))

    def analysis_component(self, component_id: str) -> AbsorberComponent | None:
        """Return a current absorber component by identifier."""
        project = self._project_provider()
        return project.find_absorber_component(component_id) if project is not None else None

    def execute_line_analysis_half_width_change(
        self, change: PreparedLineAnalysisHalfWidthChange
    ) -> None:
        """Commit project mutation, invalidation, and history atomically."""
        project = self._require_project()
        snapshot = self._snapshot(project, change)

        def mutate() -> bool:
            for line_change in change.line_changes:
                line = project.absorption_lines[line_change.line_id]
                line.window_kms = line_change.after_half_width.kms
                line.lambda_range = line_change.after_lambda_range
            project.absorption_regions[
                change.region_id
            ].analysis_range = change.after_region_analysis_range
            return True

        def record_history() -> None:
            self._history.record_line_analysis_half_width_change(
                tuple(item.line_id for item in change.line_changes),
                snapshot.line_states,
                tuple(
                    LineAnalysisHalfWidthStateSnapshot(
                        line_id=item.line_id,
                        half_width_kms=item.after_half_width.kms,
                        lambda_range=item.after_lambda_range,
                    )
                    for item in change.line_changes
                ),
                change.region_id,
            )

        self._transaction.execute(
            project,
            RegionLocalMutationRequest(affected_region_ids=(change.region_id,)),
            mutate=mutate,
            rollback=lambda: self._restore(project, change, snapshot),
            record_history=record_history,
            history_scope=self._history.atomic_recording,
        )

        # UI/export/style derivation is post-commit. Observer failures are logged
        # and isolated while scientific state stays committed.
        run_postcommit_actions_isolated(
            lambda: self._group_controller.refresh_group_analysis_views(project, change.region_id)
        )

    def _snapshot(
        self, project: SpectroscopyProject, change: PreparedLineAnalysisHalfWidthChange
    ) -> _TransactionSnapshot:
        """Capture all project and session state touched by the transaction."""
        missing_lines = [
            line_id
            for line_id in change.region_line_ids
            if line_id not in project.absorption_lines
        ]
        if missing_lines or change.region_id not in project.absorption_regions:
            msg = "Prepared analysis half-width change no longer matches the active project."
            raise RuntimeError(msg)
        return _TransactionSnapshot(
            line_states=tuple(
                LineAnalysisHalfWidthStateSnapshot(
                    line_id=item.line_id,
                    half_width_kms=item.before_half_width,
                    lambda_range=item.before_lambda_range,
                )
                for item in change.line_changes
            ),
            region_analysis_range=project.absorption_regions[change.region_id].analysis_range,
        )

    def _restore(
        self,
        project: SpectroscopyProject,
        change: PreparedLineAnalysisHalfWidthChange,
        snapshot: _TransactionSnapshot,
    ) -> None:
        """Restore project and session state after a failed commit."""
        for state in snapshot.line_states:
            line = project.absorption_lines[state.line_id]
            line.window_kms = state.half_width_kms
            line.lambda_range = state.lambda_range
        project.absorption_regions[
            change.region_id
        ].analysis_range = snapshot.region_analysis_range

    def _require_project(self) -> SpectroscopyProject:
        project = self._project_provider()
        if project is None:
            msg = "A current project is required for an analysis half-width edit."
            raise RuntimeError(msg)
        return project


__all__ = ["OptimizeLineAnalysisHalfWidthTransactionAdapter"]
