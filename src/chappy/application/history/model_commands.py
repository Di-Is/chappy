"""Typed history commands for model parameter operations."""

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
    from .ports import (
        AbsorberComponentSnapshot,
        ComponentParameterState,
        HistoryCommandContext,
        LineAnalysisHalfWidthStateSnapshot,
        LineOptimizationStateSnapshot,
        ModelComponentLinkSnapshot,
        TieSetSnapshot,
    )


_MODEL_ADD_OPERATION_IDS = frozenset(
    (OperationId.MODEL_ADD, OperationId.MODEL_BULK_ADD, OperationId.MODEL_BULK_ADD_MULTIPLET)
)
_MODEL_DELETE_OPERATION_IDS = frozenset(
    (
        OperationId.MODEL_DELETE,
        OperationId.MODEL_BULK_DELETE,
        OperationId.MODEL_BULK_DELETE_MULTIPLET,
    )
)
_MODEL_COMPONENT_OPERATION_IDS = _MODEL_ADD_OPERATION_IDS | _MODEL_DELETE_OPERATION_IDS


@dataclass(frozen=True, slots=True)
class ModelComponentHistoryCommand:
    """History command for adding or deleting model components."""

    op_id: OperationId
    components: tuple[AbsorberComponentSnapshot, ...]
    component_indices: tuple[int, ...]
    links: tuple[ModelComponentLinkSnapshot, ...]
    tie_sets_before: tuple[TieSetSnapshot, ...]
    tie_set_indices_before: tuple[int, ...]
    tie_sets_after: tuple[TieSetSnapshot, ...]
    tie_set_indices_after: tuple[int, ...]

    def __post_init__(self) -> None:
        """Validate that the operation is a model component mutation."""
        if self.op_id not in _MODEL_COMPONENT_OPERATION_IDS:
            msg = f"Unsupported model component history operation: {self.op_id}"
            raise ValueError(msg)
        if len(self.component_indices) != len(self.components):
            msg = "Model component snapshots and indices must have equal length."
            raise ValueError(msg)
        if len(set(self.component_indices)) != len(self.component_indices) or any(
            index < 0 for index in self.component_indices
        ):
            msg = "Model component history indices must be unique and non-negative."
            raise ValueError(msg)
        for snapshots, indices in (
            (self.tie_sets_before, self.tie_set_indices_before),
            (self.tie_sets_after, self.tie_set_indices_after),
        ):
            if len(snapshots) != len(indices):
                msg = "Model tie set history snapshots and indices must have equal length."
                raise ValueError(msg)
            if len(set(indices)) != len(indices) or any(index < 0 for index in indices):
                msg = "Model tie set history indices must be unique and non-negative."
                raise ValueError(msg)

    @property
    def operation_id(self) -> OperationId:
        """Return the model component operation identifier."""
        return self.op_id

    @property
    def qualifier(self) -> str | None:
        """Return no operation qualifier."""
        return None

    def redo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Apply the component mutation."""
        if self.op_id in _MODEL_ADD_OPERATION_IDS:
            return self._restore_components(
                context, self.tie_sets_after, self.tie_set_indices_after
            )
        return self._remove_components(context, self.tie_sets_after, self.tie_set_indices_after)

    def undo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Restore the component state before the mutation."""
        if self.op_id in _MODEL_ADD_OPERATION_IDS:
            return self._remove_components(
                context, self.tie_sets_before, self.tie_set_indices_before
            )
        return self._restore_components(context, self.tie_sets_before, self.tie_set_indices_before)

    def is_noop(self) -> bool:
        """Return whether no components are affected."""
        return not self.components

    def coalesced_with(
        self, next_command: ModelComponentHistoryCommand
    ) -> ModelComponentHistoryCommand | None:
        """Model component add/delete commands are not coalesced."""
        _ = next_command
        return None

    def _restore_components(
        self,
        context: HistoryCommandContext,
        tie_sets: tuple[TieSetSnapshot, ...],
        tie_set_indices: tuple[int, ...],
    ) -> HistoryApplyResult:
        """Restore component snapshots through the model port."""
        model_port = context.require_model_port()
        try:
            change_set = model_port.restore_model_components(
                self.components,
                component_indices=self.component_indices,
                links=self.links,
                tie_sets=tie_sets,
                tie_set_indices=tie_set_indices,
                removed_tie_uids=self._affected_tie_uids(),
            )
        except HistoryApplyError as error:
            return recoverable_history_apply_failure(error)
        return _model_component_result(change_set)

    def _remove_components(
        self,
        context: HistoryCommandContext,
        tie_sets: tuple[TieSetSnapshot, ...],
        tie_set_indices: tuple[int, ...],
    ) -> HistoryApplyResult:
        """Remove components through the model port."""
        model_port = context.require_model_port()
        try:
            change_set = model_port.remove_model_components(
                tuple(component.component_id for component in self.components),
                links=self.links,
                tie_sets=tie_sets,
                tie_set_indices=tie_set_indices,
                removed_tie_uids=self._affected_tie_uids(),
            )
        except HistoryApplyError as error:
            return recoverable_history_apply_failure(error)
        return _model_component_result(change_set)

    def _affected_tie_uids(self) -> tuple[str, ...]:
        """Return every tie identity touched by either temporal state."""
        return tuple(
            dict.fromkeys(
                snapshot.uid for snapshot in (*self.tie_sets_before, *self.tie_sets_after)
            )
        )


