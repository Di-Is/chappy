"""Tests for optimize tree view adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

from chappy.core.absorption.models import AbsorptionLine
from chappy.core.components.absorber import AbsorberComponent
from chappy.gui.modes.analysis.region_detail.tree.tree_view_adapter import OptimizeTreeViewAdapter

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

    from chappy.gui.modes.analysis.region_detail.tree.tree_row_renderer import (
        OptimizeTreeRowRenderer,
    )


class _Renderer:
    """Tree row renderer test double."""

    def __init__(self) -> None:
        self.refreshed: list[tuple[QTreeWidgetItem, AbsorberComponent]] = []
        self.populated: list[tuple[QTreeWidgetItem, tuple[AbsorptionLine, ...], int]] = []

    def refresh_model_row(self, item: QTreeWidgetItem, component: AbsorberComponent) -> None:
        """Record component row refreshes."""
        self.refreshed.append((item, component))

    def populate_multiplet_row(
        self,
        item: QTreeWidgetItem,
        group: tuple[AbsorptionLine, ...],
        display_index: int,
        component_index: dict[str, AbsorberComponent],
    ) -> None:
        """Populate a test parent row and child rows."""
        _ = component_index
        item.setData(0, Qt.ItemDataRole.UserRole, group[0])
        self.populated.append((item, group, display_index))


def _line(line_id: str = "line-1") -> AbsorptionLine:
    """Create a deterministic absorption line."""
    return AbsorptionLine(
        line_id=line_id,
        species="H I",
        rest_wavelength=1215.67,
        center_z=2.0,
        window_kms=150.0,
        region_id="region-1",
        multiplet_label="",
        transition_name="Ly alpha",
        oscillator_strength=0.1,
        gamma_value=1e8,
    )


def _component(component_id: str = "component-1") -> AbsorberComponent:
    """Create a deterministic absorber component."""
    return AbsorberComponent(component_id=component_id, redshift=2.0)


def _adapter(
    tree: QTreeWidget, renderer: _Renderer, suppressed: list[bool], selected: list[None]
) -> OptimizeTreeViewAdapter:
    """Create an adapter with recording callbacks."""
    return OptimizeTreeViewAdapter(
        tree=tree,
        row_renderer=cast("OptimizeTreeRowRenderer", renderer),
        set_item_changed_suppressed=suppressed.append,
        on_selection_changed=lambda: selected.append(None),
    )


def test_iter_component_rows_yields_child_components(qtbot: "QtBot") -> None:
    """Adapter should traverse component child rows."""
    tree = QTreeWidget()
    qtbot.addWidget(tree)
    component = _component()
    parent = QTreeWidgetItem(tree)
    child = QTreeWidgetItem(parent)
    child.setData(0, Qt.ItemDataRole.UserRole, component)
    adapter = _adapter(tree, _Renderer(), [], [])

    assert list(adapter.iter_component_rows()) == [(child, component)]


def test_refresh_component_row_suppresses_item_changed(qtbot: "QtBot") -> None:
    """Row refreshes should run inside the item-changed suppression guard."""
    tree = QTreeWidget()
    qtbot.addWidget(tree)
    item = QTreeWidgetItem(tree)
    component = _component()
    renderer = _Renderer()
    suppressed: list[bool] = []
    adapter = _adapter(tree, renderer, suppressed, [])

    adapter.refresh_component_row(item, component)

    assert renderer.refreshed == [(item, component)]
    assert suppressed == [True, False]


def test_update_parameter_values_refreshes_every_matching_id(qtbot: "QtBot") -> None:
    """Adapter should re-render every row matching an affected component ID."""
    tree = QTreeWidget()
    tree.setColumnCount(7)
    qtbot.addWidget(tree)
    component = _component("component-1")
    same_id_component = _component("component-1")
    unaffected_component = _component("component-2")
    parent = QTreeWidgetItem(tree)
    first_item = QTreeWidgetItem(parent)
    first_item.setData(0, Qt.ItemDataRole.UserRole, component)
    second_item = QTreeWidgetItem(parent)
    second_item.setData(0, Qt.ItemDataRole.UserRole, same_id_component)
    unaffected_item = QTreeWidgetItem(parent)
    unaffected_item.setData(0, Qt.ItemDataRole.UserRole, unaffected_component)
    renderer = _Renderer()
    suppressed: list[bool] = []
    adapter = _adapter(tree, renderer, suppressed, [])

    adapter.update_parameter_values((component.id,))

    assert renderer.refreshed == [(first_item, component), (second_item, same_id_component)]
    assert suppressed == [True, False]


def test_select_line_by_id_selects_line_and_notifies(qtbot: "QtBot") -> None:
    """Adapter should select a line row by id and notify selection workflow."""
    tree = QTreeWidget()
    qtbot.addWidget(tree)
    line = _line()
    item = QTreeWidgetItem(tree)
    item.setData(0, Qt.ItemDataRole.UserRole, line)
    selected: list[None] = []
    adapter = _adapter(tree, _Renderer(), [], selected)

    assert adapter.select_line_by_id(line.line_id) is True

    assert item.isSelected()
    assert selected == [None]
