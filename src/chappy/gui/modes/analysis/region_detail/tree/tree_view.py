"""Region Detail parameter tree: widget, row/selection/style controllers, and editing."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QAbstractItemView

from chappy.core.components.tie_set import effective_tie_set_for_parameter
from chappy.gui.modes.analysis.region_detail.composition import (
    create_optimize_tree_header_controller,
    create_optimize_tree_render_controller,
    create_optimize_tree_row_renderer,
    create_optimize_tree_selection_controller,
    create_optimize_tree_style_controller,
    create_optimize_tree_view_adapter,
)
from chappy.gui.modes.analysis.region_detail.tree.tie_label_allocator import (
    OptimizeTieLabelAllocator,
)
from chappy.gui.modes.analysis.region_detail.tree.tree_columns import (
    COLUMNS,
    PARAMETER_CONFIGS,
    ColumnMeta,
)
from chappy.gui.modes.analysis.region_detail.tree.tree_edit_controller import (
    OptimizeTreeEditController,
)
from chappy.gui.modes.analysis.region_detail.tree.tree_style_controller import (
    component_needs_optimization,
)
from chappy.gui.modes.analysis.region_detail.tree.tree_widget import (
    BackgroundAwareItemDelegate,
    OptimizeTreeWidget,
)
from chappy.presentation.interaction.interaction_contracts import OptimizeLineSelectionChange

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

    from PySide6.QtWidgets import QTreeWidgetItem, QWidget

    from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
    from chappy.core.components.absorber import AbsorberComponent
    from chappy.core.components.base import Parameter
    from chappy.core.cosmology import CosmologyParameters
    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.modes.analysis.region_detail.state import RegionDetailViewState
    from chappy.gui.modes.analysis.region_detail.tree.tree_header_controller import SavedTreeHeader

_PARAMETER_DISPLAY_SOURCE: dict[str, str] = {
    param_name: COLUMNS[value_column].source_text
    for param_name, value_column, _fmt, _default in PARAMETER_CONFIGS
}


class RegionDetailTreeView:
    """Owns the optimize parameter tree widget and its rendering/editing collaborators.

    Not a ``QWidget``: the shell docks the raw tree widget directly (see
    ``RegionDetailPanel.parameter_tree_widget``), so this view has no layout of
    its own to build. It implements the tree-facing controller ports directly
    (``OptimizeTreeSelectionPort``, ``OptimizeTreeRowRenderPort``,
    ``OptimizeTreeStylePort``, ``OptimizeTreeRenderPort``,
    ``OptimizeTreeHeaderPort``, and group selection's ``RegionTreeRenderPort``)
    instead of going through separate forwarding adapters.
    """

    def __init__(  # noqa: PLR0913 - collaborators are injected explicitly, one per responsibility
        self,
        *,
        parent: QWidget,
        project_provider: Callable[[], SpectroscopyProject | None],
        view_state: RegionDetailViewState,
        ensure_covering_factor_parameter: Callable[[AbsorberComponent], Parameter],
        request_action_state_refresh: Callable[[], None],
        request_export_controls_refresh: Callable[[], None],
        emit_line_selected: Callable[[OptimizeLineSelectionChange], None],
        apply_parameter_value: Callable[[AbsorberComponent, str, float], bool],
        reset_component_parameter: Callable[[QTreeWidgetItem, int, AbsorberComponent, str], None],
        apply_line_analysis_half_width: Callable[[QTreeWidgetItem, int], None],
        load_tree_header_state: Callable[[], SavedTreeHeader | None],
        save_tree_header_state: Callable[[SavedTreeHeader], None],
        load_cosmology_parameters: Callable[[], CosmologyParameters],
    ) -> None:
        """Initialize the tree view and its owned controllers.

        Args:
            parent: Owning panel widget, used to parent the tree widget and its
                header customization menu.
            project_provider: Returns the active project, if any.
            view_state: UI-projection state written by tree selection changes.
            ensure_covering_factor_parameter: Registers a component's covering
                factor parameter before it is styled or rendered.
            request_action_state_refresh: Refreshes action/summary display after
                a selection or render change.
            request_export_controls_refresh: Refreshes export controls after a
                region tree render.
            emit_line_selected: Emits the panel's line-selection change signal.
            apply_parameter_value: Applies a validated component parameter edit.
            reset_component_parameter: Restores a component parameter cell after
                a rejected or unparsable edit.
            apply_line_analysis_half_width: Applies one scientific half-width
                cell edit.
            load_tree_header_state: Returns the persisted header layout, if any.
            save_tree_header_state: Persists the header layout.
            load_cosmology_parameters: Returns cosmology parameters used for the
                lookback/comoving columns.
        """
        self._project_provider = project_provider
        self._view_state = view_state
        self._ensure_covering_factor_parameter = ensure_covering_factor_parameter
        self._request_action_state_refresh = request_action_state_refresh
        self._request_export_controls_refresh = request_export_controls_refresh
        self._emit_line_selected = emit_line_selected
        self._load_tree_header_state = load_tree_header_state
        self._save_tree_header_state = save_tree_header_state
        self._load_cosmology_parameters = load_cosmology_parameters

        self._suppress_item_changed = False
        self._tie_label_allocator = OptimizeTieLabelAllocator()
        self._display_cosmology = load_cosmology_parameters()

        self.tree = OptimizeTreeWidget(parent=parent)
        self.tree.setObjectName("analysisDetailParameterTree")
        self.tree.setColumnCount(len(COLUMNS))
        self.tree.setHeaderLabels(self._column_headers())
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setIndentation(20)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tree.setAllColumnsShowFocus(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.setItemDelegate(BackgroundAwareItemDelegate(self.tree))

        self._selection_controller = create_optimize_tree_selection_controller(
            tree=self.tree, port=self
        )
        self._style_controller = create_optimize_tree_style_controller(port=self)
        self._row_renderer = create_optimize_tree_row_renderer(port=self)
        self._view_adapter = create_optimize_tree_view_adapter(
            tree=self.tree,
            row_renderer=self._row_renderer,
            set_item_changed_suppressed=self._set_item_changed_suppressed,
            on_selection_changed=self._on_selection_changed,
        )
        self._render_controller = create_optimize_tree_render_controller(port=self)
        self._header_controller = create_optimize_tree_header_controller(
            tree=self.tree, parent=parent, port=self
        )
        self._header_controller.initialize()
        self.tree.viewport_resized.connect(self._header_controller.on_viewport_resized)

        self._edit_controller = OptimizeTreeEditController(
            apply_parameter_value=apply_parameter_value,
            reset_component_parameter=reset_component_parameter,
            apply_line_analysis_half_width=apply_line_analysis_half_width,
        )

        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)

    # -- Public panel-facing API --------------------------------------------

    @property
    def tie_label_allocator(self) -> OptimizeTieLabelAllocator:
        """Return the tie-label allocator shared with the context menu controller."""
        return self._tie_label_allocator

    def retranslate(self) -> None:
        """Reapply translated column headers."""
        self.tree.setHeaderLabels(self._column_headers())

    def clear(self) -> None:
        """Clear rendered rows and refresh dependent controls."""
        self._render_controller.clear_tree()

    def rebuild_region(
        self, project: SpectroscopyProject | None, region: AbsorptionRegion
    ) -> None:
        """Rebuild the tree for one absorption region."""
        self._render_controller.rebuild_region(project, region)

    def refresh_model_parameters(self, project: SpectroscopyProject | None) -> None:
        """Refresh rendered component rows from current project model state."""
        self._render_controller.refresh_model_parameters(project)

    def focus_component(self, component_id: str) -> None:
        """Highlight the tree row corresponding to the component identifier."""
        self._view_adapter.focus_component(component_id)

    def select_component_for_line(
        self, line: AbsorptionLine, component: AbsorberComponent | None
    ) -> None:
        """Select and start editing a component row under a line row."""
        self._view_adapter.select_component_for_line(line, component)

    def refresh_component_row(self, item: QTreeWidgetItem, component: AbsorberComponent) -> None:
        """Refresh one rendered component row from a current component."""
        self._view_adapter.refresh_component_row(item, component)

    def refresh_analysis_half_width_rows(
        self, project: SpectroscopyProject, affected_line_ids: tuple[str, ...]
    ) -> None:
        """Refresh rendered line-group half-width cells without rebuilding the tree."""
        self._view_adapter.refresh_analysis_half_width_rows(project, affected_line_ids)

    def update_parameter_values(self, component_ids: tuple[str, ...]) -> None:
        """Refresh every rendered row whose component ID was affected."""
        self._view_adapter.update_parameter_values(component_ids)

    def has_rendered_rows(self) -> bool:
        """Return whether the tree currently has any top-level rows."""
        return self.tree.topLevelItemCount() > 0

    def tie_label_for_uid(self, uid: str) -> str | None:
        """Return the display label allocated for one tie-set uid, if assigned."""
        return self._tie_label_allocator.label_for(uid)

    def refresh_parameter_styles(self) -> None:
        """Refresh parameter cell styles for every rendered component row."""
        self._style_controller.refresh_parameter_styles(
            items=self._view_adapter.iter_model_items(), project=self._project_provider()
        )

    def _set_item_changed_suppressed(self, suppressed: bool) -> None:
        self._suppress_item_changed = suppressed

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._suppress_item_changed:
            return
        self._edit_controller.item_changed(item, column)

    def _on_selection_changed(self) -> None:
        self._selection_controller.selection_changed()

    def _column_label_for(self, meta: ColumnMeta) -> str:
        return QCoreApplication.translate("RegionDetailPanel", meta.source_text)

    def _column_headers(self) -> list[str]:
        return [self._column_label_for(meta) for meta in COLUMNS]

    # -- OptimizeTreeSelectionPort -------------------------------------------

    def clear_selected_line(self) -> None:
        """Clear the selected line and notify dependent controls."""
        self._view_state.set_selected_line_id(None)
        self._request_action_state_refresh()
        self._emit_line_selected_change(None, None)

    def select_line_from_tree(self, line: AbsorptionLine, component_id: str | None) -> None:
        """Record a line selected from the tree and notify dependent controls."""
        self._view_state.set_selected_line_id(line.line_id)
        self._request_action_state_refresh()
        self._emit_line_selected_change(line, component_id)

    def _emit_line_selected_change(
        self, line: AbsorptionLine | None, component_id: str | None
    ) -> None:
        self._emit_line_selected(OptimizeLineSelectionChange(line=line, component_id=component_id))

    # -- OptimizeTreeRowRenderPort / OptimizeTreeStylePort -------------------

    def tree_display_name_for_line(self, line: AbsorptionLine) -> str:
        """Return the display label for an absorption line row."""
        display_name = ""
        project = self._project_provider()
        if project is not None:
            for model_id in line.model_ids:
                component = project.find_absorber_component(model_id)
                if component is not None and component.atomic_line is not None:
                    atomic_line = component.atomic_line
                    display_name = atomic_line.multiplet_label or atomic_line.transition_name
                    if display_name:
                        break

        if not display_name:
            display_name = line.transition_name
        return display_name

    def ensure_tree_covering_factor_parameter(self, component: AbsorberComponent) -> None:
        """Ensure the component has a covering factor parameter."""
        self._ensure_covering_factor_parameter(component)

    def apply_tree_parameter_styles(self, item: QTreeWidgetItem) -> None:
        """Apply parameter-related cell styles to a rendered model row."""
        self._style_controller.apply_parameter_styles(item, self._project_provider())

    def tie_label_for(self, component: AbsorberComponent, parameter_name: str) -> str | None:
        """Return the tie-set display label for a masked parameter cell, if tied."""
        tie_set = effective_tie_set_for_parameter(component, parameter_name)
        if tie_set is None:
            return None
        return self._tie_label_allocator.label_for(tie_set.uid)

    def is_tree_component_stale(self, component: AbsorberComponent) -> bool:
        """Return whether the component needs re-optimization."""
        return component_needs_optimization(self._project_provider(), component)

    def tree_cosmology_parameters(self) -> CosmologyParameters:
        """Return the cached cosmology parameters used for lookback/comoving columns."""
        return self._display_cosmology

    def tie_tooltip_for(self, component: AbsorberComponent, parameter_name: str) -> str | None:
        """Return the tie-set tooltip text for a masked parameter cell, if tied."""
        tie_set = effective_tie_set_for_parameter(component, parameter_name)
        if tie_set is None:
            return None
        label = self._tie_label_allocator.label_for(tie_set.uid)
        members = ", ".join(member.name for member in tie_set.components)
        parameter_label = QCoreApplication.translate(
            "RegionDetailPanel", _PARAMETER_DISPLAY_SOURCE.get(parameter_name, parameter_name)
        )
        template = QCoreApplication.translate(
            "RegionDetailPanel", "Shared {parameter} [{label}]: {members}"
        )
        return template.format(parameter=parameter_label, label=label, members=members)

    def tie_accent_index_for(
        self, component: AbsorberComponent, parameter_name: str
    ) -> int | None:
        """Return the tie-set accent palette index for a masked parameter cell, if tied."""
        tie_set = effective_tie_set_for_parameter(component, parameter_name)
        if tie_set is None:
            return None
        return self._tie_label_allocator.index_for(tie_set.uid)

    # -- OptimizeTreeRenderPort ------------------------------------------------

    def reload_cosmology_display_cache(self) -> None:
        """Refresh the cached cosmology parameters used for the lookback/comoving columns."""
        self._display_cosmology = self._load_cosmology_parameters()

    def clear_tree_view(self) -> None:
        """Remove all rendered tree rows."""
        self._view_adapter.clear()

    def apply_empty_tree_state(self) -> None:
        """Refresh dependent controls after an empty tree render."""
        self._request_action_state_refresh()

    def sync_tie_labels(self, project: SpectroscopyProject) -> None:
        """Assign display labels to any tie sets not yet seen this session."""
        if project.model is None:
            return
        self._tie_label_allocator.assign_all(
            tie_set.uid for tie_set in project.model.iter_tie_sets()
        )

    def render_tree_groups(
        self,
        groups: tuple[tuple[AbsorptionLine, ...], ...],
        component_index: Mapping[str, AbsorberComponent],
    ) -> None:
        """Render grouped line rows and model child rows."""
        self._view_adapter.render_groups(groups, component_index)

    def apply_region_tree_rendered(self) -> None:
        """Refresh dependent controls after a region tree render."""
        self._request_action_state_refresh()
        self.refresh_parameter_styles()
        self._request_export_controls_refresh()
        self._header_controller.on_tree_populated()

    def iter_component_tree_rows(self) -> Iterable[tuple[QTreeWidgetItem, AbsorberComponent]]:
        """Return rendered component rows and their stored component references."""
        return self._view_adapter.iter_component_rows()

    def refresh_component_tree_row(
        self, item: QTreeWidgetItem, component: AbsorberComponent
    ) -> None:
        """Refresh one rendered component row from a current component."""
        self._view_adapter.refresh_component_row(item, component)

    # -- OptimizeTreeHeaderPort ------------------------------------------------

    def load_tree_header_state(self) -> SavedTreeHeader | None:
        """Return the persisted header layout, if any."""
        return self._load_tree_header_state()

    def save_tree_header_state(self, saved: SavedTreeHeader) -> None:
        """Persist the header layout."""
        self._save_tree_header_state(saved)

    # -- RegionTreeRenderPort (group selection controller) ---------------------

    def clear_group_tree(self) -> None:
        """Clear the optimize tree."""
        self.clear()

    def render_group_region_tree(self, region: AbsorptionRegion) -> None:
        """Render the tree for the selected region."""
        self.rebuild_region(self._project_provider(), region)

    def refresh_group_parameter_styles(self) -> None:
        """Refresh parameter styles tied to optimization state."""
        self.refresh_parameter_styles()
