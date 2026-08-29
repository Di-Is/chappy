"""Input UX tests for line-selection filters."""

from __future__ import annotations

from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from chappy.core.atomic_data import AtomicLine, AtomicLineData
from chappy.gui.dialogs.line_selection_dialog import LineSelectionDialog


def _line(identifier: str, element: str, wavelength: float) -> AtomicLine:
    return AtomicLine(
        line_identifier=identifier,
        species=f"{element} II",
        wavelength_angstrom=wavelength,
        oscillator_strength=0.1,
        gamma_value=1.0,
        element_symbol=element,
        charge_state=1,
        transition_name=identifier,
    )


def _dialog(qtbot: QtBot) -> LineSelectionDialog:
    dialog = LineSelectionDialog(
        atomic_data=AtomicLineData(
            [
                _line("h-1000", "H", 1000.0),
                _line("fe-2500", "Fe", 2500.0),
                _line("fe-4500", "Fe", 4500.0),
                _line("si-5000", "Si", 5000.0),
            ]
        )
    )
    qtbot.addWidget(dialog)
    dialog.show()
    return dialog


def test_typing_unique_element_prefix_selects_matching_element(qtbot: QtBot) -> None:
    dialog = _dialog(qtbot)
    element_edit = dialog._element_combo.lineEdit()
    assert element_edit is not None

    element_edit.setFocus()
    qtbot.keyClicks(element_edit, "f")

    qtbot.waitUntil(lambda: dialog._element_combo.currentData() == "FE", timeout=1000)
    assert dialog._element_combo.currentText() == "Fe"
    assert dialog._table.rowCount() == 2


def test_invalid_element_draft_is_retained_with_inline_error(qtbot: QtBot) -> None:
    dialog = _dialog(qtbot)
    element_edit = dialog._element_combo.lineEdit()
    assert element_edit is not None
    initial_rows = dialog._table.rowCount()

    element_edit.setFocus()
    qtbot.keyClicks(element_edit, "Zz")

    qtbot.waitUntil(dialog._filter_warning.isVisible, timeout=1000)
    assert element_edit.text() == "Zz"
    assert dialog._element_combo.property("error") is True
    assert dialog._table.rowCount() == initial_rows


def test_wavelength_can_be_typed_without_selecting_placeholder(qtbot: QtBot) -> None:
    dialog = _dialog(qtbot)

    dialog._wavelength_min.setFocus()
    qtbot.keyClicks(dialog._wavelength_min, "4000")

    qtbot.waitUntil(lambda: dialog._table.rowCount() == 2, timeout=1000)
    assert dialog._wavelength_min.text() == "4000"
    assert dialog._last_applied_filters is not None
    assert dialog._last_applied_filters.wavelength_min == 4000.0


def test_invalid_wavelength_is_retained_and_keeps_last_results(qtbot: QtBot) -> None:
    dialog = _dialog(qtbot)
    dialog._wavelength_min.setFocus()
    qtbot.keyClicks(dialog._wavelength_min, "4000")
    qtbot.waitUntil(lambda: dialog._table.rowCount() == 2, timeout=1000)

    dialog._wavelength_min.selectAll()
    qtbot.keyClicks(dialog._wavelength_min, "invalid")

    qtbot.waitUntil(dialog._filter_warning.isVisible, timeout=1000)
    assert dialog._wavelength_min.text() == "invalid"
    assert dialog._wavelength_min.property("error") is True
    assert dialog._table.rowCount() == 2


def test_inverted_range_recovers_after_user_correction(qtbot: QtBot) -> None:
    dialog = _dialog(qtbot)
    dialog._wavelength_min.setText("4500")
    dialog._wavelength_max.setText("2000")
    dialog._apply_filters()

    assert dialog._filter_warning.isVisible()
    assert dialog._wavelength_min.property("error") is True
    assert dialog._wavelength_max.property("error") is True

    dialog._wavelength_max.selectAll()
    qtbot.keyClicks(dialog._wavelength_max, "5000")
    qtbot.waitUntil(lambda: not dialog._filter_warning.isVisible(), timeout=1000)

    assert dialog._table.rowCount() == 2
    assert dialog._wavelength_min.property("error") is False
    assert dialog._wavelength_max.property("error") is False


def test_escape_restores_last_applied_wavelength(qtbot: QtBot) -> None:
    dialog = _dialog(qtbot)
    dialog._wavelength_min.setFocus()
    qtbot.keyClicks(dialog._wavelength_min, "4000")
    qtbot.waitUntil(lambda: dialog._table.rowCount() == 2, timeout=1000)

    dialog._wavelength_min.selectAll()
    qtbot.keyClicks(dialog._wavelength_min, "invalid")
    qtbot.keyClick(dialog._wavelength_min, Qt.Key.Key_Escape)

    assert dialog._wavelength_min.text() == "4000"
    assert not dialog._filter_warning.isVisible()


def test_clear_filters_restores_unbounded_empty_fields(qtbot: QtBot) -> None:
    dialog = _dialog(qtbot)
    dialog._wavelength_min.setText("4000")
    dialog._element_combo.setCurrentIndex(dialog._element_combo.findData("FE"))
    dialog._apply_filters()

    dialog._reset_filters()

    assert dialog._element_combo.currentIndex() == -1
    assert dialog._element_combo.currentText() == ""
    assert dialog._wavelength_min.text() == ""
    assert dialog._wavelength_max.text() == ""
    assert dialog._table.rowCount() == 4
