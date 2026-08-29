"""Exact runtime-state snapshots captured and restored during history application.

These types and functions capture the precise mutable state required to roll a
history command back out atomically if a later step of its transaction fails.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from chappy.application.history import (
    ComponentParameterState,
    LineAnalysisHalfWidthStateSnapshot,
    ResolutionStateSnapshot,
)
from chappy.application.history.apply.parameter_targets import resolve_parameter_targets
from chappy.core.components.continuum import ContinuumComponent

if TYPE_CHECKING:
    from chappy.core.components.base import ModelComponent, Parameter
    from chappy.core.masking import MaskDefinition
    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.core.spectrum_model import SpectrumModelDerivedStateSnapshot


@dataclass(frozen=True, slots=True)
class LineAnalysisHalfWidthApplySnapshot:
    """Command-specific line and session state restored after an abort."""

    line_states: tuple[LineAnalysisHalfWidthStateSnapshot, ...]
    region_analysis_range: tuple[float, float] | None


@dataclass(frozen=True, slots=True)
class MaskHistoryApplySnapshot:
    """Exact mask collection and derived model caches restored after an abort."""

    masks: tuple[MaskDefinition, ...]
    derived_model: SpectrumModelDerivedStateSnapshot


@dataclass(frozen=True, slots=True)
class ContinuumRuntimeState:
    """Exact mutable state for one retained continuum component."""

    component: ContinuumComponent
    name: str
    enabled: bool
    is_shared_with_absorption: bool
    points: tuple[tuple[float, float], ...]


@dataclass(frozen=True, slots=True)
class ContinuumHistoryApplySnapshot:
    """Exact model order, continuum objects, and derived cache for rollback."""

    component_order: tuple[ModelComponent, ...]
    continua: tuple[ContinuumRuntimeState, ...]
    derived_model: SpectrumModelDerivedStateSnapshot


@dataclass(frozen=True, slots=True)
class ParameterRuntimeValue:
    """Exact mutable state of one unique runtime parameter."""

    parameter: Parameter
    value: float
    min_value: float
    max_value: float
    fixed: bool
    error: float


@dataclass(frozen=True, slots=True)
class ParameterHistoryApplySnapshot:
    """Parameter identities and derived model state restored after an abort."""

    parameters: tuple[ParameterRuntimeValue, ...]
    derived_model: SpectrumModelDerivedStateSnapshot


@dataclass(frozen=True, slots=True)
class ResolutionHistoryApplySnapshot:
    """Exact resolution and model cache restored after an aborted history apply."""

    resolution: ResolutionStateSnapshot
    derived_model: SpectrumModelDerivedStateSnapshot


def snapshot_continuum_history(project: SpectroscopyProject) -> ContinuumHistoryApplySnapshot:
    """Capture exact continuum objects, model order, and derived caches."""
    return ContinuumHistoryApplySnapshot(
        component_order=tuple(project.model.components),
        continua=tuple(
            ContinuumRuntimeState(
                component=component,
                name=component.name,
                enabled=component.enabled,
                is_shared_with_absorption=component.is_shared_with_absorption,
                points=tuple(component.get_continuum_points()),
            )
            for component in project.model.components
            if isinstance(component, ContinuumComponent)
        ),
        derived_model=project.model.snapshot_derived_state_for_transaction(),
    )


def restore_continuum_history(
    project: SpectroscopyProject, snapshot: ContinuumHistoryApplySnapshot
) -> None:
    """Restore exact continuum identity/order/state and model caches silently."""
    project.model.restore_component_order_for_transaction(snapshot.component_order)
    for state in snapshot.continua:
        state.component.name = state.name
        state.component.enabled = state.enabled
        state.component.is_shared_with_absorption = state.is_shared_with_absorption
        state.component.continuum_points = list(state.points)
    project.model.restore_derived_state_for_transaction(snapshot.derived_model)


def snapshot_parameter_history(
    project: SpectroscopyProject, states: tuple[ComponentParameterState, ...]
) -> ParameterHistoryApplySnapshot:
    """Capture unique parameter identities and all derived model caches."""
    resolved = resolve_parameter_targets(
        project, tuple(state.component_id for state in states), states
    )
    return ParameterHistoryApplySnapshot(
        parameters=tuple(
            ParameterRuntimeValue(
                parameter=item.parameter,
                value=item.parameter.value,
                min_value=item.parameter.min_val,
                max_value=item.parameter.max_val,
                fixed=item.parameter.fixed,
                error=item.parameter.error,
            )
            for item in resolved
        ),
        derived_model=project.model.snapshot_derived_state_for_transaction(),
    )


def restore_parameter_history(
    project: SpectroscopyProject, snapshot: ParameterHistoryApplySnapshot
) -> None:
    """Restore parameter identities and derived caches without notification."""
    for state in snapshot.parameters:
        state.parameter.min_val = state.min_value
        state.parameter.max_val = state.max_value
        state.parameter.set_value(state.value)
        state.parameter.fixed = state.fixed
        state.parameter.error = state.error
    project.model.restore_derived_state_for_transaction(snapshot.derived_model)


def snapshot_mask_history(project: SpectroscopyProject) -> MaskHistoryApplySnapshot:
    """Capture exact mask ordering and all mask-dependent model caches."""
    return MaskHistoryApplySnapshot(
        masks=project.model.mask_definitions,
        derived_model=project.model.snapshot_derived_state_for_transaction(),
    )


def restore_mask_history(project: SpectroscopyProject, snapshot: MaskHistoryApplySnapshot) -> None:
    """Restore exact mask ordering and derived caches without notifications."""
    project.model.restore_mask_definitions_for_transaction(
        snapshot.masks, model_was_valid=snapshot.derived_model.model_valid
    )
    project.model.restore_derived_state_for_transaction(snapshot.derived_model)


def snapshot_resolution_history(project: SpectroscopyProject) -> ResolutionHistoryApplySnapshot:
    """Capture exact resolution and derived cache before Undo or Redo."""
    return ResolutionHistoryApplySnapshot(
        resolution=ResolutionStateSnapshot.from_state(project.resolution_state),
        derived_model=project.model.snapshot_derived_state_for_transaction(),
    )


def restore_resolution_history(
    project: SpectroscopyProject, snapshot: ResolutionHistoryApplySnapshot
) -> None:
    """Restore exact resolution and derived cache after a transaction failure."""
    project.set_resolution(snapshot.resolution.value, snapshot.resolution.enabled)
    project.model.restore_derived_state_for_transaction(snapshot.derived_model)


__all__ = [
    "ContinuumHistoryApplySnapshot",
    "ContinuumRuntimeState",
    "LineAnalysisHalfWidthApplySnapshot",
    "MaskHistoryApplySnapshot",
    "ParameterHistoryApplySnapshot",
    "ParameterRuntimeValue",
    "ResolutionHistoryApplySnapshot",
    "restore_continuum_history",
    "restore_mask_history",
    "restore_parameter_history",
    "restore_resolution_history",
    "snapshot_continuum_history",
    "snapshot_mask_history",
    "snapshot_parameter_history",
    "snapshot_resolution_history",
]
