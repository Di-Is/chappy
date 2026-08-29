"""Continuum topology and control-point history application."""

from __future__ import annotations

import math
from dataclasses import replace
from itertools import pairwise
from typing import TYPE_CHECKING

from chappy.application.analysis_artifacts import AnalysisMutationOutcome
from chappy.application.history import (
    ContinuumAddComponentCommand,
    ContinuumComponentSnapshot,
    ContinuumPointSnapshot,
    HistoryApplyError,
    HistoryApplyErrorCode,
    HistoryRefreshTarget,
    ScientificHistoryApplyExecution,
    ScientificHistoryScope,
)
from chappy.application.history.apply.runtime_state import (
    restore_continuum_history,
    snapshot_continuum_history,
)
from chappy.application.history.snapshot_builders import continuum_component_snapshot
from chappy.core.change_set import ChangeSet as DomainChangeSet
from chappy.core.components.continuum import ContinuumComponent
from chappy.core.events import ComponentAdded, ComponentChanged, ComponentRemoved

if TYPE_CHECKING:
    from chappy.application.history import (
        ContinuumAddPointCommand,
        ContinuumDeletePointCommand,
        ContinuumMovePointCommand,
        ContinuumResetCommand,
        HistoryApplyResult,
        HistoryCommandContext,
    )
    from chappy.application.history.apply.project_appliers import ProjectContinuumHistoryApplier
    from chappy.application.history.scientific_apply_executor import ScientificHistoryApplyExecutor
    from chappy.core.components.base import ModelComponent
    from chappy.core.events import DomainEvent
    from chappy.core.spectroscopy_project import SpectroscopyProject

    ContinuumHistoryCommand = (
        ContinuumAddComponentCommand
        | ContinuumAddPointCommand
        | ContinuumDeletePointCommand
        | ContinuumMovePointCommand
        | ContinuumResetCommand
    )


def validate_continuum_points(points: tuple[ContinuumPointSnapshot, ...]) -> None:
    """Reject non-finite or non-canonical ordered continuum points."""
    if any(
        not math.isfinite(point.wavelength) or not math.isfinite(point.flux) for point in points
    ) or any(first.wavelength >= second.wavelength for first, second in pairwise(points)):
        raise HistoryApplyError(
            HistoryApplyErrorCode.INVALID_STATE,
            "Continuum history points must be finite with strictly increasing wavelengths.",
        )


def continuum_component_state_matches(
    project: SpectroscopyProject,
    current: ModelComponent | None,
    snapshot: ContinuumComponentSnapshot,
    index: int,
    *,
    present: bool,
) -> bool:
    """Compare one continuum component and its model position exactly."""
    if not present:
        return current is None
    return (
        isinstance(current, ContinuumComponent)
        and project.model.components.index(current) == index
        and continuum_component_snapshot(current) == snapshot
    )


