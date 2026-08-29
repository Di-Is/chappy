"""Port adapters backed by named parameter-editing collaborators."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from chappy.gui.modes.analysis.region_detail.parameters.parameter_edit_controller import (
    OptimizeParameterDialogContext,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager

    from chappy.application.history.ports import TieSetSnapshot
    from chappy.application.optimize import ModelDeletionHistorySnapshot
    from chappy.core.components.absorber import AbsorberComponent
    from chappy.core.components.base import Parameter
    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.modes.analysis.region_detail.adapters.confirm_dialog_adapter import (
        OptimizeConfirmDialogAdapter,
    )
    from chappy.gui.modes.analysis.region_detail.adapters.history_adapter import (
        ComponentParameterState,
        OptimizeHistoryAdapter,
    )
    from chappy.gui.modes.analysis.region_detail.group_selection_controller import (
        OptimizeGroupSelectionController,
    )
    from chappy.gui.modes.analysis.region_detail.parameters.parameter_context_controller import (
        OptimizeParameterContextController,
    )
    from chappy.gui.modes.analysis.region_detail.parameters.parameter_edit_controller import (
        OptimizeParameterEditController,
    )
    from chappy.gui.modes.analysis.region_detail.parameters.parameter_fix_controller import (
        OptimizeParameterFixController,
    )
    from chappy.gui.modes.analysis.region_detail.parameters.parameter_value_controller import (
        OptimizeParameterValueController,
    )
    from chappy.gui.modes.analysis.region_detail.tree.tree_view import RegionDetailTreeView
    from chappy.gui.modes.analysis.region_detail.views.header_view import RegionDetailHeaderView


@dataclass(frozen=True, slots=True)
class OptimizeParameterValuePortAdapter:
    """Adapt named collaborators for parameter value edits."""

    project_provider: Callable[[], SpectroscopyProject | None]
    history_adapter: OptimizeHistoryAdapter
    group_selection_controller_provider: Callable[[], OptimizeGroupSelectionController]
    tree_view: RegionDetailTreeView
    validate_value: Callable[[str, float, AbsorberComponent], bool]
    emit_parameter_changed: Callable[[str, float], None]

    def value_mutation_project(self) -> SpectroscopyProject | None:
        """Return the active project for a scientific parameter transaction."""
        return self.project_provider()

    def value_history_atomic_recording(self) -> AbstractContextManager[None]:
        """Return a history rollback scope for a scientific parameter edit."""
        return self.history_adapter.atomic_recording()

    def validate_parameter_value(
        self, param_name: str, value: float, component: AbsorberComponent
    ) -> bool:
        """Return whether a candidate parameter value is valid."""
        return self.validate_value(param_name, value, component)

    def emit_parameter_value_changed(self, param_name: str, value: float) -> None:
        """Emit a parameter value change to collaborators."""
        self.emit_parameter_changed(param_name, value)

    def refresh_parameter_tree_values(self, component_ids: tuple[str, ...]) -> None:
        """Refresh the rendered tree rows for affected component IDs."""
        self.tree_view.update_parameter_values(component_ids)

    def region_id_for_value_component(self, component: AbsorberComponent) -> str | None:
        """Return the region id associated with a component."""
        return self.group_selection_controller_provider().region_id_for_component(
            self.project_provider(), component
        )

    def current_value_group_id(self) -> str | None:
        """Return the region currently focused in Analysis Detail."""
        return self.group_selection_controller_provider().current_group_id()

    def record_value_parameter_edit(
        self,
        component_ids: list[str],
        param_name: str,
        before_states: tuple[ComponentParameterState, ...],
        after_states: tuple[ComponentParameterState, ...],
        region_id: str | None,
    ) -> None:
        """Record a parameter value edit in history."""
        self.history_adapter.record_parameter_edit(
            component_ids, param_name, before_states, after_states, region_id
        )


@dataclass(frozen=True, slots=True)
class OptimizeParameterFixPortAdapter:
    """Adapt named collaborators for parameter fixed-state edits."""

    project_provider: Callable[[], SpectroscopyProject | None]
    history_adapter: OptimizeHistoryAdapter
    group_selection_controller_provider: Callable[[], OptimizeGroupSelectionController]
    parameter_value_controller: OptimizeParameterValueController
    parameter_edit_controller: OptimizeParameterEditController
    tree_view: RegionDetailTreeView

    def fix_mutation_project(self) -> SpectroscopyProject | None:
        """Return the active project for a fixed-state transaction."""
        return self.project_provider()

    def fix_history_atomic_recording(self) -> AbstractContextManager[None]:
        """Return a history rollback scope for a fixed-state edit."""
        return self.history_adapter.atomic_recording()

    def mark_fix_parameter_initialized(self, parameter: Parameter) -> None:
        """Mark a parameter as initialized by the optimize workflow."""
        self.parameter_value_controller.mark_parameter_initialized(parameter)

    def region_id_for_fix_component(self, component: AbsorberComponent) -> str | None:
        """Return the region id associated with a component."""
        return self.group_selection_controller_provider().region_id_for_component(
            self.project_provider(), component
        )

    def current_fix_group_id(self) -> str | None:
        """Return the region currently focused in Analysis Detail."""
        return self.group_selection_controller_provider().current_group_id()

    def record_fix_parameter_edit(
        self,
        component_ids: list[str],
        param_name: str,
        before_states: tuple[ComponentParameterState, ...],
        after_states: tuple[ComponentParameterState, ...],
        region_id: str | None,
    ) -> None:
        """Record a parameter fixed-state edit."""
        self.history_adapter.record_parameter_edit(
            component_ids, param_name, before_states, after_states, region_id
        )

    def refresh_fix_parameter_styles(self) -> None:
        """Refresh parameter row styles after fixed-state changes."""
        self.tree_view.refresh_parameter_styles()

    def refresh_fix_parameter_dialog(self) -> None:
        """Refresh the parameter edit dialog after fixed-state changes."""
        self.parameter_edit_controller.refresh_dialog()


@dataclass(frozen=True, slots=True)
class OptimizeParameterDeletePortAdapter:
    """Adapt the history adapter for component deletion."""

    history_adapter: OptimizeHistoryAdapter

    def record_delete_components(self, snapshot: ModelDeletionHistorySnapshot) -> None:
        """Record immutable component deletion state after scientific commit."""
        self.history_adapter.record_delete(snapshot)

    def delete_history_atomic_recording(self) -> AbstractContextManager[None]:
        """Return the required atomic history scope."""
        return self.history_adapter.atomic_recording()


@dataclass(frozen=True, slots=True)
class OptimizeParameterEditPortAdapter:
    """Adapt named collaborators for the parameter edit dialog."""

    project_provider: Callable[[], SpectroscopyProject | None]
    parameter_context_controller: OptimizeParameterContextController
    parameter_fix_controller_provider: Callable[[], OptimizeParameterFixController]
    tree_view: RegionDetailTreeView
    apply_parameter_value: Callable[[AbsorberComponent, str, float], bool]

    def parameter_dialog_context(
        self, component: AbsorberComponent
    ) -> OptimizeParameterDialogContext:
        """Return display context for the parameter dialog."""
        project = self.project_provider()
        line = self.parameter_context_controller.line_for_component(project, component)
        z_bounds = self.parameter_context_controller.z_bounds(component, line)
        line_display_id = self.parameter_context_controller.line_display_id(project, line)
        component_index = self.parameter_context_controller.component_index(component, line)
        return OptimizeParameterDialogContext(
            component,
            line=line,
            z_bounds=z_bounds,
            line_display_id=line_display_id,
            component_index=component_index,
        )

    def apply_parameter_dialog_value(
        self, component: AbsorberComponent, param_name: str, value: float
    ) -> bool:
        """Apply a value edited in the parameter dialog."""
        return self.apply_parameter_value(component, param_name, value)

    def set_parameter_dialog_fixed_state(
        self, component: AbsorberComponent, param_name: str, fixed: bool
    ) -> None:
        """Apply a fixed-state change edited in the parameter dialog."""
        self.parameter_fix_controller_provider().set_fixed_state(component, param_name, fixed)
        self.tree_view.refresh_parameter_styles()


@dataclass(frozen=True, slots=True)
class OptimizeTieSetEditPortAdapter:
    """Adapt named collaborators for tie set share/remove actions."""

    project_provider: Callable[[], SpectroscopyProject | None]
    history_adapter: OptimizeHistoryAdapter
    confirm_dialog_adapter: OptimizeConfirmDialogAdapter
    header_view: RegionDetailHeaderView
    on_group_combo_changed: Callable[[int], None]

    def tie_set_edit_project(self) -> SpectroscopyProject | None:
        """Return the active project."""
        return self.project_provider()

    def confirm_tie_set_redshift_divergence(
        self, max_delta_z: float, adopted_redshift: float
    ) -> bool:
        """Return whether the user confirmed sharing despite redshift divergence."""
        return self.confirm_dialog_adapter.confirm_tie_set_redshift_divergence(
            max_delta_z, adopted_redshift
        )

    def record_tie_set_created(
        self,
        uid: str,
        before_component_states: tuple[ComponentParameterState, ...],
        after_tie_set: TieSetSnapshot,
        after_tie_set_index: int,
    ) -> None:
        """Record tie set creation in history."""
        self.history_adapter.record_tie_set_create(
            uid, before_component_states, after_tie_set, after_tie_set_index
        )

    def record_tie_set_removed(
        self,
        uids: tuple[str, ...],
        before_tie_sets: tuple[TieSetSnapshot, ...],
        before_tie_set_indices: tuple[int, ...],
        after_tie_sets: tuple[TieSetSnapshot, ...],
        after_tie_set_indices: tuple[int, ...],
        after_component_states: tuple[ComponentParameterState, ...],
    ) -> None:
        """Record tie set member removal or dissolution in history."""
        self.history_adapter.record_tie_set_remove(
            uids,
            before_tie_sets,
            before_tie_set_indices,
            after_tie_sets,
            after_tie_set_indices,
            after_component_states,
        )

    def refresh_after_tie_set_edit(self) -> None:
        """Refresh the tree and dependent panel state after a tie set edit."""
        index = self.header_view.current_group_selector_index()
        if index >= 0:
            self.on_group_combo_changed(index)

    def tie_set_history_atomic_recording(self) -> AbstractContextManager[None]:
        """Return the required atomic history scope."""
        return self.history_adapter.atomic_recording()
