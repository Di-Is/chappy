"""Tests for absorber editor layout composition boundaries."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QTableWidget
from pytestqt.qtbot import QtBot

from chappy.gui.shell.absorber_editor_layout import AbsorberEditorLayout


def test_setup_absorber_table_requires_table() -> None:
    """Missing absorber table is a shell composition error."""
    layout = AbsorberEditorLayout()

    with pytest.raises(TypeError, match="requires a QTableWidget"):
        layout.setup_absorber_table(None)  # type: ignore[arg-type]


def test_setup_absorber_table_configures_valid_table(qtbot: QtBot) -> None:
    """Valid absorber tables are configured by the layout builder."""
    table = QTableWidget()
    qtbot.addWidget(table)
    layout = AbsorberEditorLayout()

    layout.setup_absorber_table(table)

    assert table.columnCount() == 6
    assert table.horizontalHeaderItem(0).text() == "Name"
