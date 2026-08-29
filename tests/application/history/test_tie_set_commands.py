"""Tests for typed tie set edit history commands."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from chappy.application.history import (
    ChangeSet,
    ComponentParameterState,
    HistoryCommandContext,
    NamedParameterState,
    TieSetEditCommand,
    TieSetSnapshot,
)
from chappy.core.history import OperationId


@dataclass(slots=True)
class _ModelPort:
    """Model history port test double for tie set commands."""

    restore_tie_set_calls: list[
        tuple[tuple[TieSetSnapshot, ...], tuple[int, ...], tuple[str, ...]]
    ] = field(default_factory=list)
    parameter_calls: list[tuple[ComponentParameterState, ...]] = field(default_factory=list)

    def restore_tie_sets(
        self,
        snapshots: tuple[TieSetSnapshot, ...],
        *,
        tie_set_indices: tuple[int, ...],
        removed_uids: tuple[str, ...],
    ) -> ChangeSet:
        """Record tie set restore requests."""
        self.restore_tie_set_calls.append((snapshots, tie_set_indices, removed_uids))
        return ChangeSet(
            changed_component_ids=tuple(
                component_id for snapshot in snapshots for component_id in snapshot.component_ids
            )
        )

    def restore_component_parameters(
        self, states: tuple[ComponentParameterState, ...]
    ) -> ChangeSet:
        """Record restored component states."""
        self.parameter_calls.append(states)
        return ChangeSet(changed_component_ids=tuple(state.component_id for state in states))


def _snapshot(tie_id: str, origin: str = "user") -> TieSetSnapshot:
    """Create one tie set snapshot."""
    return TieSetSnapshot(
        uid=tie_id,
        tie_id=tie_id,
        name=tie_id,
        origin=origin,
        mask=("b_parameter", "column_density", "covering_factor", "redshift"),
        component_ids=("comp-1", "comp-2"),
        shared_parameters=(
            NamedParameterState(
                name="redshift", value=1.2, vary=True, min_value=-0.1, max_value=10.0, error=0.0
            ),
        ),
    )


def _state(component_id: str) -> ComponentParameterState:
    """Create one component parameter state."""
    return ComponentParameterState(
        component_id=component_id,
        parameters=(
            NamedParameterState(
                name="redshift", value=1.2, vary=True, min_value=None, max_value=None, error=0.0
            ),
        ),
    )


def test_create_command_redo_restores_after_and_undo_restores_before() -> None:
    """Create command replays the after snapshot and unbinds on undo."""
    port = _ModelPort()
    context = HistoryCommandContext(model_port=port)
    command = TieSetEditCommand(
        op_id=OperationId.MODEL_TIE_SET_CREATE,
        uids=("user-1",),
        before_tie_sets=(),
        before_tie_set_indices=(),
        after_tie_sets=(_snapshot("user-1"),),
        after_tie_set_indices=(0,),
        before_component_states=(_state("comp-1"), _state("comp-2")),
        after_component_states=(),
    )

    assert command.redo(context).success
    assert port.restore_tie_set_calls[-1] == ((_snapshot("user-1"),), (0,), ("user-1",))
    assert port.parameter_calls == []

    assert command.undo(context).success
    assert port.restore_tie_set_calls[-1] == ((), (), ("user-1",))
    assert port.parameter_calls[-1] == (_state("comp-1"), _state("comp-2"))


def test_remove_command_undo_restores_before_snapshot() -> None:
    """Remove command undo rebuilds the pre-removal multiplet tie set."""
    port = _ModelPort()
    context = HistoryCommandContext(model_port=port)
    before = _snapshot("multiplet-1", origin="multiplet")
    after = _snapshot("multiplet-1", origin="user")
    command = TieSetEditCommand(
        op_id=OperationId.MODEL_TIE_SET_REMOVE,
        uids=("multiplet-1",),
        before_tie_sets=(before,),
        before_tie_set_indices=(0,),
        after_tie_sets=(after,),
        after_tie_set_indices=(0,),
        before_component_states=(),
        after_component_states=(_state("comp-3"),),
    )

    assert command.redo(context).success
    assert port.restore_tie_set_calls[-1] == ((after,), (0,), ("multiplet-1",))
    assert port.parameter_calls[-1] == (_state("comp-3"),)

    assert command.undo(context).success
    assert port.restore_tie_set_calls[-1] == ((before,), (0,), ("multiplet-1",))
    assert port.restore_tie_set_calls[-1][0][0].origin == "multiplet"


def test_dissolve_command_redo_clears_tie_set() -> None:
    """Dissolve command redo removes the tie set without rebuilding one."""
    port = _ModelPort()
    context = HistoryCommandContext(model_port=port)
    command = TieSetEditCommand(
        op_id=OperationId.MODEL_TIE_SET_DISSOLVE,
        uids=("multiplet-1",),
        before_tie_sets=(_snapshot("multiplet-1", origin="multiplet"),),
        before_tie_set_indices=(0,),
        after_tie_sets=(),
        after_tie_set_indices=(),
        before_component_states=(),
        after_component_states=(_state("comp-1"), _state("comp-2")),
    )

    assert command.redo(context).success
    assert port.restore_tie_set_calls[-1] == ((), (), ("multiplet-1",))


def test_command_rejects_non_tie_set_operation() -> None:
    """Non tie-set operations are rejected at construction."""
    with pytest.raises(ValueError, match="Unsupported tie set history operation"):
        TieSetEditCommand(
            op_id=OperationId.MODEL_EDIT_PARAMS,
            uids=(),
            before_tie_sets=(),
            before_tie_set_indices=(),
            after_tie_sets=(),
            after_tie_set_indices=(),
            before_component_states=(),
            after_component_states=(),
        )


def test_command_is_noop_when_states_match() -> None:
    """Identical before and after states make the command a no-op."""
    snapshot = _snapshot("user-1")
    command = TieSetEditCommand(
        op_id=OperationId.MODEL_TIE_SET_CREATE,
        uids=("user-1",),
        before_tie_sets=(snapshot,),
        before_tie_set_indices=(0,),
        after_tie_sets=(snapshot,),
        after_tie_set_indices=(0,),
        before_component_states=(),
        after_component_states=(),
    )

    assert command.is_noop()
    assert command.coalesced_with(command) is None
