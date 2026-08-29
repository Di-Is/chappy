"""Use cases for absorber model parameter edits."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from chappy.application.analysis_artifacts import (
    AnalysisMutationImpact,
    GlobalAnalysisMutationProjectPort,
    GlobalAnalysisMutationUseCase,
)
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.components.base import ModelComponent
from chappy.core.redshift_limits import clamp_z_value

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager

type AbsorberEditTarget = ModelComponent | str


class AbsorberModelProjectPort(GlobalAnalysisMutationProjectPort, Protocol):
    """Project model access required by absorber edits."""


@dataclass(frozen=True, slots=True)
class RedshiftConstraintContext:
    """Describe optional wavelength constraints used for redshift edits."""

    rest_wavelength: float | None = None
    lambda_range: tuple[float, float] | None = None


@dataclass(frozen=True, slots=True)
class AbsorberParameterEditResult:
    """Result of applying a model parameter edit."""

    component: ModelComponent
    parameter_name: str
    requested_value: float
    applied_value: float
    impact: AnalysisMutationImpact


class AbsorberEditError(ValueError):
    """Base error raised for absorber edit failures."""


class AbsorberEditValidationError(AbsorberEditError):
    """Raised when a user-supplied parameter value is invalid."""


class AbsorberEditContractError(AbsorberEditError):
    """Raised when the caller requests an unsupported edit."""


class AbsorberEditModelStateError(AbsorberEditError):
    """Raised when existing model data is not valid for the requested edit."""


class AbsorberEditUseCase:
    """Apply validated absorber parameter changes to a project model."""

    def __init__(self, *, mutations: GlobalAnalysisMutationUseCase | None = None) -> None:
        """Initialize with the global scientific mutation transaction."""
        self._mutations = mutations or GlobalAnalysisMutationUseCase()

    def update_parameter(
        self,
        project: AbsorberModelProjectPort,
        target: AbsorberEditTarget,
        parameter_name: str,
        value: float,
        constraint_context: RedshiftConstraintContext | None = None,
        *,
        record_history: Callable[[], None] | None = None,
        history_scope: Callable[[], AbstractContextManager[None]] | None = None,
    ) -> AbsorberParameterEditResult | None:
        """Update one component parameter and refresh the project model.

        Args:
            project: Project whose model should be updated.
            target: Component instance, component id, or component name.
            parameter_name: Parameter to edit.
            value: Requested parameter value.
            constraint_context: Optional redshift constraint source.
            record_history: Optional history record committed with the mutation.
            history_scope: Optional history stack rollback boundary.

        Returns:
            Edit result, or None when the target component cannot be resolved.
        """
        component = self.resolve_component(project, target)
        if component is None:
            return None

        applied_value = self._validated_parameter_value(
            component, parameter_name, value, constraint_context
        )
        parameter = component.parameters.get(parameter_name)
        if parameter is None:
            msg = f"Unsupported absorber parameter: {parameter_name}"
            raise AbsorberEditContractError(msg)
        before_value = parameter.value
        if not parameter.min_val <= applied_value <= parameter.max_val:
            msg = f"Invalid value {applied_value} for absorber parameter {parameter_name}"
            raise AbsorberEditValidationError(msg)
        impact = self._mutations.execute(
            project,
            mutate=lambda: self._apply_parameter_if_changed(
                component,
                parameter_name=parameter_name,
                before_value=before_value,
                applied_value=applied_value,
            ),
            rollback=lambda: self._restore_parameter(
                component, parameter_name=parameter_name, value=before_value
            ),
            record_history=record_history,
            history_scope=history_scope,
        )
        return AbsorberParameterEditResult(
            component=component,
            parameter_name=parameter_name,
            requested_value=value,
            applied_value=applied_value,
            impact=impact,
        )

    def update_redshift(
        self,
        project: AbsorberModelProjectPort,
        component_id: str,
        redshift: float,
        constraint_context: RedshiftConstraintContext | None = None,
        *,
        record_history: Callable[[], None] | None = None,
        history_scope: Callable[[], AbstractContextManager[None]] | None = None,
    ) -> AbsorberParameterEditResult | None:
        """Update a component redshift and refresh the project model.

        Args:
            project: Project whose model should be updated.
            component_id: Component identifier.
            redshift: Requested redshift value.
            constraint_context: Optional redshift constraint source.
            record_history: Optional history record committed with the mutation.
            history_scope: Optional history stack rollback boundary.

        Returns:
            Edit result, or None when the component cannot be resolved.
        """
        return self.update_parameter(
            project,
            component_id,
            "redshift",
            redshift,
            constraint_context,
            record_history=record_history,
            history_scope=history_scope,
        )

    @staticmethod
    def _apply_parameter_if_changed(
        component: ModelComponent,
        *,
        parameter_name: str,
        before_value: float,
        applied_value: float,
    ) -> bool:
        """Apply a validated parameter only when its scientific value changes."""
        if before_value == float(applied_value):
            return False
        component.set_parameter(parameter_name, applied_value)
        return True

    @staticmethod
    def _restore_parameter(
        component: ModelComponent, *, parameter_name: str, value: float
    ) -> None:
        """Restore one parameter after a failed scientific transaction."""
        component.set_parameter(parameter_name, value)

    def resolve_component(
        self, project: AbsorberModelProjectPort, target: AbsorberEditTarget
    ) -> ModelComponent | None:
        """Resolve a component from a project model.

        Args:
            project: Project containing the model.
            target: Component instance, component id, or component name.

        Returns:
            Matching component, or None when no match exists.
        """
        components = project.model.components
        if not components:
            return None

        identifiers: tuple[str, ...]
        if isinstance(target, str):
            identifiers = (target,)
        elif target in components:
            return target
        else:
            identifiers = (target.id, target.name)

        for component in components:
            if component.id in identifiers:
                return component
            if component.name in identifiers:
                return component

        return None

    def _validated_parameter_value(
        self,
        component: ModelComponent,
        parameter_name: str,
        value: float,
        constraint_context: RedshiftConstraintContext | None,
    ) -> float:
        """Return the model-ready parameter value."""
        if parameter_name != "redshift" or not isinstance(component, AbsorberComponent):
            return value

        rest_wavelength = self._redshift_rest_wavelength(component, constraint_context)
        lambda_range = constraint_context.lambda_range if constraint_context is not None else None
        return clamp_z_value(value, rest_wavelength, lambda_range)

    def _redshift_rest_wavelength(
        self, component: AbsorberComponent, constraint_context: RedshiftConstraintContext | None
    ) -> float:
        """Return the finite rest wavelength used for redshift validation."""
        if constraint_context is not None and constraint_context.rest_wavelength is not None:
            value = constraint_context.rest_wavelength
        else:
            value = component.wavelength

        numeric_value = float(value)
        if not math.isfinite(numeric_value):
            msg = f"absorber {component.id} has invalid value: rest_wavelength"
            raise AbsorberEditModelStateError(msg)
        return numeric_value


__all__ = [
    "AbsorberEditContractError",
    "AbsorberEditError",
    "AbsorberEditModelStateError",
    "AbsorberEditTarget",
    "AbsorberEditUseCase",
    "AbsorberEditValidationError",
    "AbsorberModelProjectPort",
    "AbsorberParameterEditResult",
    "RedshiftConstraintContext",
]
