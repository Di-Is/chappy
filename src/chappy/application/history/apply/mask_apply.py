"""Mask storage history application."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chappy.application.analysis_artifacts import AnalysisMutationOutcome
from chappy.application.history import (
    HistoryApplyError,
    HistoryApplyErrorCode,
    MaskDefinitionSnapshot,
    ScientificHistoryApplyExecution,
    ScientificHistoryScope,
)
from chappy.application.history.apply.runtime_state import (
    restore_mask_history,
    snapshot_mask_history,
)
from chappy.application.history.snapshot_mapping import mask_from_snapshot

if TYPE_CHECKING:
    from chappy.application.history import HistoryCommandContext, MaskHistoryCommand
    from chappy.application.history.scientific_apply_executor import ScientificHistoryApplyExecutor
    from chappy.core.masking import MaskDefinition
    from chappy.core.spectroscopy_project import SpectroscopyProject


def mask_state_matches(
    current: MaskDefinition | None,
    current_index: int | None,
    expected: MaskDefinition | None,
    expected_index: int | None,
) -> bool:
    """Return whether one optional mask and its storage index match exactly."""
    return current == expected and current_index == expected_index


def preflight_mask_history(
    project: SpectroscopyProject,
    command: MaskHistoryCommand,
    *,
    target_snapshot: MaskDefinitionSnapshot | None,
    target_index: int | None,
    source_snapshot: MaskDefinitionSnapshot | None,
    source_index: int | None,
) -> AnalysisMutationOutcome:
    """Require current mask storage to equal either source or target exactly."""
    matching_indices = tuple(
        index
        for index, mask in enumerate(project.model.mask_definitions)
        if mask.identifier == command.mask_id
    )
    if len(matching_indices) > 1:
        raise HistoryApplyError(
            HistoryApplyErrorCode.INVALID_STATE,
            f"Mask history found duplicate storage identities: {command.mask_id}",
        )
    current_index = matching_indices[0] if matching_indices else None
    current = project.model.mask_definitions[current_index] if current_index is not None else None
    target = mask_from_snapshot(target_snapshot) if target_snapshot is not None else None
    source = mask_from_snapshot(source_snapshot) if source_snapshot is not None else None
    if mask_state_matches(current, current_index, target, target_index):
        return AnalysisMutationOutcome.NO_CHANGE
    if not mask_state_matches(current, current_index, source, source_index):
        if current is None and source is not None and target is not None:
            raise HistoryApplyError(
                HistoryApplyErrorCode.TARGET_NOT_FOUND,
                f"Mask history target not found: {command.mask_id}",
            )
        raise HistoryApplyError(
            HistoryApplyErrorCode.INVALID_STATE,
            f"Mask history source state does not match storage: {command.mask_id}",
        )
    remaining_count = len(project.model.mask_definitions) - (1 if current is not None else 0)
    if target is not None and (target_index is None or not 0 <= target_index <= remaining_count):
        raise HistoryApplyError(
            HistoryApplyErrorCode.INVALID_STATE,
            f"Mask history target index is out of bounds: {target_index}",
        )
    return AnalysisMutationOutcome.CHANGED


class MaskApply:
    """Apply mask storage history."""

    def __init__(self, scientific_executor: ScientificHistoryApplyExecutor) -> None:
        """Initialize with the shared scientific executor."""
        self._scientific_executor = scientific_executor

    def apply(
        self,
        project: SpectroscopyProject,
        command: MaskHistoryCommand,
        *,
        context: HistoryCommandContext,
        is_undo: bool,
    ) -> ScientificHistoryApplyExecution:
        """Apply one local mask storage transition atomically and silently."""
        target_snapshot = command.before if is_undo else command.after
        target_index = command.before_index if is_undo else command.after_index
        source_snapshot = command.after if is_undo else command.before
        source_index = command.after_index if is_undo else command.before_index
        return self._scientific_executor.execute(
            project,
            ScientificHistoryScope.regions(*command.affected_region_ids),
            preflight=lambda: preflight_mask_history(
                project,
                command,
                target_snapshot=target_snapshot,
                target_index=target_index,
                source_snapshot=source_snapshot,
                source_index=source_index,
            ),
            capture_runtime=lambda: snapshot_mask_history(project),
            mutate=lambda: command.undo(context) if is_undo else command.redo(context),
            restore_runtime=lambda snapshot: restore_mask_history(project, snapshot),
            rebuild_derived=project.model.rebuild_mask_storage,
        )


__all__ = ["MaskApply", "mask_state_matches", "preflight_mask_history"]
