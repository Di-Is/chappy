"""History adapter for optimize mode workflows."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Protocol

from chappy.application.history import (
    ComponentParameterState,
    LineOptimizationStateSnapshot,
    component_parameter_state,
)

if TYPE_CHECKING:
    from contextlib import AbstractContextManager

    from chappy.application.history.ports import (
        LineAnalysisHalfWidthStateSnapshot,
        MaskDefinitionSnapshot,
        TieSetSnapshot,
    )
    from chappy.application.optimize import MaskMutationKind, ModelDeletionHistorySnapshot
    from chappy.core.components.absorber import AbsorberComponent
    from chappy.core.components.tie_set import ParameterTieSet

__all__ = [
    "ComponentParameterState",
    "LineOptimizationStateSnapshot",
    "OptimizeHistoryAdapter",
    "OptimizeHistoryRecorder",
    "component_parameter_state_for_history",
]


def component_parameter_state_for_history(component: AbsorberComponent) -> ComponentParameterState:
    """Build a parameter-state snapshot for optimize history recording."""
    return component_parameter_state(component)


class OptimizeHistoryRecorder(Protocol):
    """History recording operations required by optimize mode."""

    def suppress_recording(self) -> AbstractContextManager[None]:
        """Return a context suppressing nested history records."""
        ...

    def atomic_recording(self) -> AbstractContextManager[None]:
        """Return a context that rolls history back when recording fails."""
        ...

    def record_model_edit_params(
        self,
        component_ids: list[str],
        param_name: str,
        before_states: tuple[ComponentParameterState, ...],
        after_states: tuple[ComponentParameterState, ...],
        region_id: str | None,
    ) -> None:
        """Record a parameter edit."""
        ...

    def record_model_delete_snapshot(self, snapshot: ModelDeletionHistorySnapshot) -> None:
        """Record component deletion from an immutable pre-mutation snapshot."""
        ...

    def record_model_add(
        self, components: dict[str, AbsorberComponent], tie_sets: tuple[ParameterTieSet, ...]
    ) -> None:
        """Record component addition."""
        ...

    def record_tie_set_create(
        self,
        uid: str,
        before_component_states: tuple[ComponentParameterState, ...],
        after_tie_set: TieSetSnapshot,
        after_tie_set_index: int,
    ) -> None:
        """Record parameter tie set creation."""
        ...

    def record_tie_set_remove(
        self,
        uids: tuple[str, ...],
        before_tie_sets: tuple[TieSetSnapshot, ...],
        before_tie_set_indices: tuple[int, ...],
        after_tie_sets: tuple[TieSetSnapshot, ...],
        after_tie_set_indices: tuple[int, ...],
        after_component_states: tuple[ComponentParameterState, ...],
    ) -> None:
        """Record parameter tie set member removal or dissolution."""
        ...

    def record_line_analysis_half_width_change(
        self,
        affected_line_ids: tuple[str, ...],
        before_states: tuple[LineAnalysisHalfWidthStateSnapshot, ...],
        after_states: tuple[LineAnalysisHalfWidthStateSnapshot, ...],
        region_id: str,
    ) -> None:
        """Record one Optimize scientific range edit."""
        ...

    def record_mask_mutation(
        self,
        *,
        kind: MaskMutationKind,
        mask_id: str,
        before: MaskDefinitionSnapshot | None,
        after: MaskDefinitionSnapshot | None,
        before_index: int | None,
        after_index: int | None,
        affected_region_ids: tuple[str, ...],
    ) -> None:
        """Record one mask create, update, or remove."""
        ...


class OptimizeHistoryAdapter:
    """Adapt optimize workflow history events to the history recorder."""

    def __init__(self) -> None:
        """Initialize an adapter without a connected history recorder."""
        self._recorder: OptimizeHistoryRecorder | None = None

    def set_bridge(self, bridge: OptimizeHistoryRecorder | None) -> None:
        """Set the active history bridge."""
        self._recorder = bridge

    def recording_suppressed(self) -> AbstractContextManager[None]:
        """Return a context that suppresses nested history recording."""
        if self._recorder is None:
            return contextlib.nullcontext()
        return self._recorder.suppress_recording()

    def atomic_recording(self) -> AbstractContextManager[None]:
        """Return a history-only rollback boundary for a compound mode transaction."""
        if self._recorder is None:
            msg = "Scientific Optimize edits require a connected history recorder."
            raise RuntimeError(msg)
        return self._recorder.atomic_recording()

    def record_parameter_edit(
        self,
        component_ids: list[str],
        param_name: str,
        before_states: tuple[ComponentParameterState, ...],
        after_states: tuple[ComponentParameterState, ...],
        region_id: str | None,
    ) -> None:
        """Record an optimize parameter edit."""
        if self._recorder is None:
            return
        self._recorder.record_model_edit_params(
            component_ids, param_name, before_states, after_states, region_id
        )

    def record_delete(self, snapshot: ModelDeletionHistorySnapshot) -> None:
        """Record optimize component deletion from immutable pre-delete state."""
        if self._recorder is None:
            msg = "Scientific Optimize edits require a connected history recorder."
            raise RuntimeError(msg)
        self._recorder.record_model_delete_snapshot(snapshot)

    def record_add(
        self, components: dict[str, AbsorberComponent], tie_sets: tuple[ParameterTieSet, ...]
    ) -> None:
        """Record optimize component addition."""
        if self._recorder is None or not components:
            return
        self._recorder.record_model_add(components, tie_sets)

    def record_tie_set_create(
        self,
        uid: str,
        before_component_states: tuple[ComponentParameterState, ...],
        after_tie_set: TieSetSnapshot,
        after_tie_set_index: int,
    ) -> None:
        """Record tie set creation."""
        if self._recorder is None:
            return
        self._recorder.record_tie_set_create(
            uid, before_component_states, after_tie_set, after_tie_set_index
        )

    def record_tie_set_remove(
        self,
        uids: tuple[str, ...],
        before_tie_sets: tuple[TieSetSnapshot, ...],
        before_tie_set_indices: tuple[int, ...],
        after_tie_sets: tuple[TieSetSnapshot, ...],
        after_tie_set_indices: tuple[int, ...],
        after_component_states: tuple[ComponentParameterState, ...],
    ) -> None:
        """Record tie set member removal or dissolution."""
        if self._recorder is None or not before_tie_sets:
            return
        self._recorder.record_tie_set_remove(
            uids,
            before_tie_sets,
            before_tie_set_indices,
            after_tie_sets,
            after_tie_set_indices,
            after_component_states,
        )

    def record_line_analysis_half_width_change(
        self,
        affected_line_ids: tuple[str, ...],
        before_states: tuple[LineAnalysisHalfWidthStateSnapshot, ...],
        after_states: tuple[LineAnalysisHalfWidthStateSnapshot, ...],
        region_id: str,
    ) -> None:
        """Record one Optimize scientific range edit."""
        if self._recorder is None:
            return
        self._recorder.record_line_analysis_half_width_change(
            affected_line_ids, before_states, after_states, region_id
        )

    def record_mask_mutation(
        self,
        *,
        kind: MaskMutationKind,
        mask_id: str,
        before: MaskDefinitionSnapshot | None,
        after: MaskDefinitionSnapshot | None,
        before_index: int | None,
        after_index: int | None,
        affected_region_ids: tuple[str, ...],
    ) -> None:
        """Record one mask create, update, or remove."""
        if self._recorder is None:
            msg = "Scientific Optimize edits require a connected history recorder."
            raise RuntimeError(msg)
        self._recorder.record_mask_mutation(
            kind=kind,
            mask_id=mask_id,
            before=before,
            after=after,
            before_index=before_index,
            after_index=after_index,
            affected_region_ids=affected_region_ids,
        )
