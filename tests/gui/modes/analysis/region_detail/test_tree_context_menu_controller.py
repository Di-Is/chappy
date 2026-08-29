"""Tests for optimize tree context-menu controller."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtWidgets import QApplication, QTreeWidget, QTreeWidgetItem, QWidget

from chappy.core.components.absorber import AbsorberComponent
from chappy.gui.modes.analysis.region_detail.tree.tree_columns import ColumnMeta
from chappy.gui.modes.analysis.region_detail.tree.tree_context_menu_controller import (
    OptimizeTreeContextMenuController,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from chappy.gui.modes.analysis.region_detail.tie_set_edit_controller import (
        OptimizeTieSetEditController,
    )


@pytest.fixture(name="qapp")
def fixture_qapp() -> QApplication:
    """Provide a QApplication instance for Qt widgets."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _Port:
    """Tree context-menu port test double."""

    def __init__(self) -> None:
        self.explicit_targets: list[AbsorberComponent] = []
        self.source_targets: list[AbsorberComponent] = []
        self.confirmed_components: list[AbsorberComponent] = []
        self.deleted_components: list[AbsorberComponent] = []
        self.refresh_count = 0
        self.delete_changed = True
        self.fail_refresh = False

    def ensure_context_covering_factor_parameter(self, component: AbsorberComponent) -> None:
        """No-op covering factor initialization."""
        _ = component

    def context_column_label(self, meta: ColumnMeta) -> str:
        """Return source text for tests."""
        return meta.source_text

    def context_fix_action_label(
        self, parameter_label: str, components: list[AbsorberComponent], param_name: str
    ) -> str:
        """Return deterministic fix label."""
        _ = components
        _ = param_name
        return f"Fix {parameter_label}"

    def are_context_components_fixed(
        self, components: Iterable[AbsorberComponent], param_name: str
    ) -> bool:
        """Return False for deterministic menu state."""
        _ = tuple(components)
        _ = param_name
        return False

    def handle_context_fix_action(
        self, components: list[AbsorberComponent], param_name: str, fixed: bool
    ) -> None:
        """No-op fix action."""
        _ = components
        _ = param_name
        _ = fixed

    def context_adjust_parameters_label(self) -> str:
        """Return deterministic adjust label."""
        return "Adjust parameters..."

    def show_context_parameter_dialog(self, component: AbsorberComponent) -> None:
        """No-op dialog action."""
        _ = component

    def context_delete_component_label(self) -> str:
        """Return deterministic delete label."""
        return "Delete Component"

    def collect_context_delete_targets(
        self, components: Iterable[AbsorberComponent]
    ) -> list[AbsorberComponent]:
        """Return configured explicit targets."""
        _ = tuple(components)
        return self.explicit_targets

    def collect_context_source_delete_targets(
        self, component: AbsorberComponent
    ) -> list[AbsorberComponent]:
        """Return configured source targets."""
        _ = component
        return self.source_targets

    def confirm_context_component_deletion(self, components: list[AbsorberComponent]) -> bool:
        """Record confirmation target and confirm."""
        self.confirmed_components = components
        return True

    def delete_context_components(self, components: list[AbsorberComponent]) -> bool:
        """Record deletion target."""
        self.deleted_components = components
        return self.delete_changed

    def refresh_context_group_after_delete(self) -> None:
        """Record group refresh."""
        if self.fail_refresh:
            raise RuntimeError("injected delete refresh failure")
        self.refresh_count += 1


def _component(component_id: str) -> AbsorberComponent:
    """Create a deterministic absorber component."""
    return AbsorberComponent(component_id=component_id, redshift=2.0)


def _tree_with_components(
    first: AbsorberComponent, second: AbsorberComponent
) -> tuple[QTreeWidget, QTreeWidgetItem, QTreeWidgetItem, QTreeWidgetItem]:
    """Create a tree with component rows, including a duplicate row for the first component."""
    tree = QTreeWidget()
    tree.setColumnCount(1)
    first_item = QTreeWidgetItem(tree)
    first_item.setData(0, Qt.ItemDataRole.UserRole, first)
    duplicate_item = QTreeWidgetItem(tree)
    duplicate_item.setData(0, Qt.ItemDataRole.UserRole, first)
    second_item = QTreeWidgetItem(tree)
    second_item.setData(0, Qt.ItemDataRole.UserRole, second)
    return tree, first_item, duplicate_item, second_item


class _TieSetEdit:
    """Tie set edit controller test double, unused by delete/selection tests."""

    def can_remove_from_shared_group(self, components: Iterable[AbsorberComponent]) -> bool:
        """Return False for deterministic menu state."""
        _ = tuple(components)
        return False

    def can_remove_from_external_group(self, components: Iterable[AbsorberComponent]) -> bool:
        """Return False for deterministic menu state."""
        _ = tuple(components)
        return False


