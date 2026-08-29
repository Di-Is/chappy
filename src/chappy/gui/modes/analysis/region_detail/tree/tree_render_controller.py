"""Controller for optimize tree render orchestration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from chappy.core.absorption_display import group_lines_by_multiplet, sort_lines_for_display
from chappy.core.components.absorber import AbsorberComponent

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from PySide6.QtWidgets import QTreeWidgetItem

    from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
    from chappy.core.spectroscopy_project import SpectroscopyProject


class OptimizeTreeRenderPort(Protocol):
    """Panel operations required by tree render orchestration."""

    def reload_cosmology_display_cache(self) -> None:
        """Refresh the cached cosmology parameters used for the lookback/comoving columns."""
        ...

    def clear_tree_view(self) -> None:
        """Remove all rendered tree rows."""
        ...

    def apply_empty_tree_state(self) -> None:
        """Refresh dependent controls after an empty tree render."""
        ...

    def sync_tie_labels(self, project: SpectroscopyProject) -> None:
        """Assign display labels to any tie sets not yet seen this session."""
        ...

    def render_tree_groups(
        self,
        groups: tuple[tuple[AbsorptionLine, ...], ...],
        component_index: Mapping[str, AbsorberComponent],
    ) -> None:
        """Render grouped line rows and model child rows."""
        ...

    def apply_region_tree_rendered(self) -> None:
        """Refresh dependent controls after a region tree render."""
        ...

    def iter_component_tree_rows(self) -> Iterable[tuple[QTreeWidgetItem, AbsorberComponent]]:
        """Return rendered component rows and their stored component references."""
        ...

    def refresh_component_tree_row(
        self, item: QTreeWidgetItem, component: AbsorberComponent
    ) -> None:
        """Refresh one rendered component row from a current component."""
        ...


class OptimizeTreeRenderController:
    """Build render inputs for the optimize model tree."""

    def __init__(self, *, port: OptimizeTreeRenderPort) -> None:
        """Initialize the controller.

        Args:
            port: Panel-facing tree render operations.
        """
        self._port = port

    def clear_tree(self) -> None:
        """Clear tree rows and refresh dependent UI state."""
        self._port.clear_tree_view()
        self._port.apply_empty_tree_state()

    def rebuild_region(
        self, project: SpectroscopyProject | None, region: AbsorptionRegion
    ) -> None:
        """Rebuild the tree for an absorption region.

        Args:
            project: Active project, if available.
            region: Region whose lines should be rendered.
        """
        self._port.reload_cosmology_display_cache()
        self._port.clear_tree_view()
        if project is None:
            self._port.apply_empty_tree_state()
            return

        self._port.sync_tie_labels(project)

        lines = tuple(
            project.absorption_lines[line_id]
            for line_id in region.line_ids
            if line_id in project.absorption_lines
        )
        sorted_lines = tuple(sort_lines_for_display(lines))
        component_index = self._component_index(project, sorted_lines)
        groups = tuple(tuple(group) for group in group_lines_by_multiplet(sorted_lines))

        self._port.render_tree_groups(groups, component_index)
        self._port.apply_region_tree_rendered()

    def refresh_model_parameters(self, project: SpectroscopyProject | None) -> None:
        """Refresh rendered component rows from current project model state.

        Args:
            project: Active project, if available.
        """
        if project is None or project.model is None:
            return

        components = {
            component.id: component
            for component in project.model.components
            if isinstance(component, AbsorberComponent)
        }

        for item, rendered_component in self._port.iter_component_tree_rows():
            current_component = components.get(rendered_component.id)
            if current_component is not None:
                self._port.refresh_component_tree_row(item, current_component)

    def _component_index(
        self, project: SpectroscopyProject, lines: tuple[AbsorptionLine, ...]
    ) -> dict[str, AbsorberComponent]:
        """Return absorber components referenced by rendered lines."""
        if project.model is None:
            msg = "Project model is required before rendering optimize tree components."
            raise RuntimeError(msg)

        required_ids: set[str] = set()
        for line in lines:
            required_ids.update(line.model_ids)

        components: dict[str, AbsorberComponent] = {}
        for component_id in required_ids:
            component = project.find_absorber_component(component_id)
            if component is not None:
                components[component_id] = component
        return components
