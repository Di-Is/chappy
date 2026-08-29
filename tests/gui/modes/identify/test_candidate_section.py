"""Tests for the identify detection candidate section."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from chappy.gui.modes.identify.panel.candidate_section import IdentifyCandidateSection
from chappy.gui.modes.identify.panel.panel_models import CandidateRow
from tests.gui.support.faithful_env import faithful_application_environment

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def _candidate(identifier: str, start: float, end: float, sigma: float) -> CandidateRow:
    return CandidateRow(
        identifier=identifier, lambda_start=start, lambda_end=end, sigma=sigma, status="unused"
    )


def test_range_column_is_short_with_full_precision_tooltip(qtbot: QtBot) -> None:
    """The λ range cell uses 1-decimal display and keeps full precision in the tooltip."""
    section = IdentifyCandidateSection()
    qtbot.addWidget(section)

    section.set_candidates([_candidate("c-1", 4523.1234, 4530.5678, 12.34)])

    range_item = section._candidate_table.item(0, 0)
    sigma_item = section._candidate_table.item(0, 1)
    assert range_item is not None
    assert sigma_item is not None
    assert range_item.text() == "4523.1–4530.6"
    assert range_item.toolTip() == "4523.123–4530.568 Å"
    assert sigma_item.text() == "12.3"
    assert sigma_item.textAlignment() & Qt.AlignmentFlag.AlignRight


def test_sigma_column_fits_four_digit_values_without_elision(qtbot: QtBot) -> None:
    """The σ column width covers the widest expected value under the real app font."""
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    with faithful_application_environment(app, "ja"):
        section = IdentifyCandidateSection()
        qtbot.addWidget(section)

        section.set_candidates([_candidate("c-1", 4788.8, 4795.1, 9999.9)])

        table = section._candidate_table
        assert table.columnWidth(1) >= table.sizeHintForColumn(1)


def test_sigma_column_sorts_numerically(qtbot: QtBot) -> None:
    """Sorting the σ column compares numeric values, not display strings."""
    section = IdentifyCandidateSection()
    qtbot.addWidget(section)

    section.set_candidates(
        [_candidate("c-low", 4000.0, 4004.0, 9.5), _candidate("c-high", 5000.0, 5004.0, 12.0)]
    )

    section._candidate_table.sortItems(1, Qt.SortOrder.AscendingOrder)

    first = section._candidate_table.item(0, 1)
    assert first is not None
    assert first.text() == "9.5"


def test_sigma_slider_and_spin_stay_in_range_and_emit_one_shared_intent(qtbot: QtBot) -> None:
    """Slider and numeric input remain synchronized through the existing signal."""
    section = IdentifyCandidateSection()
    qtbot.addWidget(section)

    assert (section._sigma_slider.minimum(), section._sigma_slider.maximum()) == (20, 1000)
    assert (section._sigma_spin.minimum(), section._sigma_spin.maximum()) == (2.0, 100.0)

    slider_spy = QSignalSpy(section.sigma_threshold_changed)
    section._sigma_slider.setValue(73)
    assert section._sigma_spin.value() == 7.3
    assert slider_spy.count() == 1
    assert slider_spy.at(0) == [7.3]

    spin_spy = QSignalSpy(section.sigma_threshold_changed)
    section._sigma_spin.setValue(8.4)
    assert section._sigma_slider.value() == 84
    assert spin_spy.count() == 1
    assert spin_spy.at(0) == [8.4]


def test_single_click_selects_without_moving_the_spectrum(qtbot: QtBot) -> None:
    """A single click only selects, so browsing candidates never moves the view."""
    section = IdentifyCandidateSection()
    qtbot.addWidget(section)
    section.resize(300, 400)
    section.show()

    section.set_candidates([_candidate("c-1", 4523.1, 4530.5, 12.3)])
    table = section._candidate_table
    item = table.item(0, 0)
    assert item is not None

    spy = QSignalSpy(section.candidate_activated)
    qtbot.mouseClick(
        table.viewport(), Qt.MouseButton.LeftButton, pos=table.visualItemRect(item).center()
    )

    assert spy.count() == 0
    assert table.currentRow() == 0


def test_enter_activates_current_candidate_once(qtbot: QtBot) -> None:
    """Up/down selection followed by Enter activates the current row once."""
    section = IdentifyCandidateSection()
    qtbot.addWidget(section)
    section.resize(300, 400)
    section.show()
    section.set_candidates(
        [_candidate("c-1", 4523.1, 4530.5, 12.3), _candidate("c-2", 4600.0, 4601.0, 8.0)]
    )
    table = section._candidate_table
    table.setCurrentCell(0, 0)
    table.setFocus()
    qtbot.keyClick(table, Qt.Key.Key_Down)

    spy = QSignalSpy(section.candidate_activated)
    qtbot.keyClick(table, Qt.Key.Key_Return)

    assert spy.count() == 1
    assert spy.at(0) == ["c-2"]


def test_double_click_activates_candidate_once(qtbot: QtBot) -> None:
    """A double-click uses Qt activation and emits one navigation request."""
    section = IdentifyCandidateSection()
    qtbot.addWidget(section)
    section.resize(300, 400)
    section.show()
    section.set_candidates([_candidate("c-1", 4523.1, 4530.5, 12.3)])
    table = section._candidate_table
    item = table.item(0, 0)
    assert item is not None

    spy = QSignalSpy(section.candidate_activated)
    qtbot.mouseDClick(
        table.viewport(), Qt.MouseButton.LeftButton, pos=table.visualItemRect(item).center()
    )

    assert spy.count() == 1
    assert spy.at(0) == ["c-1"]


def test_double_click_targets_visual_row_after_sorting(qtbot: QtBot) -> None:
    """After a sort reorders rows, activation follows the visual row, not the input order."""
    section = IdentifyCandidateSection()
    qtbot.addWidget(section)
    section.resize(300, 400)
    section.show()

    section.set_candidates(
        [_candidate("c-blue", 4000.0, 4004.0, 8.0), _candidate("c-red", 5000.0, 5004.0, 15.0)]
    )
    table = section._candidate_table
    table.sortItems(0, Qt.SortOrder.DescendingOrder)

    top_item = table.item(0, 0)
    assert top_item is not None
    assert top_item.text().startswith("5000.0")

    with qtbot.waitSignal(section.candidate_activated, timeout=1000) as blocker:
        qtbot.mouseDClick(
            table.viewport(),
            Qt.MouseButton.LeftButton,
            pos=table.visualItemRect(top_item).center(),
        )

    assert blocker.args == ["c-red"]
