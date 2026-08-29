"""History management module for undo/redo operations.

This module provides the core infrastructure for undo/redo functionality:

Classes:
    CommandHistory: Main class managing undo/redo stacks.
    HistoryEvent: Immutable data structure representing a single operation.
    HistoryState: Snapshot of stack state for UI updates.
    UndoResult: Result of an undo operation.
    RedoResult: Result of a redo operation.
    OperationId: Enum of all undoable operation types.
    CoalesceBuffer: Buffer for aggregating high-frequency operations.

Example:
    from chappy.core.history import CommandHistory, HistoryEvent, OperationId

    history = CommandHistory()

    event = HistoryEvent(command=my_command)
    history.push(event)

    result = history.undo()
    if result.success:
        print(f"Undone: {result.operation_name}")
"""

from .coalesce import DEFAULT_COALESCE_WINDOW_MS, CoalesceBuffer
from .command_history import (
    HISTORY_MAX,
    CommandHistory,
    HistoryApplier,
    HistoryOwnerThreadError,
    StateChangeCallback,
)
from .commands import HistoryCommand
from .history_event import HistoryEvent, HistoryState, RedoResult, UndoResult
from .operation_id import OperationId

__all__ = [
    "DEFAULT_COALESCE_WINDOW_MS",
    "HISTORY_MAX",
    "CoalesceBuffer",
    "CommandHistory",
    "HistoryApplier",
    "HistoryCommand",
    "HistoryEvent",
    "HistoryOwnerThreadError",
    "HistoryState",
    "OperationId",
    "RedoResult",
    "StateChangeCallback",
    "UndoResult",
]
