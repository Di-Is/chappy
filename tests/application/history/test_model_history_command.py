"""Tests for typed model history commands."""

from __future__ import annotations

from dataclasses import dataclass, field

from chappy.application.history import (
    AbsorberComponentParameterSnapshot,
    AbsorberComponentSnapshot,
    ChangeSet,
    ComponentParameterState,
    HistoryCommandContext,
    LineOptimizationStateSnapshot,
    ModelComponentHistoryCommand,
    ModelComponentLinkSnapshot,
    ModelOptimizeApplyCommand,
    ModelParameterEditCommand,
    NamedParameterState,
    TieSetSnapshot,
)
from chappy.core.history import OperationId


@dataclass(slots=True)
class _ModelPort:
    """Model history port test double."""

    restore_component_calls: list[
        tuple[
            tuple[AbsorberComponentSnapshot, ...],
            tuple[int, ...],
            tuple[ModelComponentLinkSnapshot, ...],
            tuple[TieSetSnapshot, ...],
            tuple[int, ...],
            tuple[str, ...],
        ]
    ] = field(default_factory=list)
    remove_component_calls: list[
        tuple[
            tuple[str, ...],
            tuple[ModelComponentLinkSnapshot, ...],
            tuple[TieSetSnapshot, ...],
            tuple[int, ...],
            tuple[str, ...],
        ]
    ] = field(default_factory=list)
    parameter_calls: list[tuple[ComponentParameterState, ...]] = field(default_factory=list)
    line_calls: list[tuple[LineOptimizationStateSnapshot, ...]] = field(default_factory=list)
    cleared_regions: list[str] = field(default_factory=list)

    def restore_model_components(
        self,
        components: tuple[AbsorberComponentSnapshot, ...],
        *,
        component_indices: tuple[int, ...],
        links: tuple[ModelComponentLinkSnapshot, ...],
        tie_sets: tuple[TieSetSnapshot, ...],
        tie_set_indices: tuple[int, ...],
        removed_tie_uids: tuple[str, ...],
    ) -> ChangeSet:
        """Record restored model component snapshots."""
        self.restore_component_calls.append(
            (components, component_indices, links, tie_sets, tie_set_indices, removed_tie_uids)
        )
        return ChangeSet(
            changed_component_ids=tuple(component.component_id for component in components),
            changed_line_ids=tuple(link.line_id for link in links),
        )

    def remove_model_components(
        self,
        component_ids: tuple[str, ...],
        *,
        links: tuple[ModelComponentLinkSnapshot, ...],
        tie_sets: tuple[TieSetSnapshot, ...],
        tie_set_indices: tuple[int, ...],
        removed_tie_uids: tuple[str, ...],
    ) -> ChangeSet:
        """Record removed model component snapshots."""
        self.remove_component_calls.append(
            (component_ids, links, tie_sets, tie_set_indices, removed_tie_uids)
        )
        return ChangeSet(
            changed_component_ids=component_ids,
            changed_line_ids=tuple(link.line_id for link in links),
        )

    def restore_component_parameters(
        self, states: tuple[ComponentParameterState, ...]
    ) -> ChangeSet:
        """Record restored component states."""
        self.parameter_calls.append(states)
        return ChangeSet(changed_component_ids=tuple(state.component_id for state in states))

    def restore_line_optimization(
        self, states: tuple[LineOptimizationStateSnapshot, ...]
    ) -> ChangeSet:
        """Record restored line optimization states."""
        self.line_calls.append(states)
        return ChangeSet(changed_line_ids=tuple(state.line_id for state in states))

    def clear_region_needs_optimization(self, region_id: str) -> ChangeSet:
        """Record cleared region."""
        self.cleared_regions.append(region_id)
        return ChangeSet(changed_region_ids=(region_id,))


def _state(component_id: str, value: float, error: float = 0.01) -> ComponentParameterState:
    """Create one component parameter state."""
    return ComponentParameterState(
        component_id=component_id,
        parameters=(
            NamedParameterState(
                name="redshift",
                value=value,
                vary=True,
                min_value=None,
                max_value=None,
                error=error,
            ),
        ),
    )


def _component_snapshot(component_id: str) -> AbsorberComponentSnapshot:
    """Create one absorber component snapshot."""
    return AbsorberComponentSnapshot(
        component_id=component_id,
        name="Mg II 2796",
        enabled=True,
        wavelength=2796.35,
        oscillator_strength=0.6123,
        gamma=2.6e8,
        group_id=None,
        external_continuum_name=None,
        parameters=(
            AbsorberComponentParameterSnapshot(
                name="redshift",
                value=0.5,
                min_value=-0.1,
                max_value=10.0,
                fixed=False,
                error=0.01,
                unit=None,
            ),
        ),
    )


def _link_snapshot(component_id: str) -> ModelComponentLinkSnapshot:
    """Create one model component link snapshot."""
    return ModelComponentLinkSnapshot(line_id="line-1", component_id=component_id, index=0)


