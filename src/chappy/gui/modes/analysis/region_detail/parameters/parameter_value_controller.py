"""Parameter value edit controller for optimize mode."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from chappy.application.analysis_artifacts import (
    GlobalAnalysisMutationUseCase,
    run_postcommit_actions_isolated,
)
from chappy.application.history import restore_component_parameter_states
from chappy.application.optimize import OptimizeParameterMutationUseCase
from chappy.gui.modes.analysis.region_detail.adapters.history_adapter import (
    ComponentParameterState,
    component_parameter_state_for_history,
)

if TYPE_CHECKING:
    from contextlib import AbstractContextManager

    from chappy.core.components.absorber import AbsorberComponent
    from chappy.core.components.base import Parameter
    from chappy.core.spectroscopy_project import SpectroscopyProject


class OptimizeParameterValuePort(Protocol):
    """View and application boundary required by parameter value edits."""

    def value_mutation_project(self) -> SpectroscopyProject | None:
        """Return the active project for a scientific parameter transaction."""
        ...

    def value_history_atomic_recording(self) -> AbstractContextManager[None]:
        """Return a scope that restores history state when recording fails."""
        ...

    def validate_parameter_value(
        self, param_name: str, value: float, component: AbsorberComponent
    ) -> bool:
        """Return whether a candidate parameter value is valid."""
        ...

    def emit_parameter_value_changed(self, param_name: str, value: float) -> None:
        """Emit a parameter value change to collaborators."""
        ...

    def refresh_parameter_tree_values(self, component_ids: tuple[str, ...]) -> None:
        """Refresh rendered tree rows for the affected components."""
        ...

    def region_id_for_value_component(self, component: AbsorberComponent) -> str | None:
        """Return the region id associated with a component."""
        ...

    def current_value_group_id(self) -> str | None:
        """Return the region currently focused in Analysis Detail."""
        ...

    def record_value_parameter_edit(
        self,
        component_ids: list[str],
        param_name: str,
        before_states: tuple[ComponentParameterState, ...],
        after_states: tuple[ComponentParameterState, ...],
        region_id: str | None,
    ) -> None:
        """Record a parameter value edit in history."""
        ...


class OptimizeParameterValueController:
    """Coordinate optimize parameter value edits."""

    def __init__(
        self,
        *,
        port: OptimizeParameterValuePort,
        usecase: OptimizeParameterMutationUseCase,
        mutations: GlobalAnalysisMutationUseCase | None = None,
    ) -> None:
        """Initialize the controller.

        Args:
            port: Boundary used for validation, UI refresh, and history.
            usecase: UI-independent parameter mutation rules.
            mutations: Atomic global-analysis mutation use case.
        """
        self._port = port
        self._usecase = usecase
        self._mutations = mutations or GlobalAnalysisMutationUseCase()

    def apply_parameter_value(
        self, component: AbsorberComponent, param_name: str, value: float
    ) -> bool:
        """Apply a parameter edit originating from the model tree or dialog.

        Args:
            component: Target absorber component.
            param_name: Name of the parameter being updated.
            value: The candidate value to assign.

        Returns:
            True when the value passes validation and updates the model.
        """
        if not self._port.validate_parameter_value(param_name, value, component):
            return False
        project = self._port.value_mutation_project()
        if project is None:
            return False

        target_components = self._usecase.target_components(component, param_name)
        target_component_ids = [target_component.id for target_component in target_components]
        before_states = tuple(
            component_parameter_state_for_history(target_component)
            for target_component in target_components
        )

        region_id = (
            self._port.region_id_for_value_component(component)
            or self._port.current_value_group_id()
        )
        impact = self._mutations.execute(
            project,
            mutate=lambda: self._apply_parameter_value(
                component, param_name=param_name, value=value
            ),
            rollback=lambda: self._restore_parameter_states(target_components, before_states),
            record_history=lambda: self._record_parameter_history(
                target_components,
                component_ids=target_component_ids,
                param_name=param_name,
                before_states=before_states,
                region_id=region_id,
            ),
            history_scope=self._port.value_history_atomic_recording,
        )
        if not impact.changed:
            return False

        run_postcommit_actions_isolated(
            lambda: self._port.emit_parameter_value_changed(param_name, value),
            lambda: self._port.refresh_parameter_tree_values(tuple(target_component_ids)),
        )

        return True

    def _apply_parameter_value(
        self, component: AbsorberComponent, *, param_name: str, value: float
    ) -> bool:
        """Apply a parameter value inside the common scientific transaction."""
        return self._usecase.apply_parameter_value(component, param_name, value)

    def _restore_parameter_states(
        self,
        components: tuple[AbsorberComponent, ...],
        states: tuple[ComponentParameterState, ...],
    ) -> None:
        """Restore exact component parameter state."""
        restore_component_parameter_states(components, states)

    def _record_parameter_history(
        self,
        components: tuple[AbsorberComponent, ...],
        *,
        component_ids: list[str],
        param_name: str,
        before_states: tuple[ComponentParameterState, ...],
        region_id: str | None,
    ) -> None:
        """Record the committed parameter state inside the transaction."""
        after_states = tuple(
            component_parameter_state_for_history(target_component)
            for target_component in components
        )
        self._port.record_value_parameter_edit(
            component_ids, param_name, before_states, after_states, region_id
        )

    def ensure_covering_factor_parameter(self, component: AbsorberComponent) -> Parameter:
        """Return and register the component's required covering factor parameter.

        Args:
            component: Component to initialize.

        Returns:
            Existing covering factor parameter.
        """
        return self._usecase.ensure_covering_factor_parameter(component)

    def is_parameter_initialized(self, parameter: Parameter) -> bool:
        """Return whether a parameter has had one-time optimize setup."""
        return self._usecase.is_parameter_initialized(parameter)

    def mark_parameter_initialized(self, parameter: Parameter) -> None:
        """Record that a parameter has had one-time optimize setup."""
        self._usecase.mark_parameter_initialized(parameter)

    @staticmethod
    def param_value(component: AbsorberComponent, param: str) -> float:
        """Return a parameter value or fail fast for missing required parameters."""
        return OptimizeParameterMutationUseCase().parameter_value(component, param)
