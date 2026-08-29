"""Spectral resolution history application."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from chappy.application.analysis_artifacts import AnalysisMutationOutcome
from chappy.application.history import (
    HistoryApplyError,
    HistoryApplyErrorCode,
    ResolutionStateSnapshot,
    ScientificHistoryApplyExecution,
    ScientificHistoryScope,
)
from chappy.application.history.apply.runtime_state import (
    restore_resolution_history,
    snapshot_resolution_history,
)
from chappy.core.resolution import RESOLUTION_CONSTRAINTS

if TYPE_CHECKING:
    from chappy.application.history import (
        HistoryApplyResult,
        HistoryCommandContext,
        ResolutionHistoryCommand,
    )
    from chappy.application.history.scientific_apply_executor import ScientificHistoryApplyExecutor
    from chappy.core.spectroscopy_project import SpectroscopyProject


def preflight_resolution_history(
    project: SpectroscopyProject,
    *,
    source: ResolutionStateSnapshot,
    target: ResolutionStateSnapshot,
) -> AnalysisMutationOutcome:
    """Require a valid command and an exact temporal resolution source state."""
    for label, snapshot in (("source", source), ("target", target)):
        if (
            not math.isfinite(snapshot.value)
            or snapshot.value < RESOLUTION_CONSTRAINTS["min"]
            or snapshot.value > RESOLUTION_CONSTRAINTS["max"]
            or not isinstance(snapshot.enabled, bool)
        ):
            raise HistoryApplyError(
                HistoryApplyErrorCode.INVALID_STATE,
                f"Resolution history {label} state is invalid.",
            )
    current = ResolutionStateSnapshot.from_state(project.resolution_state)
    if current == target:
        return AnalysisMutationOutcome.NO_CHANGE
    if current != source:
        raise HistoryApplyError(
            HistoryApplyErrorCode.INVALID_STATE,
            "Resolution history source state does not match current storage.",
        )
    return AnalysisMutationOutcome.CHANGED


class ResolutionApply:
    """Apply spectral resolution history."""

    def __init__(self, scientific_executor: ScientificHistoryApplyExecutor) -> None:
        """Initialize with the shared scientific executor."""
        self._scientific_executor = scientific_executor

    def apply(
        self,
        project: SpectroscopyProject,
        command: ResolutionHistoryCommand,
        *,
        context: HistoryCommandContext,
        is_undo: bool,
    ) -> ScientificHistoryApplyExecution:
        """Apply one global spectral-resolution transition atomically."""
        source = command.after if is_undo else command.before
        target = command.before if is_undo else command.after

        def mutate() -> HistoryApplyResult:
            result = command.undo(context) if is_undo else command.redo(context)
            if not result.success:
                return result
            if ResolutionStateSnapshot.from_state(project.resolution_state) != target:
                raise HistoryApplyError(
                    HistoryApplyErrorCode.INVALID_STATE,
                    "Resolution history mutation did not reach its exact target.",
                )
            return result

        return self._scientific_executor.execute(
            project,
            ScientificHistoryScope.all_analysis_capable(),
            preflight=lambda: preflight_resolution_history(project, source=source, target=target),
            capture_runtime=lambda: snapshot_resolution_history(project),
            mutate=mutate,
            restore_runtime=lambda snapshot: restore_resolution_history(project, snapshot),
            rebuild_derived=project.model.rebuild_model_storage,
            notification_scope=project.model.suppress_scientific_notifications,
        )


__all__ = ["ResolutionApply", "preflight_resolution_history"]
