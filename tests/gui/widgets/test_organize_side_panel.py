"""OrganizeSidePanel empty-state behavior tests."""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QLabel, QPushButton, QTableView, QTreeWidget, QTreeWidgetItem

from chappy.gui.modes.analysis.overview.panel import OrganizeSidePanel
from chappy.gui.modes.analysis.overview.review_widget import AnalysisOverviewReviewWidget
from chappy.presentation.organize.tree_presenter import OrganizeGroupEntry
from scripts.i18n_lupdate import run_lupdate


if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


ORGANIZE_SIDE_PANEL_QT_SOURCES = {
    "Edit regions",
    "Back to Overview",
    "Return to Analysis Overview (Alt+Left)",
    "Load absorber data to manage regions and lines here.",
    "Observed range: {minimum:.2f} – {maximum:.2f} Å",
    "Unknown",
    "{species} {wavelengths} [z={redshift}, ±{window} km/s]",
    "(λ: {range_text} Å)",
    "(1 line)",
    "({count} lines)",
    "Drop here to create a new region",
    "Drag lines here to create a new region.",
}


def test_review_stays_visible_and_structure_editor_starts_closed(qtbot: "QtBot") -> None:
    """Overview remains primary while the existing structure editor is session-local."""
    panel = OrganizeSidePanel()
    qtbot.addWidget(panel)

    panel.show()
    qtbot.waitUntil(panel.isVisible)

    panel.refresh()

    tree = panel.findChild(QTreeWidget, "analysisStructureTree")
    review = panel.findChild(QTableView, "analysisOverviewReviewTable")
    placeholder = panel.findChild(QLabel, "organizeSidePanelEmptyState")

    assert review is not None and review.isVisible()
    assert tree is not None and not tree.isVisible()
    assert placeholder is not None and not placeholder.isVisible()

    assert tree.topLevelItemCount() >= 1
    placeholder_item = tree.topLevelItem(tree.topLevelItemCount() - 1)
    assert placeholder_item is not None
    payload = placeholder_item.data(0, Qt.ItemDataRole.UserRole)
    assert isinstance(payload, dict)
    assert payload.get("type") == "new_group"


def test_panel_re_emits_review_region_delete_request(qtbot: "QtBot") -> None:
    """The panel forwards the review delete intent unchanged to the shell."""
    panel = OrganizeSidePanel()
    qtbot.addWidget(panel)
    review = panel.findChild(AnalysisOverviewReviewWidget)
    assert review is not None

    spy = QSignalSpy(panel.region_delete_requested)
    review.region_delete_requested.emit("region-1")

    assert spy.count() == 1
    assert spy.at(0)[0] == "region-1"


def test_back_button_emits_back_requested(qtbot: "QtBot") -> None:
    """The region editor page exposes an explicit way back to the Overview."""
    panel = OrganizeSidePanel()
    qtbot.addWidget(panel)
    back_button = panel.findChild(QPushButton, "organizeSidePanelBackButton")
    assert back_button is not None

    spy = QSignalSpy(panel.back_requested)
    back_button.click()

    assert spy.count() == 1


def test_group_item_carries_full_text_tooltip_with_warning_explanation(qtbot: "QtBot") -> None:
    """Narrow widths keep label, range, count, and the ⚠ meaning reachable."""
    panel = OrganizeSidePanel()
    qtbot.addWidget(panel)
    entry = OrganizeGroupEntry(
        identifier="region-1",
        label="Region 1",
        wavelength_min=4000.0,
        wavelength_max=4100.0,
        components=[],
        system_count=2,
        needs_optimization=True,
        shows_badges=True,
    )
    item = QTreeWidgetItem()

    panel._render_group_item_text(item, entry)

    tooltip = item.toolTip(0)
    assert "Region 1" in tooltip
    assert "4000-4100" in tooltip
    assert "2 lines" in tooltip
    assert "re-optimization" in tooltip
    assert "⚠️" in item.text(0)


def test_structure_action_buttons_use_short_labels_with_full_tooltips(qtbot: "QtBot") -> None:
    """Merge/Split/Delete/Unlink stay short at width 220 and explain via tooltips."""
    panel = OrganizeSidePanel()
    qtbot.addWidget(panel)

    buttons = {
        "analysisOverviewMergeButton": "Merge",
        "analysisOverviewSplitButton": "Split",
        "analysisOverviewDeleteButton": "Delete",
        "organizeUnlinkSystemButton": "Unlink system",
    }
    for object_name, label in buttons.items():
        button = panel.findChild(QPushButton, object_name)
        assert button is not None, object_name
        assert button.text() == label
        assert button.toolTip(), object_name


def test_organize_side_panel_migrated_gui_text_uses_qt_sources(qtbot: "QtBot") -> None:
    """Verify migrated organize GUI text is plain Qt source text."""
    panel = OrganizeSidePanel()
    qtbot.addWidget(panel)

    panel.refresh()

    header = panel.findChild(QLabel, "organizeSidePanelHeader")
    placeholder = panel.findChild(QLabel, "organizeSidePanelEmptyState")
    tree = panel.findChild(QTreeWidget, "analysisStructureTree")

    assert header is not None
    assert header.text() == "Edit regions"
    assert placeholder is not None
    assert placeholder.text() == "Load absorber data to manage regions and lines here."
    assert tree is not None

    placeholder_item = tree.topLevelItem(tree.topLevelItemCount() - 1)
    assert placeholder_item is not None
    assert placeholder_item.text(0) == "Drop here to create a new region"
    assert placeholder_item.toolTip(0) == "Drag lines here to create a new region."


def test_lupdate_extracts_organize_side_panel_sources(tmp_path: Path) -> None:
    """Verify lupdate extracts migrated OrganizeSidePanel sources without old keys."""
    if shutil.which("pyside6-lupdate") is None:
        pytest.skip("pyside6-lupdate is not available")

    ts_path = tmp_path / "chappy_ja.ts"
    run_lupdate(
        source_dirs=[Path("src/chappy/gui/modes/analysis/overview/panel.py")], ts_output=ts_path
    )

    root = ET.parse(ts_path).getroot()
    sources = {
        source.text
        for source in root.findall("./context/message/source")
        if source.text is not None
    }
    assert ORGANIZE_SIDE_PANEL_QT_SOURCES <= sources
    assert not any("GUI__" in source for source in sources)
