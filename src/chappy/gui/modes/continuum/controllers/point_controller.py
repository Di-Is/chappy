"""Point mutation controller for continuum interaction snapshots."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from chappy.application.analysis_artifacts import (
    AnalysisMutationImpact,
    GlobalAnalysisMutationUseCase,
    run_postcommit_actions_isolated,
)
from chappy.presentation.interaction.interaction_contracts import (
    ContinuumContext,
    ContinuumOperationType,
    InteractionChannel,
    InteractionPhase,
    InteractionStateSnapshot,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from chappy.core.components.continuum import ContinuumComponent
    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.modes.continuum.history_adapter import ContinuumPointHistoryPort

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContinuumPointMutationPorts:
    """Ports required to apply continuum point interaction snapshots."""

    project_provider: Callable[[], SpectroscopyProject | None]
    continuum_provider: Callable[[], ContinuumComponent | None]
    history: ContinuumPointHistoryPort
    preview_callback: Callable[[ContinuumComponent, int, tuple[float, float]], None]
    refresh_callback: Callable[[ContinuumComponent], None]
    error_callback: Callable[[str], None]


class ContinuumPointMutationController:
    """Apply continuum point mutations from interaction snapshots."""

    def __init__(
        self,
        ports: ContinuumPointMutationPorts,
        *,
        mutations: GlobalAnalysisMutationUseCase | None = None,
    ) -> None:
        """Initialize the controller.

        Args:
            ports: Dependencies required to mutate continuum points and update UI.
            mutations: Atomic global-analysis mutation use case.
        """
        self._ports = ports
        self._mutations = mutations or GlobalAnalysisMutationUseCase()

    def apply_snapshot(self, snapshot: InteractionStateSnapshot[ContinuumContext]) -> None:
        """Apply a continuum interaction snapshot when it contains a mutation.

        Args:
            snapshot: Snapshot describing the current continuum interaction state.
        """
        if snapshot.channel != InteractionChannel.CONTINUUM:
            return

        context = snapshot.context
        if context is None or context.operation_type is None:
            return

        continuum = self._ports.continuum_provider()
        project = self._ports.project_provider()
        if continuum is None or project is None:
            return

        try:
            self._apply_snapshot(snapshot, context, continuum, project)
        except (RuntimeError, TypeError):
            raise
        except Exception as exc:
            logger.exception("Failed to apply continuum snapshot")
            self._ports.error_callback(f"Continuum editing error: {exc}")

    def _apply_snapshot(
        self,
        snapshot: InteractionStateSnapshot[ContinuumContext],
        context: ContinuumContext,
        continuum: ContinuumComponent,
        project: SpectroscopyProject,
    ) -> None:
        operation_type = context.operation_type
        if (
            operation_type == ContinuumOperationType.ADD
            and snapshot.phase == InteractionPhase.IDLE
        ):
            self._commit_add(context, continuum, project)
            return

        if (
            operation_type == ContinuumOperationType.MOVE
            and snapshot.phase == InteractionPhase.ACTIVE
        ):
            self._preview_move(context, continuum)
            return

        if (
            operation_type == ContinuumOperationType.MOVE
            and snapshot.phase == InteractionPhase.IDLE
        ):
            self._commit_move(context, continuum, project)
            return

        if (
            operation_type == ContinuumOperationType.DELETE
            and snapshot.phase == InteractionPhase.IDLE
        ):
            self._commit_delete(context, continuum, project)

    def _commit_add(
        self,
        context: ContinuumContext,
        continuum: ContinuumComponent,
        project: SpectroscopyProject,
    ) -> None:
        if context.end_position is None:
            return

        wavelength, flux = context.end_position
        before_points = continuum.get_continuum_points()
        after_points = [*before_points, (wavelength, flux)]
        after_points.sort(key=lambda point: point[0])
        impact = self._commit_points(
            project,
            continuum,
            before_points=before_points,
            after_points=after_points,
            record_history=lambda: self._ports.history.record_add_point(
                continuum, before_points, after_points
            ),
        )
        if not impact.changed:
            return
        logger.info("Added continuum point via snapshot: %.1f Å, %.4f", wavelength, flux)
        run_postcommit_actions_isolated(lambda: self._ports.refresh_callback(continuum))

    def _preview_move(self, context: ContinuumContext, continuum: ContinuumComponent) -> None:
        if context.point_index is None or context.current_position is None:
            return

        self._ports.preview_callback(continuum, context.point_index, context.current_position)

    def _commit_move(
        self,
        context: ContinuumContext,
        continuum: ContinuumComponent,
        project: SpectroscopyProject,
    ) -> None:
        if context.validation_result is not None:
            logger.warning(
                "Move operation rejected: validation failed - %s",
                context.validation_result.message,
            )
            return
        if context.point_index is None or context.end_position is None:
            return
        if not 0 <= context.point_index < continuum.num_continuum_points():
            return

        wavelength, flux = context.end_position
        before_points = continuum.get_continuum_points()
        after_points = list(before_points)
        after_points[context.point_index] = (wavelength, flux)
        after_points.sort(key=lambda point: point[0])
        impact = self._commit_points(
            project,
            continuum,
            before_points=before_points,
            after_points=after_points,
            record_history=lambda: self._ports.history.record_move_point(
                continuum, before_points, after_points
            ),
        )
        if not impact.changed:
            return
        logger.info(
            "Moved continuum point %d via snapshot: %.1f Å, %.4f",
            context.point_index,
            wavelength,
            flux,
        )

        run_postcommit_actions_isolated(lambda: self._ports.refresh_callback(continuum))

    def _commit_delete(
        self,
        context: ContinuumContext,
        continuum: ContinuumComponent,
        project: SpectroscopyProject,
    ) -> None:
        if context.point_index is None:
            return
        if not 0 <= context.point_index < continuum.num_continuum_points():
            return

        before_points = continuum.get_continuum_points()
        after_points = list(before_points)
        del after_points[context.point_index]
        impact = self._commit_points(
            project,
            continuum,
            before_points=before_points,
            after_points=after_points,
            record_history=lambda: self._ports.history.record_delete_point(
                continuum, before_points, after_points
            ),
        )
        if not impact.changed:
            return
        logger.info("Deleted continuum point %d via snapshot", context.point_index)
        run_postcommit_actions_isolated(lambda: self._ports.refresh_callback(continuum))

    def _commit_points(
        self,
        project: SpectroscopyProject,
        continuum: ContinuumComponent,
        *,
        before_points: list[tuple[float, float]],
        after_points: list[tuple[float, float]],
        record_history: Callable[[], None],
    ) -> AnalysisMutationImpact:
        """Commit point state, project invalidation, and history atomically."""
        return self._mutations.execute(
            project,
            mutate=lambda: self._replace_points(
                continuum, before_points=before_points, after_points=after_points
            ),
            rollback=lambda: self._restore_points(continuum, before_points),
            record_history=record_history,
            history_scope=self._ports.history.atomic_recording,
        )

    @staticmethod
    def _replace_points(
        continuum: ContinuumComponent,
        *,
        before_points: list[tuple[float, float]],
        after_points: list[tuple[float, float]],
    ) -> bool:
        """Replace continuum points when their scientific state changed."""
        if before_points == after_points:
            return False
        continuum.continuum_points = list(after_points)
        return True

    @staticmethod
    def _restore_points(
        continuum: ContinuumComponent, before_points: list[tuple[float, float]]
    ) -> None:
        """Restore continuum points after a failed transaction."""
        continuum.continuum_points = list(before_points)
