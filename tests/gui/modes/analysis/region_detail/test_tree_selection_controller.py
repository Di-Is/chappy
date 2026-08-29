"""Tests for optimize tree selection controller."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem
from pytestqt.qtbot import QtBot

from chappy.core.absorption.models import AbsorptionLine
from chappy.core.components.absorber import AbsorberComponent
from chappy.gui.modes.analysis.region_detail.tree.tree_selection_controller import (
    OptimizeTreeSelectionController,
)


class _Port:
    """Panel-port test double."""

    def __init__(self) -> None:
        self.cleared = 0
        self.selected_lines: list[AbsorptionLine] = []
        self.selected_component_ids: list[str | None] = []

    def clear_selected_line(self) -> None:
        """Record selected-line clearing."""
        self.cleared += 1

    def select_line_from_tree(self, line: AbsorptionLine, component_id: str | None) -> None:
        """Record selected lines and the component row they came from."""
        self.selected_lines.append(line)
        self.selected_component_ids.append(component_id)


def _line() -> AbsorptionLine:
    """Return a minimal absorption line for selection tests."""
    return AbsorptionLine(
        line_id="line-1",
        species="H I",
        rest_wavelength=1215.67,
        center_z=2.0,
        window_kms=150.0,
        lambda_range=(3500.0, 4000.0),
        multiplet_label="",
        transition_name="H I 1215.7",
        oscillator_strength=0.1,
        gamma_value=1e8,
    )


def test_empty_selection_clears_selected_line(qtbot: QtBot) -> None:
    """Controller should clear state when the tree has no selection."""
    tree = QTreeWidget()
    qtbot.addWidget(tree)
    port = _Port()
    controller = OptimizeTreeSelectionController(tree=tree, port=port)

    controller.selection_changed()

    assert port.cleared == 1
    assert port.selected_lines == []


def test_line_row_selection_selects_line(qtbot: QtBot) -> None:
    """Controller should select the line stored on a selected top-level row."""
    tree = QTreeWidget()
    qtbot.addWidget(tree)
    line = _line()
    item = QTreeWidgetItem(tree)
    item.setData(0, Qt.ItemDataRole.UserRole, line)
    item.setSelected(True)
    tree.setCurrentItem(item)
    port = _Port()
    controller = OptimizeTreeSelectionController(tree=tree, port=port)

    controller.selection_changed()

    assert port.cleared == 0
    assert port.selected_lines == [line]
    assert port.selected_component_ids == [None]


def test_component_row_selection_selects_parent_line(qtbot: QtBot) -> None:
    """Controller should select the parent line when a component row is selected."""
    tree = QTreeWidget()
    qtbot.addWidget(tree)
    line = _line()
    parent = QTreeWidgetItem(tree)
    parent.setData(0, Qt.ItemDataRole.UserRole, line)
    child = QTreeWidgetItem(parent)
    child.setData(0, Qt.ItemDataRole.UserRole, AbsorberComponent(component_id="comp-1"))
    child.setSelected(True)
    tree.setCurrentItem(child)
    port = _Port()
    controller = OptimizeTreeSelectionController(tree=tree, port=port)

    controller.selection_changed()

    assert port.cleared == 0
    assert port.selected_lines == [line]
    assert port.selected_component_ids == ["comp-1"]
