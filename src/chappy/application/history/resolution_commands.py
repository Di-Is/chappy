"""Typed history command for spectral-resolution changes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from chappy.core.history.operation_id import OperationId

from .models import HistoryApplyResult, HistoryRefreshTarget

if TYPE_CHECKING:
    from contextlib import AbstractContextManager

    from chappy.application.history.ports import HistoryCommandContext
    from chappy.core.resolution import ResolutionState

    from .models import ChangeSet


@dataclass(frozen=True, slots=True)
class ResolutionStateSnapshot:
    """Exact spectral-resolution state stored by one history command."""

    value: float
    enabled: bool

    @classmethod
    def from_state(cls, state: ResolutionState) -> ResolutionStateSnapshot:
        """Capture a core resolution state without retaining mutable identity."""
        return cls(value=float(state.value), enabled=state.enabled)


class ResolutionHistoryPort(Protocol):
    """Port used to apply a spectral-resolution history snapshot."""

    def apply_resolution_state(self, snapshot: ResolutionStateSnapshot) -> ChangeSet:
        """Apply an exact resolution state to the current project."""
        ...


@runtime_checkable
class ResolutionHistoryRecorder(Protocol):
    """History recorder required by atomic forward resolution updates."""

    def record_resolution_change(
        self, before: ResolutionStateSnapshot, after: ResolutionStateSnapshot
    ) -> None:
        """Record one exact spectral-resolution transition."""
        ...

    def atomic_recording(self) -> AbstractContextManager[None]:
        """Return the rollback scope for the history stack."""
        ...


@dataclass(frozen=True, slots=True)
class ResolutionHistoryCommand:
    """Undoable global spectral-resolution transition."""

    before: ResolutionStateSnapshot
    after: ResolutionStateSnapshot

    @property
    def operation_id(self) -> OperationId:
        """Return the spectral-resolution operation identifier."""
        return OperationId.MODEL_EDIT_RESOLUTION

    @property
    def qualifier(self) -> str | None:
        """Return no operation qualifier."""
        return None

    def redo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Apply the recorded after-state."""
        return self._apply(context, self.after)

    def undo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Restore the recorded before-state."""
        return self._apply(context, self.before)

    def is_noop(self) -> bool:
        """Return whether both exact states are equal."""
        return self.before == self.after

    def coalesced_with(
        self, next_command: ResolutionHistoryCommand
    ) -> ResolutionHistoryCommand | None:
        """Resolution confirmations remain distinct user operations."""
        _ = next_command
        return None

    @staticmethod
    def _apply(
        context: HistoryCommandContext, snapshot: ResolutionStateSnapshot
    ) -> HistoryApplyResult:
        """Apply one direction through the typed resolution port."""
        change_set = context.require_resolution_port().apply_resolution_state(snapshot)
        return HistoryApplyResult.ok(
            change_set=change_set, refresh_targets=(HistoryRefreshTarget.MODEL,)
        )


__all__ = [
    "ResolutionHistoryCommand",
    "ResolutionHistoryPort",
    "ResolutionHistoryRecorder",
    "ResolutionStateSnapshot",
]