@dataclass(frozen=True, slots=True)
class ModelParameterEditCommand:
    """History command for manual parameter edits."""

    param_name: str
    component_ids: tuple[str, ...]
    before: tuple[ComponentParameterState, ...]
    after: tuple[ComponentParameterState, ...]
    region_id: str | None

    @property
    def operation_id(self) -> OperationId:
        """Return the model edit operation identifier."""
        return OperationId.MODEL_EDIT_PARAMS

    @property
    def qualifier(self) -> str | None:
        """Return no operation qualifier."""
        return None

    def redo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Apply edited parameter states."""
        return self._apply(context, self.after)

    def undo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Restore previous parameter states."""
        return self._apply(context, self.before)

    def is_noop(self) -> bool:
        """Return whether before and after states are equal."""
        return self.before == self.after

    def coalesced_with(
        self, next_command: ModelParameterEditCommand
    ) -> ModelParameterEditCommand | None:
        """Model parameter edits are not coalesced."""
        _ = next_command
        return None

    def _apply(
        self, context: HistoryCommandContext, states: tuple[ComponentParameterState, ...]
    ) -> HistoryApplyResult:
        """Apply parameter states through the model port."""
        model_port = context.require_model_port()
        try:
            change_set = model_port.restore_component_parameters(states)
        except HistoryApplyError as error:
            return recoverable_history_apply_failure(error)
        return HistoryApplyResult.ok(
            change_set=change_set,
            refresh_targets=(HistoryRefreshTarget.MODEL, HistoryRefreshTarget.OPTIMIZE_PANEL),
        )


@dataclass(frozen=True, slots=True)
class LineAnalysisHalfWidthHistoryCommand:
    """History command for Optimize scientific analysis half-width edits."""

    affected_line_ids: tuple[str, ...]
    before: tuple[LineAnalysisHalfWidthStateSnapshot, ...]
    after: tuple[LineAnalysisHalfWidthStateSnapshot, ...]
    region_id: str

    @property
    def operation_id(self) -> OperationId:
        """Return the dedicated scientific edit operation identifier."""
        return OperationId.MODEL_EDIT_LINE_ANALYSIS_HALF_WIDTH

    @property
    def qualifier(self) -> str | None:
        """Return no operation qualifier."""
        return None

    def redo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Apply the edited scientific ranges and keep the region stale."""
        return self._apply(context, self.after)

    def undo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Restore previous scientific ranges and keep the region stale."""
        return self._apply(context, self.before)

    def is_noop(self) -> bool:
        """Return whether before and after scientific range states are equal."""
        return self.before == self.after

    def coalesced_with(
        self, next_command: LineAnalysisHalfWidthHistoryCommand
    ) -> LineAnalysisHalfWidthHistoryCommand | None:
        """Scientific range edits are not coalesced."""
        _ = next_command
        return None

    def _apply(
        self,
        context: HistoryCommandContext,
        states: tuple[LineAnalysisHalfWidthStateSnapshot, ...],
    ) -> HistoryApplyResult:
        model_port = context.require_model_port()
        try:
            change_set = model_port.restore_line_analysis_half_width_states(
                states, region_id=self.region_id
            )
        except HistoryApplyError as error:
            return recoverable_history_apply_failure(error)
        return HistoryApplyResult.ok(
            change_set=change_set,
            refresh_targets=(
                HistoryRefreshTarget.OPTIMIZE_PANEL,
                HistoryRefreshTarget.LINE_OVERLAYS,
                HistoryRefreshTarget.VELOCITY_PLOT,
                HistoryRefreshTarget.OPTIMIZE_WAVELENGTH_MODEL_RESIDUAL,
            ),
        )


@dataclass(frozen=True, slots=True)
class ModelOptimizeApplyCommand:
    """History command for applying fit results to model parameters."""

    component_ids: tuple[str, ...]
    before: tuple[ComponentParameterState, ...]
    after: tuple[ComponentParameterState, ...]
    region_id: str | None
    needs_optimization_before: tuple[LineOptimizationStateSnapshot, ...]

    @property
    def operation_id(self) -> OperationId:
        """Return the model optimize operation identifier."""
        return OperationId.MODEL_OPTIMIZE_APPLY

    @property
    def qualifier(self) -> str | None:
        """Return no operation qualifier."""
        return None

    def redo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Apply optimized parameter states without reviving fit freshness."""
        model_port = context.require_model_port()
        try:
            change_set = model_port.restore_component_parameters(self.after)
        except HistoryApplyError as error:
            return recoverable_history_apply_failure(error)
        return HistoryApplyResult.ok(
            change_set=change_set,
            refresh_targets=(HistoryRefreshTarget.MODEL, HistoryRefreshTarget.OPTIMIZE_PANEL),
        )

    def undo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Restore pre-optimization parameters without reviving old line flags."""
        model_port = context.require_model_port()
        try:
            change_set = model_port.restore_component_parameters(self.before)
        except HistoryApplyError as error:
            return recoverable_history_apply_failure(error)
        return HistoryApplyResult.ok(
            change_set=change_set,
            refresh_targets=(HistoryRefreshTarget.MODEL, HistoryRefreshTarget.OPTIMIZE_PANEL),
        )

    def is_noop(self) -> bool:
        """Return whether parameters and optimization flags are unchanged."""
        clears_optimization_flag = self.region_id is not None and any(
            state.needs_optimization for state in self.needs_optimization_before
        )
        return self.before == self.after and not clears_optimization_flag

    def coalesced_with(
        self, next_command: ModelOptimizeApplyCommand
    ) -> ModelOptimizeApplyCommand | None:
        """Optimize apply commands are not coalesced."""
        _ = next_command
        return None


def _model_component_result(change_set: ChangeSet) -> HistoryApplyResult:
    """Create the common apply result for model component mutations."""
    return HistoryApplyResult.ok(
        change_set=change_set,
        refresh_targets=(HistoryRefreshTarget.MODEL, HistoryRefreshTarget.OPTIMIZE_PANEL),
    )
