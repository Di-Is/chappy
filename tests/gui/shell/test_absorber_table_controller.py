"""Absorber table controller boundary tests."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from chappy.core.components.absorber import AbsorberComponent
from chappy.gui.shell.absorber_table_controller import TABLE_COL_REDSHIFT, AbsorberTableController


def _absorber(name: str = "component-1") -> AbsorberComponent:
    """Create an absorber component for table tests."""
    return AbsorberComponent(
        name=name, wavelength=1548.2, redshift=2.0, column_density=14.0, b_parameter=20.0
    )


def test_table_mutation_requires_configured_table() -> None:
    """Table mutation APIs require setup_table() or create_table_widget()."""
    controller = AbsorberTableController()

    with pytest.raises(RuntimeError, match="add_absorber"):
        controller.add_absorber(_absorber())


def test_selected_absorber_without_table_is_valid_empty() -> None:
    """Selection query before table setup remains a valid empty state."""
    controller = AbsorberTableController()

    assert controller.get_selected_absorber() is None


def test_invalid_user_edit_reverts_to_previous_value(qtbot) -> None:
    """Invalid inline edits remain recoverable user input."""
    controller = AbsorberTableController()
    table = controller.create_table_widget()
    qtbot.addWidget(table)
    absorber = _absorber()

    controller.add_absorber(absorber)
    item = table.item(0, TABLE_COL_REDSHIFT)
    assert item is not None
    item.setText("not-a-number")

    assert item.text() == "2.000000"
    assert item.data(Qt.ItemDataRole.UserRole) == 2.0
