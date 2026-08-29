"""Tree context-menu controller for optimize mode."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Protocol

from PySide6.QtCore import QCoreApplication, QItemSelectionModel, QPoint, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QMenu,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
    QWidgetAction,
)

from chappy.application.analysis_artifacts import run_postcommit_actions_isolated
from chappy.core.components.absorber import AbsorberComponent
from chappy.gui.modes.analysis.region_detail.parameters.parameter_fix_controller import (
    OptimizeParameterFixController,
)
from chappy.gui.modes.analysis.region_detail.tree.tree_columns import (
    COLUMNS,
    PARAMETER_COLUMNS,
    ColumnMeta,
)
from chappy.gui.theme import create_styled_menu

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from PySide6.QtGui import QMouseEvent

    from chappy.gui.modes.analysis.region_detail.tie_set_edit_controller import (
        OptimizeTieSetEditController,
    )


class OptimizeTreeContextMenuPort(Protocol):
    """Workflow boundary required by the tree context-menu controller."""

    def ensure_context_covering_factor_parameter(self, component: AbsorberComponent) -> None:
        """Ensure covering factor parameter exists before menu state is evaluated."""
        ...

    def are_context_components_fixed(
        self, components: Iterable[AbsorberComponent], param_name: str
    ) -> bool:
        """Return whether a parameter is fixed for all selected components."""
        ...

    def handle_context_fix_action(
        self, components: list[AbsorberComponent], param_name: str, fixed: bool
    ) -> None:
        """Apply a fixed-state action to selected components."""
        ...

    def show_context_parameter_dialog(self, component: AbsorberComponent) -> None:
        """Open the parameter adjustment dialog for a component."""
        ...

    def collect_context_delete_targets(
        self, components: Iterable[AbsorberComponent]
    ) -> list[AbsorberComponent]:
        """Collect delete targets for an explicit component selection."""
        ...

    def collect_context_source_delete_targets(
        self, component: AbsorberComponent
    ) -> list[AbsorberComponent]:
        """Collect delete targets for the context-clicked component."""
        ...

    def confirm_context_component_deletion(self, components: list[AbsorberComponent]) -> bool:
        """Return whether deletion is confirmed."""
        ...

    def delete_context_components(self, components: list[AbsorberComponent]) -> bool:
        """Delete selected target components and return whether state changed."""
        ...

    def refresh_context_group_after_delete(self) -> None:
        """Refresh the current Analysis region UI after deletion."""
        ...


class _MenuItemLabel(QLabel):
    """Menu row widget that stays hoverable so a disabled item's tooltip is shown.

    Plain ``QAction`` items rendered by ``QMenu`` don't reliably surface
    tooltips while disabled (a known Qt limitation), so disabled-with-reason
    items use a real widget instead: it keeps native hover/tooltip behavior
    and only gates the click callback on ``enabled``.
    """

    def __init__(
        self,
        text: str,
        menu: QMenu,
        *,
        enabled: bool,
        on_activate: Callable[[], None],
        tooltip: str | None,
    ) -> None:
        """Initialize the menu row label.

        Args:
            text: Row display text.
            menu: Owning menu, closed on activation.
            enabled: Whether the action can be triggered.
            on_activate: Callback invoked when an enabled row is clicked.
            tooltip: Tooltip shown on hover, typically the disabled reason.
        """
        super().__init__(text, menu)
        self._menu = menu
        self._enabled = enabled
        self._on_activate = on_activate
        self.setProperty("menuRowEnabled", enabled)
        if tooltip:
            self.setToolTip(tooltip)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        """Trigger the action on release and close the menu, when enabled."""
        if self._enabled and event.button() == Qt.MouseButton.LeftButton:
            self._menu.close()
            self._on_activate()
        super().mouseReleaseEvent(event)


class OptimizeTreeContextMenuController:
    """Coordinate optimize parameter tree context-menu actions."""

    def __init__(
        self,
        *,
        tree: QTreeWidget,
        parent: QWidget,
        port: OptimizeTreeContextMenuPort,
        tie_set_edit: OptimizeTieSetEditController,
        tie_label_for_uid: Callable[[str], str | None],
    ) -> None:
        """Initialize the controller.

        Args:
            tree: Parameter tree widget.
            parent: Parent widget for menu construction.
            port: Workflow boundary.
            tie_set_edit: Tie set share/remove predicates and actions.
            tie_label_for_uid: Resolve the display label for a tie set uid.
        """
        self._tree = tree
        self._parent = parent
        self._port = port
        self._tie_set_edit = tie_set_edit
        self._tie_label_for_uid = tie_label_for_uid

    def select_item_for_context_menu(self, item: QTreeWidgetItem) -> None:
        """Ensure the context-clicked tree item participates in the selection.

        Args:
            item: Tree item under the context-menu request.
        """
        if item.isSelected():
            return

        selection_model = self._tree.selectionModel()
        if selection_model is None:
            return

        index = self._tree.indexFromItem(item, 0)
        if not index.isValid():
            return

        selection_flags = (
            QItemSelectionModel.SelectionFlag.ClearAndSelect
            | QItemSelectionModel.SelectionFlag.Rows
        )
        selection_model.select(index, selection_flags)
        self._tree.setCurrentIndex(index)

    def selected_components(self) -> list[AbsorberComponent]:
        """Return absorber components selected in the tree.

        Returns:
            Selected absorber components, de-duplicated by component id.
        """
        seen_ids: set[str] = set()
        components: list[AbsorberComponent] = []
        for selected_item in self._tree.selectedItems():
            payload = selected_item.data(0, Qt.ItemDataRole.UserRole)
            if not isinstance(payload, AbsorberComponent):
                continue

            component_id = payload.id
            if not isinstance(component_id, str) or component_id in seen_ids:
                continue

            seen_ids.add(component_id)
            components.append(payload)
        return components

    def collect_delete_targets(
        self, components: Iterable[AbsorberComponent]
    ) -> list[AbsorberComponent]:
        """Collect components to delete, expanding multiplet-linked entries."""
        return self._port.collect_context_delete_targets(components)

    def delete_models(self, source_component: AbsorberComponent) -> None:
        """Delete one or more components based on the current selection.

        Args:
            source_component: Component under the context-menu invocation.
        """
        selected_components = self.selected_components()
        targets = (
            self.collect_delete_targets(selected_components)
            if len(selected_components) > 1
            else self._port.collect_context_source_delete_targets(source_component)
        )

        if not targets:
            return

        if not self._port.confirm_context_component_deletion(targets):
            return

        if self._port.delete_context_components(targets):
            run_postcommit_actions_isolated(self._port.refresh_context_group_after_delete)

    def show_context_menu(self, point: QPoint) -> None:
        """Show context menu for a parameter tree point.

        Args:
            point: Point in tree viewport coordinates.
        """
        item = self._tree.itemAt(point)
        if item is None:
            return

        component = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(component, AbsorberComponent):
            return

        self.select_item_for_context_menu(item)
        selected_components = self.selected_components()
        if not selected_components:
            return

        for selected_component in selected_components:
            self._port.ensure_context_covering_factor_parameter(selected_component)

        menu = create_styled_menu(self._parent)

        parameter_added = False
        for column, param_name in PARAMETER_COLUMNS.items():
            meta = COLUMNS[column]
            label = self._context_column_label(meta)
            checkbox = QCheckBox(
                self._context_fix_action_label(label, selected_components, param_name), menu
            )
            checkbox.setChecked(
                self._port.are_context_components_fixed(selected_components, param_name)
            )
            checkbox.toggled.connect(
                partial(self._port.handle_context_fix_action, selected_components, param_name)
            )
            widget_action = QWidgetAction(menu)
            widget_action.setDefaultWidget(checkbox)
            menu.addAction(widget_action)
            parameter_added = True

        if parameter_added:
            menu.addSeparator()

        adjust_action = menu.addAction(self._context_adjust_parameters_label())
        adjust_action.setEnabled(len(selected_components) == 1)
        adjust_action.triggered.connect(
            lambda: self._port.show_context_parameter_dialog(component)
        )
        menu.addSeparator()

        delete_action = menu.addAction(self._context_delete_component_label())
        delete_action.triggered.connect(lambda: self.delete_models(component))
        menu.addSeparator()

        self._add_tie_set_menu_items(menu, selected_components)

        global_pos = self._tree.viewport().mapToGlobal(point)
        menu.exec(global_pos)

    def _add_tie_set_menu_items(
        self, menu: QMenu, selected_components: list[AbsorberComponent]
    ) -> None:
        """Append the share/remove parameter tie set rows to the context menu."""
        controller = self._tie_set_edit
        entries = (
            (
                QCoreApplication.translate("RegionDetailPanel", "Share z"),
                controller.can_share_redshift(selected_components),
                self._context_share_redshift_tooltip(selected_components),
                partial(controller.share_redshift, tuple(selected_components)),
            ),
            (
                QCoreApplication.translate("RegionDetailPanel", "Share z and b"),
                controller.can_share_redshift_and_b(selected_components),
                self._context_share_redshift_tooltip(selected_components),
                partial(controller.share_redshift_and_b, tuple(selected_components)),
            ),
            (
                QCoreApplication.translate("RegionDetailPanel", "Share all parameters"),
                controller.can_share_all_parameters(selected_components),
                self._context_share_all_parameters_tooltip(selected_components),
                partial(controller.share_all_parameters, tuple(selected_components)),
            ),
            (
                QCoreApplication.translate("RegionDetailPanel", "Remove from shared group"),
                controller.can_remove_from_shared_group(selected_components),
                self._context_remove_from_shared_group_tooltip(selected_components),
                partial(controller.remove_from_shared_group, tuple(selected_components)),
            ),
            (
                QCoreApplication.translate("RegionDetailPanel", "Remove from external sharing"),
                controller.can_remove_from_external_group(selected_components),
                self._context_remove_from_external_group_tooltip(selected_components),
                partial(controller.remove_from_external_group, tuple(selected_components)),
            ),
        )
        for text, enabled, tooltip, on_activate in entries:
            label = _MenuItemLabel(
                text, menu, enabled=enabled, on_activate=on_activate, tooltip=tooltip
            )
            widget_action = QWidgetAction(menu)
            widget_action.setDefaultWidget(label)
            menu.addAction(widget_action)

    @staticmethod
    def _context_column_label(meta: ColumnMeta) -> str:
        """Return localized display label for a tree column."""
        return QCoreApplication.translate("RegionDetailPanel", meta.source_text)

    def _context_fix_action_label(
        self, parameter_label: str, components: list[AbsorberComponent], param_name: str
    ) -> str:
        """Return localized fixed-state menu label."""
        tie_set = OptimizeParameterFixController.resolve_shared_fix_target(components, param_name)
        if tie_set is not None:
            tie_label = self._tie_label_for_uid(tie_set.uid)
            if tie_label is not None:
                template = QCoreApplication.translate(
                    "RegionDetailPanel", "Fix {parameter} (shared {label}, {count} components)"
                )
                return template.format(
                    parameter=parameter_label, label=tie_label, count=len(tie_set.components)
                )
        return QCoreApplication.translate("RegionDetailPanel", "Fix {parameter}").format(
            parameter=parameter_label
        )

    @staticmethod
    def _context_adjust_parameters_label() -> str:
        """Return localized adjust-parameters label."""
        return QCoreApplication.translate("RegionDetailPanel", "Adjust parameters...")

    @staticmethod
    def _context_delete_component_label() -> str:
        """Return localized delete-component label."""
        return QCoreApplication.translate("RegionDetailPanel", "Delete Component")

    def _context_share_redshift_tooltip(
        self, components: Iterable[AbsorberComponent]
    ) -> str | None:
        """Return the disabled-state tooltip for share-redshift, or None when enabled."""
        components = tuple(components)
        controller = self._tie_set_edit
        if not controller.has_min_component_count(components):
            return QCoreApplication.translate("RegionDetailPanel", "Select two or more components")
        if not controller.can_share_redshift(components):
            return QCoreApplication.translate(
                "RegionDetailPanel",
                "Only untied components or full shared groups can join external sharing",
            )
        return None

    def _context_share_all_parameters_tooltip(
        self, components: Iterable[AbsorberComponent]
    ) -> str | None:
        """Return the disabled-state tooltip for share-all-parameters, or None when enabled."""
        components = tuple(components)
        base_tooltip = self._context_share_redshift_tooltip(components)
        if base_tooltip is not None:
            return base_tooltip
        controller = self._tie_set_edit
        if not controller.same_species(components):
            return QCoreApplication.translate(
                "RegionDetailPanel", "Full sharing requires components of the same ion"
            )
        return None

    def _context_remove_from_shared_group_tooltip(
        self, components: Iterable[AbsorberComponent]
    ) -> str | None:
        """Return the disabled-state tooltip for remove-from-shared-group, or None when enabled."""
        if self._tie_set_edit.can_remove_from_shared_group(components):
            return None
        return QCoreApplication.translate("RegionDetailPanel", "No shared group in selection")

    def _context_remove_from_external_group_tooltip(
        self, components: Iterable[AbsorberComponent]
    ) -> str | None:
        """Return the tooltip for remove-from-external-group, or None when enabled."""
        if self._tie_set_edit.can_remove_from_external_group(components):
            return None
        return QCoreApplication.translate("RegionDetailPanel", "No external sharing in selection")
