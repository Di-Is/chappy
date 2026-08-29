"""Controller for optimize parameter fixed-state workflow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from chappy.application.analysis_artifacts import (
    AnalysisMutationImpact,
    GlobalAnalysisMutationUseCase,
    run_postcommit_actions_isolated,
)
from chappy.application.history import (
    component_parameter_state,
    restore_component_parameter_states,
)
from chappy.core.components.tie_set import effective_tie_set_for_parameter

if TYPE_CHECKING:
    from collections.abc import Iterable
    from contextlib import AbstractContextManager

    from chappy.application.history import ComponentParameterState
    from chappy.core.components.absorber import AbsorberComponent
    from chappy.core.components.base import Parameter
    from chappy.core.components.tie_set import ParameterTieSet
    from chappy.core.spectroscopy_project import SpectroscopyProject


class OptimizeParameterFixPort(Protocol):
    """Panel operations required by parameter fixed-state workflow."""

    def fix_mutation_project(self) -> SpectroscopyProject | None:
        """Return the active project for a fixed-state transaction."""
        ...

    def fix_history_atomic_recording(self) -> AbstractContextManager[None]:
        """Return a scope that restores history state when recording fails."""
        ...

    def mark_fix_parameter_initialized(self, parameter: Parameter) -> None:
        """Mark a covering-factor parameter as initialized after commit."""
        ...

    def region_id_for_fix_component(self, component: AbsorberComponent) -> str | None:
        """Return the region id associated with a component."""
        ...

    def current_fix_group_id(self) -> str | None:
        """Return the region currently focused in Analysis Detail."""
        ...

    def record_fix_parameter_edit(
        self,
        component_ids: list[str],
        param_name: str,
        before_states: tuple[ComponentParameterState, ...],
        after_states: tuple[ComponentParameterState, ...],
        region_id: str | None,
    ) -> None:
        """Record a parameter fixed-state edit."""
        ...

    def refresh_fix_parameter_styles(self) -> None:
        """Refresh parameter row styles after fixed-state changes."""
        ...

    def refresh_fix_parameter_dialog(self) -> None:
        """Refresh the parameter edit dialog after fixed-state changes."""
        ...


class OptimizeParameterFixController:
    """Coordinate fixed-state changes for optimize parameters."""

    def __init__(
        self,
        *,
        port: OptimizeParameterFixPort,
        mutations: GlobalAnalysisMutationUseCase | None = None,
    ) -> None:
        """Initialize the controller.

        Args:
            port: Panel operations needed by the workflow.
            mutations: Atomic global-analysis mutation use case.
        """
        self._port = port
        self._mutations = mutations or GlobalAnalysisMutationUseCase()

    @staticmethod
    def resolve_shared_fix_target(
        components: Iterable[AbsorberComponent], param_name: str
    ) -> ParameterTieSet | None:
        """Return the sole tie set masking param_name for every selected component."""
        tie_set: ParameterTieSet | None = None
        for component in components:
            component_tie_set = effective_tie_set_for_parameter(component, param_name)
            if component_tie_set is None:
                return None
            if tie_set is None:
                tie_set = component_tie_set
            elif tie_set is not component_tie_set:
                return None
        return tie_set

    @staticmethod
    def are_all_components_fixed(components: Iterable[AbsorberComponent], param_name: str) -> bool:
        """Return True when the parameter is fixed for every component."""
        has_target = False
        for component in components:
            parameter = component.parameters.get(param_name)
            if parameter is None:
                return False
            has_target = True
            if not parameter.fixed:
                return False
        return has_target

    def set_fixed_state_for_components(
        self, components: Iterable[AbsorberComponent], param_name: str, fixed: bool
    ) -> AnalysisMutationImpact:
        """Set fixed state across selected components as one atomic command."""
        affected = self._expand_to_affected_components(components, param_name)
        return self._commit_fixed_state(
            affected,
            param_name=param_name,
            fixed=fixed,
            region_id=self._port.current_fix_group_id(),
        )

    def handle_fix_action_for_components(
        self, components: list[AbsorberComponent], param_name: str, fixed: bool
    ) -> None:
        """Apply a fixed-state toggle to a component selection."""
        affected = self._expand_to_affected_components(components, param_name)
        if not affected:
            return
        impact = self._commit_fixed_state(
            affected,
            param_name=param_name,
            fixed=fixed,
            region_id=self._port.current_fix_group_id(),
        )
        if not impact.changed:
            return
        run_postcommit_actions_isolated(
            self._port.refresh_fix_parameter_styles, self._port.refresh_fix_parameter_dialog
        )

    def set_fixed_state(
        self, component: AbsorberComponent, param_name: str, fixed: bool
    ) -> AnalysisMutationImpact:
        """Set fixed state for a component or its parameter tie set."""
        affected = self._expand_to_affected_components((component,), param_name)
        return self._commit_fixed_state(
            affected,
            param_name=param_name,
            fixed=fixed,
            region_id=self._port.region_id_for_fix_component(component),
        )

    def _commit_fixed_state(
        self,
        components: list[AbsorberComponent],
        *,
        param_name: str,
        fixed: bool,
        region_id: str | None,
    ) -> AnalysisMutationImpact:
        """Commit fixed state, global invalidation, and one history entry."""
        project = self._port.fix_mutation_project()
        if project is None or not components:
            return AnalysisMutationImpact.no_change()
        before_states = tuple(component_parameter_state(component) for component in components)
        target_ids = [component.id for component in components]
        impact = self._mutations.execute(
            project,
            mutate=lambda: self._apply_fixed_state(components, param_name=param_name, fixed=fixed),
            rollback=lambda: self._restore_fixed_states(components, before_states),
            record_history=lambda: self._record_fixed_history(
                components,
                target_ids=target_ids,
                param_name=param_name,
                before_states=before_states,
                region_id=region_id,
            ),
            history_scope=self._port.fix_history_atomic_recording,
        )
        if impact.changed and param_name == "covering_factor":
            seen_parameters: set[int] = set()
            actions = []
            for component in components:
                parameter = component.parameters[param_name]
                if id(parameter) in seen_parameters:
                    continue
                seen_parameters.add(id(parameter))
                actions.append(
                    lambda parameter=parameter: self._port.mark_fix_parameter_initialized(
                        parameter
                    )
                )
            run_postcommit_actions_isolated(*actions)
        return impact

    def _apply_fixed_state(
        self, components: list[AbsorberComponent], *, param_name: str, fixed: bool
    ) -> bool:
        """Apply fixed state to every unique parameter object."""
        changed = False
        processed_parameters: set[int] = set()
        for component in components:
            parameter = component.parameters.get(param_name)
            if parameter is None:
                msg = f"Absorber component {component.id} is missing parameter: {param_name}"
                raise RuntimeError(msg)
            parameter_key = id(parameter)
            if parameter_key in processed_parameters:
                continue
            processed_parameters.add(parameter_key)
            if parameter.fixed == fixed:
                continue
            parameter.fixed = fixed
            component.notify_changed()
            changed = True
        return changed

    def _restore_fixed_states(
        self, components: list[AbsorberComponent], states: tuple[ComponentParameterState, ...]
    ) -> None:
        """Restore exact fixed-state snapshots."""
        restore_component_parameter_states(components, states)

    def _record_fixed_history(
        self,
        components: list[AbsorberComponent],
        *,
        target_ids: list[str],
        param_name: str,
        before_states: tuple[ComponentParameterState, ...],
        region_id: str | None,
    ) -> None:
        """Record one fixed-state history entry inside the transaction."""
        after_states = tuple(component_parameter_state(component) for component in components)
        self._port.record_fix_parameter_edit(
            target_ids, param_name, before_states, after_states, region_id
        )

    @staticmethod
    def _expand_to_affected_components(
        components: Iterable[AbsorberComponent], param_name: str
    ) -> list[AbsorberComponent]:
        """Expand selected components to all affected components for history."""
        affected: dict[str, AbsorberComponent] = {}
        processed_tie_sets: set[int] = set()
        for component in components:
            if component.id in affected:
                continue
            tie_set = effective_tie_set_for_parameter(component, param_name)
            if tie_set is not None:
                if id(tie_set) in processed_tie_sets:
                    continue
                processed_tie_sets.add(id(tie_set))
                for tie_component in tie_set.components:
                    affected[tie_component.id] = tie_component
            else:
                affected[component.id] = component
        return list(affected.values())
