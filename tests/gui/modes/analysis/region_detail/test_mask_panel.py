"""Regression tests for OptimizeMaskPanel interactions."""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QFrame, QTreeWidgetItem

from chappy.core.masking import MaskDefinition
from chappy.gui.modes.analysis.region_detail.mask.mask_panel import OptimizeMaskPanel
from scripts.i18n_lupdate import run_lupdate


if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


OPTIMIZE_MASK_PANEL_QT_SOURCES = {
    "Masked Ranges",
    "Add Masked Range",
    "Name",
    "Start (Å)",
    "End (Å)",
    "Width (Å)",
    "Actions",
    "Delete this masked range",
    "Delete Masked Range",
}


def _panel_with_masks(qtbot: "QtBot") -> OptimizeMaskPanel:
    """Create an optimize mask panel populated with deterministic masks.

    Args:
        qtbot: Qt test helper managing widget lifetime.

    Returns:
        Populated optimize mask panel.
    """
    panel = OptimizeMaskPanel()
    qtbot.addWidget(panel)
    panel.set_masks(
        [
            MaskDefinition.from_range(5000.0, 5001.0, identifier="mask-a").rename("Mask A"),
            MaskDefinition.from_range(5002.0, 5003.0, identifier="mask-b").rename("Mask B"),
        ]
    )
    return panel


def _find_mask_item(panel: OptimizeMaskPanel, mask_id: str) -> QTreeWidgetItem:
    """Find the tree item representing a mask.

    Args:
        panel: Panel containing mask rows.
        mask_id: Identifier stored on the row.

    Returns:
        Tree item for the requested mask.

    Raises:
        AssertionError: If no matching row exists.
    """
    tree = panel._tree  # test hook: internal view used to expose the editable cells
    for index in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(index)
        if item is None:
            continue
        identifier = item.data(0, Qt.ItemDataRole.UserRole)
        if identifier == mask_id:
            return item
    pytest.fail(f"Mask row was not found: {mask_id}")


def test_editing_mask_start_cell_emits_range_change_and_updates_ui(qtbot: "QtBot") -> None:
    """Verify start-cell edits emit a public signal and refresh visible row values.

    Args:
        qtbot: Qt test helper managing signal waiting.
    """
    panel = _panel_with_masks(qtbot)
    item = _find_mask_item(panel, "mask-b")

    with qtbot.waitSignal(panel.mask_range_changed, timeout=1000) as changed:
        item.setText(1, "5002.50")

    assert changed.args == ["mask-b", 5002.5, 5003.0]
    assert item.text(1) == "5002.50"
    assert item.text(2) == "5003.00"
    assert item.text(3) == "0.50"


def test_editing_mask_end_cell_normalizes_reversed_range(qtbot: "QtBot") -> None:
    """Verify end-cell edits normalize reversed input into an observable range.

    Args:
        qtbot: Qt test helper managing signal waiting.
    """
    panel = _panel_with_masks(qtbot)
    item = _find_mask_item(panel, "mask-b")

    with qtbot.waitSignal(panel.mask_range_changed, timeout=1000) as changed:
        item.setText(2, "5001.50")

    assert changed.args == ["mask-b", 5001.5, 5002.0]
    assert item.text(1) == "5001.50"
    assert item.text(2) == "5002.00"
    assert item.text(3) == "0.50"


def test_invalid_mask_range_edit_restores_ui_without_signal(qtbot: "QtBot") -> None:
    """Verify invalid range text is rejected through visible state.

    Args:
        qtbot: Qt test helper managing widget lifetime.
    """
    panel = _panel_with_masks(qtbot)
    item = _find_mask_item(panel, "mask-b")
    spy = QSignalSpy(panel.mask_range_changed)

    item.setText(1, "not-a-number")

    assert spy.count() == 0
    assert item.text(1) == "5002.00"
    assert item.text(2) == "5003.00"
    assert item.text(3) == "1.00"


