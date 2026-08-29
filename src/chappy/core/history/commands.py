"""Core protocol for commands stored in history events."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, Self, runtime_checkable

if TYPE_CHECKING:
    from .operation_id import OperationId


@runtime_checkable
class HistoryCommand(Protocol):
    """Command contract required by the core history stack."""

    @property
    def operation_id(self) -> OperationId:
        """Return the operation identifier."""
        ...

    @property
    def qualifier(self) -> str | None:
        """Return the optional operation qualifier."""
        ...

    def is_noop(self) -> bool:
        """Return whether the command represents no state change."""
        ...

    def coalesced_with(self, next_command: Self) -> Self | None:
        """Return a merged command or None when commands cannot merge."""
        ...