def preflight_continuum_history(
    project: SpectroscopyProject,
    continuum_applier: ProjectContinuumHistoryApplier,
    command: ContinuumHistoryCommand,
    *,
    is_undo: bool,
) -> AnalysisMutationOutcome:
    """Validate exact component identity/index or complete point order."""
    if isinstance(command, ContinuumAddComponentCommand):
        snapshot = command.snapshot
        if not snapshot.component_id:
            raise HistoryApplyError(
                HistoryApplyErrorCode.INVALID_STATE,
                "Continuum history component identity cannot be empty.",
            )
        validate_continuum_points(snapshot.points)
        current_component = project.model.get_component_by_id(snapshot.component_id)
        if current_component is not None and not isinstance(current_component, ContinuumComponent):
            raise HistoryApplyError(
                HistoryApplyErrorCode.INVALID_STATE,
                f"Continuum history identity belongs to another component type: "
                f"{snapshot.component_id}",
            )
        target_present = not is_undo
        if continuum_component_state_matches(
            project, current_component, snapshot, command.component_index, present=target_present
        ):
            return AnalysisMutationOutcome.NO_CHANGE
        if not continuum_component_state_matches(
            project,
            current_component,
            snapshot,
            command.component_index,
            present=not target_present,
        ):
            if not target_present and current_component is None:
                raise HistoryApplyError(
                    HistoryApplyErrorCode.TARGET_NOT_FOUND,
                    f"Continuum history component not found: {snapshot.component_id}",
                )
            raise HistoryApplyError(
                HistoryApplyErrorCode.INVALID_STATE,
                "Continuum history component source does not match storage.",
            )
        remaining_count = len(project.model.components) - (current_component is not None)
        if target_present and not 0 <= command.component_index <= remaining_count:
            raise HistoryApplyError(
                HistoryApplyErrorCode.INVALID_STATE,
                "Continuum history component index is out of bounds.",
            )
        return AnalysisMutationOutcome.CHANGED

    continuum = continuum_applier.require_continuum(command.continuum_id)
    validate_continuum_points(command.before)
    validate_continuum_points(command.after)
    target = command.before if is_undo else command.after
    source = command.after if is_undo else command.before
    current_points = tuple(
        ContinuumPointSnapshot.from_position(point) for point in continuum.get_continuum_points()
    )
    if current_points == target:
        return AnalysisMutationOutcome.NO_CHANGE
    if current_points != source:
        raise HistoryApplyError(
            HistoryApplyErrorCode.INVALID_STATE,
            f"Continuum history point source does not match storage: {command.continuum_id}",
        )
    return AnalysisMutationOutcome.CHANGED


class ContinuumApply:
    """Apply continuum topology and control-point history."""

    def __init__(
        self,
        scientific_executor: ScientificHistoryApplyExecutor,
        continuum_applier: ProjectContinuumHistoryApplier,
    ) -> None:
        """Initialize with the shared scientific executor and continuum applier."""
        self._scientific_executor = scientific_executor
        self._continuum_applier = continuum_applier

    def apply(
        self,
        project: SpectroscopyProject,
        command: ContinuumHistoryCommand,
        *,
        context: HistoryCommandContext,
        is_undo: bool,
    ) -> ScientificHistoryApplyExecution:
        """Apply continuum topology or points through one global transaction."""
        target_present: bool | None = None
        if isinstance(command, ContinuumAddComponentCommand):
            target_present = not is_undo
            component_id = command.snapshot.component_id
        else:
            component_id = command.continuum_id

        def mutate() -> HistoryApplyResult:
            result = command.undo(context) if is_undo else command.redo(context)
            if not result.success:
                return result
            if (
                preflight_continuum_history(
                    project, self._continuum_applier, command, is_undo=is_undo
                )
                is not AnalysisMutationOutcome.NO_CHANGE
            ):
                raise HistoryApplyError(
                    HistoryApplyErrorCode.INVALID_STATE,
                    "Continuum history mutation did not reach its exact target.",
                )
            return replace(result, refresh_targets=(HistoryRefreshTarget.CONTINUUM_EDITOR,))

        def rebuild() -> DomainChangeSet:
            event: DomainEvent
            if target_present is None:
                event = ComponentChanged(component_id=component_id)
            elif target_present:
                event = ComponentAdded(component_id=component_id)
            else:
                event = ComponentRemoved(component_id=component_id)
            return DomainChangeSet.of(event).extend(project.model.rebuild_model_storage())

        return self._scientific_executor.execute(
            project,
            ScientificHistoryScope.all_analysis_capable(),
            preflight=lambda: preflight_continuum_history(
                project, self._continuum_applier, command, is_undo=is_undo
            ),
            capture_runtime=lambda: snapshot_continuum_history(project),
            mutate=mutate,
            restore_runtime=lambda snapshot: restore_continuum_history(project, snapshot),
            rebuild_derived=rebuild,
            notification_scope=project.model.suppress_scientific_notifications,
        )


__all__ = ["ContinuumApply", "preflight_continuum_history", "validate_continuum_points"]
