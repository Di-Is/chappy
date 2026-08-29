"""Common protocol for typed history commands."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, Self, runtime_checkable

from chappy.core.history.commands import HistoryCommand as CoreHistoryCommand

if TYPE_CHECKING:
    from .models import HistoryApplyResult
    from .ports import HistoryCommandContext


@runtime_checkable
class HistoryCommand(CoreHistoryCommand, Protocol):
    """Application command that can apply itself through history ports."""

    def redo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Apply the command's after-state."""
        ...

    def undo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Apply the command's before-state."""
        ...

    def is_noop(self) -> bool:
        """Return whether the command represents no state change."""
        ...

    def coalesced_with(self, next_command: Self) -> Self | None:
        """Return a merged command or None when commands cannot merge."""
        ...
