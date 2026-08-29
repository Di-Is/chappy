"""Typed history commands for spectrum range changes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from chappy.core.history.operation_id import OperationId

from .models import (
    HistoryApplyError,
    HistoryApplyResult,
    HistoryRefreshTarget,
    recoverable_history_apply_failure,
)

if TYPE_CHECKING:
    from .ports import HistoryCommandContext, RangeSnapshot


@dataclass(frozen=True, slots=True)
class RangeHistoryCommand:
    """History command for visible spectrum range changes."""

    before: RangeSnapshot
    after: RangeSnapshot
    qualifier: str | None = None

    @property
    def operation_id(self) -> OperationId:
        """Return the range change operation identifier."""
        return OperationId.DRAW_RANGE_CHANGE

    def redo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Apply the after range snapshot."""
        return self._apply(context, self.after)

    def undo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Apply the before range snapshot."""
        return self._apply(context, self.before)

    def is_noop(self) -> bool:
        """Return whether before and after snapshots are equal."""
        return self.before == self.after

    def coalesced_with(self, next_command: RangeHistoryCommand) -> RangeHistoryCommand | None:
        """Keep the first before snapshot and replace only the after snapshot."""
        if not isinstance(next_command, RangeHistoryCommand):
            return None
        if (
            self.operation_id != next_command.operation_id
            or self.qualifier != next_command.qualifier
        ):
            return None
        return RangeHistoryCommand(
            before=self.before, after=next_command.after, qualifier=self.qualifier
        )

    def _apply(
        self, context: HistoryCommandContext, snapshot: RangeSnapshot
    ) -> HistoryApplyResult:
        """Apply a range snapshot through the configured port."""
        range_port = context.require_range_port()
        try:
            change_set = range_port.apply_range(snapshot, source="history")
        except HistoryApplyError as error:
            return recoverable_history_apply_failure(error)
        return HistoryApplyResult.ok(
            change_set=change_set, refresh_targets=(HistoryRefreshTarget.SPECTRUM_RANGE,)
        )
