"""Tests for the shared side-panel disclosure header."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy

from chappy.gui.common.disclosure_header import DisclosureHeaderButton

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def test_disclosure_header_is_one_accessible_mouse_and_keyboard_target(qtbot: QtBot) -> None:
    """Title, summary, and chevron activate the same checkable button."""
    header = DisclosureHeaderButton(object_name="testDisclosureHeader")
    qtbot.addWidget(header)
    header.set_title("Preset Lines")
    header.set_summary("Reference: C IV multiplet with a deliberately long description")
    header.resize(240, header.sizeHint().height())
    header.show()
    spy = QSignalSpy(header.toggled)

    assert header.accessibleName() == "Preset Lines"
    assert header.toolTip() == header.summary_label.full_text
    assert header._title_label.geometry().right() < header._arrow_label.geometry().left()

    for child in (header._title_label, header.summary_label, header._arrow_label):
        child_center = child.mapTo(header, child.rect().center())
        qtbot.mouseClick(header, Qt.MouseButton.LeftButton, pos=child_center)

    assert not header.isChecked()

    qtbot.keyClick(header, Qt.Key.Key_Return)
    assert header.isChecked()

    qtbot.keyClick(header, Qt.Key.Key_Space)
    assert not header.isChecked()
    assert spy.count() == 5


def test_disclosure_header_keeps_title_and_trailing_chevron_at_narrow_width(qtbot: QtBot) -> None:
    """Only the optional summary yields width when the header becomes narrow."""
    header = DisclosureHeaderButton(object_name="narrowDisclosureHeader")
    qtbot.addWidget(header)
    header.set_title("Confirmed Regions")
    header.set_summary("3 regions · a long representative region name")
    header.resize(200, header.sizeHint().height())
    header.show()

    assert header._title_label.text() == "Confirmed Regions"
    assert header._title_label.geometry().left() == 0
    assert header._arrow_label.geometry().right() == header.width() - 1
    assert header.summary_label.full_text == "3 regions · a long representative region name"
