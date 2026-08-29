"""Tests for the typed spectral-resolution history command."""

from __future__ import annotations

from chappy.application.history import (
    ChangeSet,
    HistoryCommandContext,
    HistoryRefreshTarget,
    ResolutionHistoryCommand,
    ResolutionStateSnapshot,
)
from chappy.core.history import OperationId


class _ResolutionPort:
    """In-memory resolution apply port for command tests."""

    def __init__(self) -> None:
        """Initialize without an applied state."""
        self.state: ResolutionStateSnapshot | None = None

    def apply_resolution_state(self, snapshot: ResolutionStateSnapshot) -> ChangeSet:
        """Store the exact requested state."""
        self.state = snapshot
        return ChangeSet.empty()


def _command() -> ResolutionHistoryCommand:
    """Build one non-noop resolution command."""
    return ResolutionHistoryCommand(
        before=ResolutionStateSnapshot(value=36_000.0, enabled=False),
        after=ResolutionStateSnapshot(value=48_000.0, enabled=True),
    )


def test_resolution_command_applies_exact_before_and_after_states() -> None:
    """Undo and redo must delegate their complete typed snapshots."""
    port = _ResolutionPort()
    context = HistoryCommandContext(resolution_port=port)
    command = _command()

    redo = command.redo(context)
    assert redo.success is True
    assert redo.refresh_targets == (HistoryRefreshTarget.MODEL,)
    assert port.state == command.after

    undo = command.undo(context)
    assert undo.success is True
    assert port.state == command.before


def test_resolution_command_metadata_and_noop_contract() -> None:
    """Resolution commands expose stable history metadata and exact no-op semantics."""
    command = _command()

    assert command.operation_id is OperationId.MODEL_EDIT_RESOLUTION
    assert command.qualifier is None
    assert command.is_noop() is False
    assert command.coalesced_with(command) is None
    assert ResolutionHistoryCommand(before=command.before, after=command.before).is_noop() is True
