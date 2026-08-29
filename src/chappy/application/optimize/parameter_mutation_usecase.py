"""Use cases for optimizer parameter mutation rules."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chappy.core.components.tie_set import effective_tie_set_for_parameter

if TYPE_CHECKING:
    from chappy.core.components.absorber import AbsorberComponent
    from chappy.core.components.base import Parameter


class OptimizeParameterMutationUseCase:
    """Apply UI-independent optimize parameter mutation rules."""

    def __init__(self) -> None:
        """Initialize mutation rule state."""
        self._initialized_parameters: set[int] = set()

    def ensure_covering_factor_parameter(self, component: AbsorberComponent) -> Parameter:
        """Return and register the required covering factor parameter.

        Args:
            component: Component to initialize.

        Returns:
            Existing covering factor parameter.

        Raises:
            RuntimeError: If the component violates the core parameter invariant.
        """
        parameter = component.parameters.get("covering_factor")
        if parameter is None:
            msg = f"Absorber component {component.id} is missing covering_factor."
            raise RuntimeError(msg)

        self.mark_parameter_initialized(parameter)

        return parameter

    def apply_parameter_value(
        self, component: AbsorberComponent, param_name: str, value: float
    ) -> bool:
        """Apply a validated parameter value to a component.

        Args:
            component: Component containing the parameter.
            param_name: Parameter name to mutate.
            value: Validated value to assign.

        Returns:
            True when a target parameter exists and accepts the value.
        """
        parameter = self.parameter_for_edit(component, param_name)
        if parameter is None:
            return False

        if parameter.value == float(value):
            return False

        try:
            parameter.value = value
        except ValueError:
            return False

        component.notify_changed()
        return True

    def parameter_for_edit(
        self, component: AbsorberComponent, param_name: str
    ) -> Parameter | None:
        """Return the mutable parameter targeted by an edit.

        Args:
            component: Component containing the parameter.
            param_name: Parameter name to mutate.

        Returns:
            Mutable parameter, or None when the component does not contain it.
        """
        if param_name == "covering_factor":
            return self.ensure_covering_factor_parameter(component)
        return component.parameters.get(param_name)

    def is_parameter_initialized(self, parameter: Parameter) -> bool:
        """Return whether a parameter has had one-time optimize setup.

        Args:
            parameter: Parameter to inspect.

        Returns:
            True when this use case has initialized the parameter.
        """
        return id(parameter) in self._initialized_parameters

    def mark_parameter_initialized(self, parameter: Parameter) -> None:
        """Record that a parameter has had one-time optimize setup.

        Args:
            parameter: Parameter that has been initialized.
        """
        self._initialized_parameters.add(id(parameter))

    def parameter_value(self, component: AbsorberComponent, param_name: str) -> float:
        """Return a parameter value or fail fast for missing required parameters.

        Args:
            component: Component containing the parameter.
            param_name: Parameter name to read.

        Returns:
            Current numeric parameter value.

        Raises:
            RuntimeError: If the component does not contain the requested parameter.
        """
        if param_name not in component.parameters:
            msg = f"Absorber component {component.id} is missing required parameter: {param_name}"
            raise RuntimeError(msg)
        return float(component.parameters[param_name].value)

    def target_components(
        self, component: AbsorberComponent, param_name: str
    ) -> tuple[AbsorberComponent, ...]:
        """Return components whose state participates in a value edit.

        Args:
            component: Edited component.
            param_name: Edited parameter name.

        Returns:
            Components sharing the edited value for history purposes.
        """
        tie_set = effective_tie_set_for_parameter(component, param_name)
        if tie_set is not None:
            return tuple(tie_set.components)
        return (component,)
