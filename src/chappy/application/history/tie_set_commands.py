"""Typed history command for parameter tie set membership edits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from chappy.core.history.operation_id import OperationId

from .models import (
    ChangeSet,
    HistoryApplyError,
    HistoryApplyResult,
    HistoryRefreshTarget,
    recoverable_history_apply_failure,
)

if TYPE_CHECKING:
    from .ports import ComponentParameterState, HistoryCommandContext, TieSetSnapshot


_TIE_SET_EDIT_OPERATION_IDS = frozenset(
    (
        OperationId.MODEL_TIE_SET_CREATE,
        OperationId.MODEL_TIE_SET_REMOVE,
        OperationId.MODEL_TIE_SET_DISSOLVE,
    )
)


@dataclass(frozen=True, slots=True)
class TieSetEditCommand:
    """History command for tie set creation, member removal, and dissolution.

    Components are never added or removed by this command. ``uids`` lists
    every tie set uid that must be cleared before its target snapshots (if
    any) are rebuilt, so both directions can dissolve a stale tie set and
    recreate it from the opposite snapshot set in one port call.
    """

    op_id: OperationId
    uids: tuple[str, ...]
    before_tie_sets: tuple[TieSetSnapshot, ...]
    before_tie_set_indices: tuple[int, ...]
    after_tie_sets: tuple[TieSetSnapshot, ...]
    after_tie_set_indices: tuple[int, ...]
    before_component_states: tuple[ComponentParameterState, ...]
    after_component_states: tuple[ComponentParameterState, ...]

    def __post_init__(self) -> None:
        """Validate that the operation is a tie set membership mutation."""
        if self.op_id not in _TIE_SET_EDIT_OPERATION_IDS:
            msg = f"Unsupported tie set history operation: {self.op_id}"
            raise ValueError(msg)
        for snapshots, indices in (
            (self.before_tie_sets, self.before_tie_set_indices),
            (self.after_tie_sets, self.after_tie_set_indices),
        ):
            if len(snapshots) != len(indices):
                msg = "Tie set history snapshots and indices must have equal length."
                raise ValueError(msg)
            if len(set(indices)) != len(indices) or any(index < 0 for index in indices):
                msg = "Tie set history indices must be unique and non-negative."
                raise ValueError(msg)

    @property
    def operation_id(self) -> OperationId:
        """Return the tie set edit operation identifier."""
        return self.op_id

    @property
    def qualifier(self) -> str | None:
        """Return no operation qualifier."""
        return None

    def redo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Apply the tie set edit's after-state."""
        return self._apply(
            context, self.after_tie_sets, self.after_tie_set_indices, self.after_component_states
        )

    def undo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Restore the tie set state before the edit."""
        return self._apply(
            context,
            self.before_tie_sets,
            self.before_tie_set_indices,
            self.before_component_states,
        )

    def is_noop(self) -> bool:
        """Return whether the edit changes no tie set or component state."""
        return (
            self.before_tie_sets == self.after_tie_sets
            and self.before_tie_set_indices == self.after_tie_set_indices
            and self.before_component_states == self.after_component_states
        )

    def coalesced_with(self, next_command: TieSetEditCommand) -> TieSetEditCommand | None:
        """Tie set edit commands are not coalesced."""
        _ = next_command
        return None

    def _apply(
        self,
        context: HistoryCommandContext,
        tie_sets: tuple[TieSetSnapshot, ...],
        tie_set_indices: tuple[int, ...],
        component_states: tuple[ComponentParameterState, ...],
    ) -> HistoryApplyResult:
        """Restore tie set membership and affected component states through the model port."""
        model_port = context.require_model_port()
        try:
            change_set = model_port.restore_tie_sets(
                tie_sets, tie_set_indices=tie_set_indices, removed_uids=self.uids
            )
            if component_states:
                change_set = _merge_component_ids(
                    change_set, model_port.restore_component_parameters(component_states)
                )
        except HistoryApplyError as error:
            return recoverable_history_apply_failure(error)
        return HistoryApplyResult.ok(
            change_set=change_set,
            refresh_targets=(HistoryRefreshTarget.MODEL, HistoryRefreshTarget.OPTIMIZE_PANEL),
        )


def _merge_component_ids(first: ChangeSet, second: ChangeSet) -> ChangeSet:
    """Merge changed component IDs from two change sets."""
    merged_ids = tuple(
        sorted(set(first.changed_component_ids) | set(second.changed_component_ids))
    )
    return ChangeSet(changed_component_ids=merged_ids)
