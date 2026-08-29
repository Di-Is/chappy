"""Tests for confirmed-region navigation in the identify side panel."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy

from chappy.gui.modes.identify.panel.confirmed_section import IdentifyConfirmedRegionsSection
from chappy.gui.modes.identify.panel.panel_models import ConfirmedLineRow, ConfirmedRegionRow

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def _confirmed_region() -> ConfirmedRegionRow:
    return ConfirmedRegionRow(
        group_id="region-1",
        label="Region 1",
        systems=[
            ConfirmedLineRow(
                system_id="line-1",
                species="C IV",
                redshift=1.292,
                lambda_start=3544.8,
                lambda_end=3546.3,
            )
        ],
        is_expanded=True,
    )


def test_summary_uses_neutral_region_context(qtbot: QtBot) -> None:
    """Collapsed context must not imply that row order represents recency."""
    section = IdentifyConfirmedRegionsSection()
    qtbot.addWidget(section)
    section.set_confirmed_regions([_confirmed_region()])

    summary = section.summary_text()
    assert summary == "1 region · Region 1 · C IV z=1.2920"
    assert "Latest" not in summary


def test_single_click_selects_without_focusing(qtbot: QtBot) -> None:
    """A single click changes selection without issuing navigation."""
    section = IdentifyConfirmedRegionsSection()
    qtbot.addWidget(section)
    section.resize(320, 300)
    section.set_confirmed_regions([_confirmed_region()])
    section.show()
    tree = section._groups_tree
    line_item = tree.topLevelItem(0).child(0)
    assert line_item is not None
    group_spy = QSignalSpy(section.group_focus_requested)
    system_spy = QSignalSpy(section.system_focus_requested)

    qtbot.mouseClick(
        tree.viewport(), Qt.MouseButton.LeftButton, pos=tree.visualItemRect(line_item).center()
    )

    assert line_item.isSelected()
    assert group_spy.count() == 0
    assert system_spy.count() == 0


def test_enter_focuses_current_group_once(qtbot: QtBot) -> None:
    """Enter activates the selected confirmed group through the focus signal."""
    section = IdentifyConfirmedRegionsSection()
    qtbot.addWidget(section)
    section.resize(320, 300)
    section.set_confirmed_regions([_confirmed_region()])
    section.show()
    tree = section._groups_tree
    group_item = tree.topLevelItem(0)
    assert group_item is not None
    tree.setCurrentItem(group_item)
    tree.setFocus()
    spy = QSignalSpy(section.group_focus_requested)

    qtbot.keyClick(tree, Qt.Key.Key_Return)

    assert spy.count() == 1
    assert spy.at(0) == ["region-1", 3544.8, 3546.3]


def test_double_click_focuses_system_once(qtbot: QtBot) -> None:
    """Double-click activates a confirmed line through the same focus path."""
    section = IdentifyConfirmedRegionsSection()
    qtbot.addWidget(section)
    section.resize(320, 300)
    section.set_confirmed_regions([_confirmed_region()])
    section.show()
    tree = section._groups_tree
    line_item = tree.topLevelItem(0).child(0)
    assert line_item is not None
    spy = QSignalSpy(section.system_focus_requested)

    qtbot.mouseDClick(
        tree.viewport(), Qt.MouseButton.LeftButton, pos=tree.visualItemRect(line_item).center()
    )

    assert spy.count() == 1
    assert spy.at(0) == ["line-1", 3544.8, 3546.3]