def test_mask_panel_common_gui_text_uses_qt_sources(qtbot: "QtBot") -> None:
    """Verify migrated common GUI text is plain Qt source text.

    Args:
        qtbot: Qt test helper managing widget lifetime.
    """
    panel = _panel_with_masks(qtbot)
    tree = panel._tree  # test hook: internal view used to expose translated labels
    header = tree.headerItem()
    first_item = tree.topLevelItem(0)
    assert first_item is not None
    delete_button = tree.itemWidget(first_item, 4)

    assert panel._header_button.title_label.text() == "Masked Ranges"
    assert panel._header_button.accessibleName() == "Masked Ranges"
    assert panel._add_button.text() == "Add Masked Range"
    assert [header.text(column) for column in range(tree.columnCount())] == [
        "Name",
        "Start (Å)",
        "End (Å)",
        "Width (Å)",
        "Actions",
    ]
    assert delete_button is not None
    assert delete_button.toolTip() == "Delete this masked range"
    assert delete_button.accessibleName() == "Delete Masked Range"


def test_mask_disclosure_header_is_full_width_and_activates_from_title(qtbot: "QtBot") -> None:
    """The mask title and trailing chevron form one full-width target."""
    panel = OptimizeMaskPanel()
    qtbot.addWidget(panel)
    panel.resize(320, 500)
    panel.show()
    QApplication.processEvents()
    header = panel._header_button
    title_center = header.title_label.mapTo(header, header.title_label.rect().center())

    assert header.width() == panel.layout().contentsRect().width()
    assert header.title_label.geometry().left() == 0
    assert header._arrow_label.geometry().right() == header.width() - 1
    assert panel._content_widget.isHidden()

    qtbot.mouseClick(header, Qt.MouseButton.LeftButton, pos=title_center)
    assert not panel._content_widget.isHidden()

    qtbot.keyClick(header, Qt.Key.Key_Return)
    assert panel._content_widget.isHidden()

    qtbot.keyClick(header, Qt.Key.Key_Space)
    assert not panel._content_widget.isHidden()


def test_mask_section_has_no_outer_frame(qtbot: "QtBot") -> None:
    """The disclosure header and tree must not be wrapped in a redundant frame."""
    panel = _panel_with_masks(qtbot)

    assert panel.frameShape() is QFrame.Shape.NoFrame


def test_mask_disclosure_preserves_auto_expand_and_user_override(qtbot: "QtBot") -> None:
    """Shared header interaction does not change mask-specific state rules."""
    panel = OptimizeMaskPanel()
    qtbot.addWidget(panel)
    panel.show()
    mask = MaskDefinition.from_range(5000.0, 5001.0, identifier="mask-a")

    assert panel._content_widget.isHidden()

    panel.set_masks([mask])
    assert not panel._content_widget.isHidden()

    qtbot.mouseClick(panel._header_button, Qt.MouseButton.LeftButton)
    assert panel._content_widget.isHidden()
    assert panel._user_override

    panel.set_masks([mask])
    assert panel._content_widget.isHidden()

    panel.expand()
    assert not panel._content_widget.isHidden()

    panel.set_masks([])
    assert panel._content_widget.isHidden()


def test_lupdate_extracts_mask_panel_common_gui_sources(tmp_path: Path) -> None:
    """Verify lupdate extracts migrated optimize mask panel source text.

    Args:
        tmp_path: Temporary directory for the generated TS file.
    """
    if shutil.which("pyside6-lupdate") is None:
        pytest.skip("pyside6-lupdate is not available")

    ts_path = tmp_path / "chappy_ja.ts"
    run_lupdate(
        source_dirs=[Path("src/chappy/gui/modes/analysis/region_detail/mask/mask_panel.py")],
        ts_output=ts_path,
    )

    root = ET.parse(ts_path).getroot()
    sources = {
        source.text
        for source in root.findall("./context/message/source")
        if source.text is not None
    }
    assert OPTIMIZE_MASK_PANEL_QT_SOURCES <= sources
    assert not any("GUI__" in source for source in sources)