def test_model_add_command_redo_restores_and_undo_removes_components() -> None:
    """Model add command should restore on redo and remove on undo."""
    port = _ModelPort()
    context = HistoryCommandContext(model_port=port)
    component = _component_snapshot("comp-1")
    link = _link_snapshot("comp-1")
    command = ModelComponentHistoryCommand(
        op_id=OperationId.MODEL_BULK_ADD_MULTIPLET,
        components=(component,),
        component_indices=(0,),
        links=(link,),
        tie_sets_before=(),
        tie_set_indices_before=(),
        tie_sets_after=(),
        tie_set_indices_after=(),
    )

    assert command.operation_id == OperationId.MODEL_BULK_ADD_MULTIPLET
    assert command.redo(context).success
    assert command.undo(context).success

    assert port.restore_component_calls == [((component,), (0,), (link,), (), (), ())]
    assert port.remove_component_calls == [(("comp-1",), (link,), (), (), ())]


def test_model_delete_command_redo_removes_and_undo_restores_components() -> None:
    """Model delete command should remove on redo and restore on undo."""
    port = _ModelPort()
    context = HistoryCommandContext(model_port=port)
    component = _component_snapshot("comp-1")
    link = _link_snapshot("comp-1")
    command = ModelComponentHistoryCommand(
        op_id=OperationId.MODEL_DELETE,
        components=(component,),
        component_indices=(0,),
        links=(link,),
        tie_sets_before=(),
        tie_set_indices_before=(),
        tie_sets_after=(),
        tie_set_indices_after=(),
    )

    assert command.redo(context).success
    assert command.undo(context).success

    assert port.remove_component_calls == [(("comp-1",), (link,), (), (), ())]
    assert port.restore_component_calls == [((component,), (0,), (link,), (), (), ())]


def test_model_component_command_accepts_all_add_delete_operation_ids() -> None:
    """Model component command should support all add/delete operation variants."""
    component = _component_snapshot("comp-1")
    link = _link_snapshot("comp-1")
    operation_ids = (
        OperationId.MODEL_ADD,
        OperationId.MODEL_DELETE,
        OperationId.MODEL_BULK_ADD,
        OperationId.MODEL_BULK_DELETE,
        OperationId.MODEL_BULK_ADD_MULTIPLET,
        OperationId.MODEL_BULK_DELETE_MULTIPLET,
    )

    commands = tuple(
        ModelComponentHistoryCommand(
            op_id=operation_id,
            components=(component,),
            component_indices=(0,),
            links=(link,),
            tie_sets_before=(),
            tie_set_indices_before=(),
            tie_sets_after=(),
            tie_set_indices_after=(),
        )
        for operation_id in operation_ids
    )

    assert tuple(command.operation_id for command in commands) == operation_ids


def test_model_parameter_edit_redo_and_undo_restore_after_and_before() -> None:
    """Model edit command should restore after on redo and before on undo."""
    port = _ModelPort()
    context = HistoryCommandContext(model_port=port)
    before = (_state("comp-1", 0.1, error=0.03),)
    after = (_state("comp-1", 0.2, error=0.04),)
    command = ModelParameterEditCommand(
        param_name="redshift",
        component_ids=("comp-1",),
        before=before,
        after=after,
        region_id="region-1",
    )

    assert command.redo(context).success
    assert command.undo(context).success
    assert port.parameter_calls == [after, before]


def test_model_optimize_redo_and_undo_only_restore_parameter_storage() -> None:
    """Optimize history leaves freshness invalidation to its scientific executor."""
    port = _ModelPort()
    context = HistoryCommandContext(model_port=port)
    before = (_state("comp-1", 0.1),)
    after = (_state("comp-1", 0.2),)
    line_state = (LineOptimizationStateSnapshot("line-1", True),)
    command = ModelOptimizeApplyCommand(
        component_ids=("comp-1",),
        before=before,
        after=after,
        region_id="region-1",
        needs_optimization_before=line_state,
    )

    assert command.redo(context).success
    assert command.undo(context).success

    assert port.parameter_calls == [after, before]
    assert port.cleared_regions == []
    assert port.line_calls == []


def test_model_optimize_is_not_noop_when_only_optimization_flag_changes() -> None:
    """Optimize apply should be recorded when only needs-optimization flags change."""
    state = (_state("comp-1", 0.1),)
    command = ModelOptimizeApplyCommand(
        component_ids=("comp-1",),
        before=state,
        after=state,
        region_id="region-1",
        needs_optimization_before=(LineOptimizationStateSnapshot("line-1", True),),
    )

    assert not command.is_noop()


def test_model_optimize_is_noop_when_parameters_and_flags_do_not_change() -> None:
    """Optimize apply should be no-op when parameters and flags are unchanged."""
    state = (_state("comp-1", 0.1),)
    command = ModelOptimizeApplyCommand(
        component_ids=("comp-1",),
        before=state,
        after=state,
        region_id="region-1",
        needs_optimization_before=(LineOptimizationStateSnapshot("line-1", False),),
    )

    assert command.is_noop()
