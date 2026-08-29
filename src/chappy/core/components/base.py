"""Base classes for spectral model components."""

import uuid
from abc import ABC, abstractmethod
from typing import Any

import numpy as np
from numpy.typing import NDArray

from chappy.core.change_set import ChangeSet
from chappy.core.event_dispatcher import DomainEventDispatcher
from chappy.core.events import ComponentChanged, ComponentEnabledChanged


class Parameter:
    """Model parameter with bounds and constraints.

    Represents a single parameter in a spectral model component,
    including its value, bounds, and fitting status.

    Attributes:
        name: Parameter name
        value: Current parameter value
        min_val: Minimum allowed value
        max_val: Maximum allowed value
        fixed: Whether parameter is fixed during fitting
        error: Parameter uncertainty from fitting
        unit: Physical unit of parameter
    """

    def __init__(  # All parameters are essential properties for scientific parameter modeling
        self,
        name: str,
        value: float,
        min_val: float = -np.inf,
        max_val: float = np.inf,
        *,
        fixed: bool = False,
        error: float = 0.0,
        unit: str | None = None,
    ) -> None:
        """Initialize parameter.

        Args:
            name: Parameter name
            value: Initial value
            min_val: Minimum bound
            max_val: Maximum bound
            fixed: Whether to fix during fitting
            error: Parameter uncertainty
            unit: Physical unit
        """
        self.name = name
        self._value = value
        self.min_val = min_val
        self.max_val = max_val
        self.fixed = fixed
        self.error = error
        self.unit = unit

        # Validate initial value
        self.set_value(value)

    @property
    def value(self) -> float:
        """Get parameter value."""
        return self._value

    @value.setter
    def value(self, new_value: float) -> None:
        """Set parameter value."""
        self.set_value(new_value)

    def set_value(self, value: float) -> None:
        """Set parameter value with bounds checking.

        Args:
            value: New parameter value

        Raises:
            ValueError: If value is outside bounds
        """
        if not self.min_val <= value <= self.max_val:
            msg = (
                f"Value {value} outside bounds [{self.min_val}, {self.max_val}] "
                f"for parameter '{self.name}'"
            )
            raise ValueError(msg)
        self._value = float(value)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Parameter":
        """Create parameter from dictionary."""
        return cls(**data)

    def __repr__(self) -> str:
        """String representation."""
        unit_str = f" {self.unit}" if self.unit else ""
        fixed_str = " (fixed)" if self.fixed else ""
        return f"Parameter({self.name}={self.value:.6g}{unit_str}{fixed_str})"


class ModelComponent(ABC):
    """Abstract base class for spectral model components.

    All spectral components (absorbers, continuum, etc.) inherit from
    this class. Components calculate their contribution to the total
    model spectrum.

    Components emit typed domain events through ``events`` when mutable state changes.
    """

    def __init__(self, name: str = "Component", component_id: str | None = None) -> None:
        """Initialize component.

        Args:
            name: Component name for identification
            component_id: Unique identifier for the component (generated if not provided)
        """
        self.name = name
        self.id = component_id or str(uuid.uuid4())
        self._enabled = True
        self.parameters: dict[str, Parameter] = {}
        self.events = DomainEventDispatcher()

    @property
    def enabled(self) -> bool:
        """Whether component is enabled."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """Set enabled state."""
        self.set_enabled(value)

    def set_enabled(self, enabled: bool) -> ChangeSet:
        """Set the component enabled state and return emitted changes.

        Args:
            enabled: Whether the component should participate in model evaluation.

        Returns:
            Domain changes emitted for the enabled-state update.
        """
        if self._enabled == enabled:
            return ChangeSet.empty()

        self._enabled = enabled
        change_set = ChangeSet.of(
            ComponentEnabledChanged(component_id=self.id, enabled=enabled),
            ComponentChanged(component_id=self.id),
        )
        self.events.dispatch(change_set)
        return change_set

    @abstractmethod
    def calculate(self, wavelength: NDArray[np.float64]) -> NDArray[np.float64]:
        """Calculate component contribution at given wavelengths.

        Args:
            wavelength: Wavelength array in Angstroms

        Returns:
            Component contribution (multiplicative for absorption,
            additive for emission)
        """

    def set_parameter(self, name: str, value: float) -> ChangeSet:
        """Set parameter value.

        Args:
            name: Parameter name
            value: New value

        Raises:
            KeyError: If parameter not found
        """
        if name not in self.parameters:
            msg = f"Parameter '{name}' not found in {self.name}"
            raise KeyError(msg)

        self.parameters[name].set_value(value)
        return self.notify_changed()

    def notify_changed(self) -> ChangeSet:
        """Dispatch and return a component-changed event."""
        change_set = ChangeSet.of(ComponentChanged(component_id=self.id))
        self.events.dispatch(change_set)
        return change_set

    def get_parameter_value(self, name: str) -> float:
        """Get parameter value directly.

        Args:
            name: Parameter name

        Returns:
            Parameter value
        """
        return self.parameters[name].value

    def fix_parameter(self, name: str, *, fixed: bool = True) -> ChangeSet:
        """Fix or unfix a parameter.

        Args:
            name: Parameter name
            fixed: Whether to fix parameter
        """
        self.parameters[name].fixed = fixed
        return self.notify_changed()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelComponent":
        """Create component from dictionary.

        Args:
            data: Dictionary representation

        Returns:
            Component instance
        """
        # This should be overridden by subclasses
        msg = "Subclasses must implement from_dict method"
        raise NotImplementedError(msg)

    def __repr__(self) -> str:
        """String representation."""
        param_str = ", ".join(f"{name}={p.value:.3g}" for name, p in self.parameters.items())
        enabled_str = "" if self.enabled else " (disabled)"
        return f"{self.__class__.__name__}({self.name}: {param_str}){enabled_str}"