def _controller(tree: QTreeWidget, port: _Port) -> OptimizeTreeContextMenuController:
    """Create a tree context-menu controller."""
    return OptimizeTreeContextMenuController(
        tree=tree,
        parent=QWidget(),
        port=port,
        tie_set_edit=cast("OptimizeTieSetEditController", _TieSetEdit()),
        tie_label_for_uid=lambda _uid: None,
    )


def test_selected_components_deduplicates_by_component_id(qapp: QApplication) -> None:
    """Selected components should be returned once per component id."""
    assert qapp is not None
    first = _component("component-1")
    second = _component("component-2")
    tree, first_item, duplicate_item, second_item = _tree_with_components(first, second)
    selection_model = tree.selectionModel()
    assert selection_model is not None
    for item, flag in (
        (first_item, QItemSelectionModel.SelectionFlag.ClearAndSelect),
        (duplicate_item, QItemSelectionModel.SelectionFlag.Select),
        (second_item, QItemSelectionModel.SelectionFlag.Select),
    ):
        selection_model.select(
            tree.indexFromItem(item, 0), flag | QItemSelectionModel.SelectionFlag.Rows
        )
    controller = _controller(tree, _Port())

    selected = controller.selected_components()

    assert [component.id for component in selected] == ["component-1", "component-2"]


def test_select_item_for_context_menu_replaces_selection_when_item_is_unselected(
    qapp: QApplication,
) -> None:
    """Right-clicking an unselected row should select only that row."""
    assert qapp is not None
    first = _component("component-1")
    second = _component("component-2")
    tree, first_item, _duplicate_item, second_item = _tree_with_components(first, second)
    selection_model = tree.selectionModel()
    assert selection_model is not None
    selection_model.select(
        tree.indexFromItem(first_item, 0),
        QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows,
    )
    controller = _controller(tree, _Port())

    controller.select_item_for_context_menu(second_item)

    assert [component.id for component in controller.selected_components()] == ["component-2"]


def test_delete_models_uses_multi_selection_targets(qapp: QApplication) -> None:
    """Multi-selection deletion should use expanded explicit selection targets."""
    assert qapp is not None
    first = _component("component-1")
    second = _component("component-2")
    tree, first_item, _duplicate_item, second_item = _tree_with_components(first, second)
    selection_model = tree.selectionModel()
    assert selection_model is not None
    for item, flag in (
        (first_item, QItemSelectionModel.SelectionFlag.ClearAndSelect),
        (second_item, QItemSelectionModel.SelectionFlag.Select),
    ):
        selection_model.select(
            tree.indexFromItem(item, 0), flag | QItemSelectionModel.SelectionFlag.Rows
        )
    port = _Port()
    port.explicit_targets = [first, second]
    controller = _controller(tree, port)

    controller.delete_models(first)

    assert port.confirmed_components == [first, second]
    assert port.deleted_components == [first, second]
    assert port.refresh_count == 1


def test_delete_models_uses_source_targets_for_single_selection(qapp: QApplication) -> None:
    """Single-selection deletion should expand from the context-clicked component."""
    assert qapp is not None
    first = _component("component-1")
    second = _component("component-2")
    tree, first_item, _duplicate_item, _second_item = _tree_with_components(first, second)
    selection_model = tree.selectionModel()
    assert selection_model is not None
    selection_model.select(
        tree.indexFromItem(first_item, 0),
        QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows,
    )
    port = _Port()
    port.source_targets = [first, second]
    controller = _controller(tree, port)

    controller.delete_models(first)

    assert port.confirmed_components == [first, second]
    assert port.deleted_components == [first, second]
    assert port.refresh_count == 1


def test_delete_models_no_change_skips_group_refresh(qapp: QApplication) -> None:
    """A deletion rejected by the transaction must not refresh the group UI."""
    assert qapp is not None
    first = _component("component-1")
    second = _component("component-2")
    tree, first_item, _duplicate_item, _second_item = _tree_with_components(first, second)
    selection_model = tree.selectionModel()
    assert selection_model is not None
    selection_model.select(
        tree.indexFromItem(first_item, 0),
        QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows,
    )
    port = _Port()
    port.source_targets = [first]
    port.delete_changed = False

    _controller(tree, port).delete_models(first)

    assert port.deleted_components == [first]
    assert port.refresh_count == 0


def test_delete_models_refresh_failure_does_not_escape_after_commit(qapp: QApplication) -> None:
    """A failed group refresh must not make a committed deletion look rejected."""
    assert qapp is not None
    first = _component("component-1")
    second = _component("component-2")
    tree, first_item, _duplicate_item, _second_item = _tree_with_components(first, second)
    selection_model = tree.selectionModel()
    assert selection_model is not None
    selection_model.select(
        tree.indexFromItem(first_item, 0),
        QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows,
    )
    port = _Port()
    port.source_targets = [first]
    port.fail_refresh = True

    _controller(tree, port).delete_models(first)

    assert port.deleted_components == [first]
    assert port.refresh_count == 0
