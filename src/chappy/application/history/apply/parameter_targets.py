"""Shared Qt-free helpers for resolving history parameter targets.

Used both by model parameter restore ports and by scientific preflight and
snapshot logic that stays in ``gui.history.bridge`` until a later migration
unit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from chappy.application.history.models import HistoryApplyError, HistoryApplyErrorCode

if TYPE_CHECKING:
    from chappy.application.history.ports import ComponentParameterState, NamedParameterState
    from chappy.core.components.base import Parameter
    from chappy.core.spectroscopy_project import SpectroscopyProject


@dataclass(frozen=True, slots=True)
class ResolvedParameterTarget:
    """One unique runtime parameter and its exact history target state."""

    parameter: Parameter
    target: NamedParameterState


def resolve_parameter_targets(
    project: SpectroscopyProject,
    component_ids: tuple[str, ...],
    states: tuple[ComponentParameterState, ...],
) -> tuple[ResolvedParameterTarget, ...]:
    """Resolve every component and unique shared parameter before mutation."""
    normalized_component_ids = tuple(dict.fromkeys(component_ids))
    state_ids = tuple(state.component_id for state in states)
    if (
        len(normalized_component_ids) != len(component_ids)
        or len(set(state_ids)) != len(state_ids)
        or set(normalized_component_ids) != set(state_ids)
    ):
        raise HistoryApplyError(
            HistoryApplyErrorCode.INVALID_STATE,
            "Model parameter history components do not match their target snapshots.",
        )

    by_identity: dict[int, ResolvedParameterTarget] = {}
    for state in states:
        component = project.find_absorber_component(state.component_id)
        if component is None:
            raise HistoryApplyError(
                HistoryApplyErrorCode.TARGET_NOT_FOUND,
                f"Component not found for parameter restore: {state.component_id}",
            )
        names = tuple(parameter_state.name for parameter_state in state.parameters)
        if len(set(names)) != len(names):
            raise HistoryApplyError(
                HistoryApplyErrorCode.INVALID_STATE,
                f"Duplicate parameter target for component: {state.component_id}",
            )
        for parameter_state in state.parameters:
            parameter = component.parameters.get(parameter_state.name)
            if parameter is None:
                raise HistoryApplyError(
                    HistoryApplyErrorCode.TARGET_NOT_FOUND,
                    "Parameter not found for restore: "
                    f"{state.component_id}.{parameter_state.name}",
                )
            target = effective_parameter_target(parameter, parameter_state)
            resolved = ResolvedParameterTarget(parameter=parameter, target=target)
            existing = by_identity.get(id(parameter))
            if existing is not None and existing.target != target:
                raise HistoryApplyError(
                    HistoryApplyErrorCode.INVALID_STATE,
                    "Shared parameter history snapshots disagree for "
                    f"{state.component_id}.{parameter_state.name}.",
                )
            by_identity[id(parameter)] = resolved
    return tuple(by_identity.values())


def effective_parameter_target(
    parameter: Parameter, state: NamedParameterState
) -> NamedParameterState:
    """Fill optional legacy fields and reject clamping or malformed bounds."""
    minimum = parameter.min_val if state.min_value is None else state.min_value
    maximum = parameter.max_val if state.max_value is None else state.max_value
    error = parameter.error if state.error is None else state.error
    if minimum > maximum or not minimum <= state.value <= maximum:
        raise HistoryApplyError(
            HistoryApplyErrorCode.INVALID_STATE,
            f"Parameter history value {state.value} is outside target bounds "
            f"[{minimum}, {maximum}] for {state.name}.",
        )
    if not math.isfinite(state.value):
        raise HistoryApplyError(
            HistoryApplyErrorCode.INVALID_STATE,
            f"Parameter history value must be finite for {state.name}.",
        )
    return replace(state, min_value=minimum, max_value=maximum, error=error)


def parameter_matches_target(item: ResolvedParameterTarget) -> bool:
    """Return whether one runtime parameter already equals its exact target."""
    target = item.target
    parameter = item.parameter
    return (
        parameter.value == target.value
        and parameter.fixed is (not target.vary)
        and parameter.min_val == target.min_value
        and parameter.max_val == target.max_value
        and parameter.error == target.error
    )
