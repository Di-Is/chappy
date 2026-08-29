"""Typed history snapshot builders from core domain models."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chappy.application.history.ports import (
    ComponentParameterState,
    ContinuumComponentSnapshot,
    ContinuumPointSnapshot,
    NamedParameterState,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from chappy.core.components.absorber import AbsorberComponent
    from chappy.core.components.continuum import ContinuumComponent


def component_parameter_state(component: AbsorberComponent) -> ComponentParameterState:
    """Capture typed parameter state for one absorber component.

    Args:
        component: Absorber component to snapshot.

    Returns:
        Typed component parameter state.
    """
    return ComponentParameterState(
        component_id=component.id,
        parameters=tuple(
            NamedParameterState(
                name=name,
                value=parameter.value,
                vary=not parameter.fixed,
                min_value=parameter.min_val,
                max_value=parameter.max_val,
                error=parameter.error,
            )
            for name, parameter in component.parameters.items()
        ),
    )


def continuum_component_snapshot(component: ContinuumComponent) -> ContinuumComponentSnapshot:
    """Capture the complete restorable state of one continuum component."""
    return ContinuumComponentSnapshot(
        component_id=component.id,
        name=component.name,
        enabled=component.enabled,
        is_shared_with_absorption=component.is_shared_with_absorption,
        points=tuple(
            ContinuumPointSnapshot.from_position(point)
            for point in component.get_continuum_points()
        ),
    )


def restore_component_parameter_states(
    components: Iterable[AbsorberComponent], states: tuple[ComponentParameterState, ...]
) -> None:
    """Restore exact parameter state for an atomic command rollback.

    Args:
        components: Components that may have been mutated by the command.
        states: Exact snapshots captured before the command.

    Raises:
        ValueError: If a snapshot cannot be matched to a supplied component.
    """
    component_by_id = {component.id: component for component in components}
    if len(component_by_id) != len(states):
        msg = "Parameter rollback components do not match the captured states."
        raise ValueError(msg)

    for state in states:
        component = component_by_id.get(state.component_id)
        if component is None:
            msg = f"Parameter rollback component not found: {state.component_id}"
            raise ValueError(msg)
        expected_names = {parameter.name for parameter in state.parameters}
        for name in tuple(component.parameters):
            if name not in expected_names:
                del component.parameters[name]
        for parameter_state in state.parameters:
            parameter = component.parameters.get(parameter_state.name)
            if parameter is None:
                msg = (
                    "Parameter rollback target not found: "
                    f"{state.component_id}.{parameter_state.name}"
                )
                raise ValueError(msg)
            if parameter_state.min_value is not None:
                parameter.min_val = parameter_state.min_value
            if parameter_state.max_value is not None:
                parameter.max_val = parameter_state.max_value
            parameter.set_value(parameter_state.value)
            parameter.fixed = not parameter_state.vary
            if parameter_state.error is not None:
                parameter.error = parameter_state.error
        component.notify_changed()
