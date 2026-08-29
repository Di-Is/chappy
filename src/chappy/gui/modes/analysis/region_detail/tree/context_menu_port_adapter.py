"""Port adapter backed by named tree context-menu collaborators."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from chappy.core.components.absorber import AbsorberComponent
    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.modes.analysis.region_detail.adapters.confirm_dialog_adapter import (
        OptimizeConfirmDialogAdapter,
    )
    from chappy.gui.modes.analysis.region_detail.adapters.model_mutation_adapter import (
        OptimizeModelMutationAdapter,
    )
    from chappy.gui.modes.analysis.region_detail.parameters.parameter_context_controller import (
        OptimizeParameterContextController,
    )
    from chappy.gui.modes.analysis.region_detail.parameters.parameter_delete_controller import (
        OptimizeParameterDeleteController,
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
    from chappy.gui.modes.analysis.region_detail.views.header_view import RegionDetailHeaderView


@dataclass(frozen=True, slots=True)
class OptimizeTreeContextMenuPortAdapter:
    """Adapt named collaborators for the parameter tree context menu."""

    project_provider: Callable[[], SpectroscopyProject | None]
    parameter_value_controller: OptimizeParameterValueController
    parameter_fix_controller: OptimizeParameterFixController
    parameter_edit_controller: OptimizeParameterEditController
    parameter_delete_controller: OptimizeParameterDeleteController
    parameter_context_controller: OptimizeParameterContextController
    model_mutation_adapter: OptimizeModelMutationAdapter
    confirm_dialog_adapter: OptimizeConfirmDialogAdapter
    header_view: RegionDetailHeaderView
    on_group_combo_changed: Callable[[int], None]

    def ensure_context_covering_factor_parameter(self, component: AbsorberComponent) -> None:
        """Ensure covering factor parameter exists before menu state is evaluated."""
        self.parameter_value_controller.ensure_covering_factor_parameter(component)

    def are_context_components_fixed(
        self, components: Iterable[AbsorberComponent], param_name: str
    ) -> bool:
        """Return whether a parameter is fixed for all selected components."""
        return self.parameter_fix_controller.are_all_components_fixed(components, param_name)

    def handle_context_fix_action(
        self, components: list[AbsorberComponent], param_name: str, fixed: bool
    ) -> None:
        """Apply a fixed-state action to selected components."""
        self.parameter_fix_controller.handle_fix_action_for_components(
            components, param_name, fixed
        )

    def show_context_parameter_dialog(self, component: AbsorberComponent) -> None:
        """Open the parameter adjustment dialog for a component."""
        self.parameter_edit_controller.show_dialog(component)

    def collect_context_delete_targets(
        self, components: Iterable[AbsorberComponent]
    ) -> list[AbsorberComponent]:
        """Collect delete targets for an explicit component selection."""
        return self.model_mutation_adapter.collect_delete_targets(
            components,
            lambda component: self.parameter_context_controller.collect_multiplet_components(
                self.project_provider(), component
            ),
        )

    def collect_context_source_delete_targets(
        self, component: AbsorberComponent
    ) -> list[AbsorberComponent]:
        """Collect delete targets for the context-clicked component."""
        return self.parameter_context_controller.collect_multiplet_components(
            self.project_provider(), component
        )

    def confirm_context_component_deletion(self, components: list[AbsorberComponent]) -> bool:
        """Return whether deletion is confirmed."""
        return self.confirm_dialog_adapter.confirm_component_deletion(len(components))

    def delete_context_components(self, components: list[AbsorberComponent]) -> bool:
        """Delete selected target components."""
        return self.parameter_delete_controller.delete_components(
            self.project_provider(), components
        )

    def refresh_context_group_after_delete(self) -> None:
        """Refresh the current Analysis region UI after deletion."""
        index = self.header_view.current_group_selector_index()
        if index >= 0:
            self.on_group_combo_changed(index)
