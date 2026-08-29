"""Tests for the identify preset setup header."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel

from chappy.core.velocity_ranges import NewCandidateAnalysisHalfWidth
from chappy.gui.modes.identify.panel.new_candidate_half_width_spinbox import (
    NewCandidateAnalysisHalfWidthSpinBox,
)
from chappy.gui.modes.identify.panel.panel_models import LineListItem
from chappy.gui.modes.identify.panel.preset_lines_section import IdentifyPresetLinesSection
from chappy.gui.theme import Colors

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def _line(
    identifier: str,
    name: str,
    wavelength: float,
    f_value: float,
    *,
    is_reference: bool = False,
    multiplet_id: str = "",
) -> LineListItem:
    return LineListItem(
        identifier=identifier,
        reference=name,
        name=name,
        wavelength=wavelength,
        oscillator_strength=f_value,
        is_reference=is_reference,
        multiplet_id=multiplet_id,
    )


def test_reference_combo_shows_name_with_wavelength_sorted_ascending(qtbot: QtBot) -> None:
    """Combo entries merge name and 3-decimal wavelength in wavelength order."""
    section = IdentifyPresetLinesSection()
    qtbot.addWidget(section)

    section.set_line_items(
        [_line("line-a", "H I", 1215.67, 0.416), _line("line-b", "H I", 949.743, 0.007)]
    )

    combo = section._reference_combo
    assert combo.count() == 2
    assert combo.itemText(0) == "H I 949.743"
    assert combo.itemText(1) == "H I 1215.670"
    assert combo.itemData(0, Qt.ItemDataRole.UserRole) == "line-b"
    assert combo.itemData(1, Qt.ItemDataRole.UserRole) == "line-a"


def test_reference_combo_item_tooltip_carries_f_value_and_wavelength(qtbot: QtBot) -> None:
    """The removed f-value column survives as an item tooltip, including zero."""
    section = IdentifyPresetLinesSection()
    qtbot.addWidget(section)

    section.set_line_items([_line("line-1", "Lyman", 1215.67, 0.0)])

    item = section._reference_model.item(0)
    assert item is not None
    assert item.toolTip() == "f = 0.000, λ = 1215.670 Å"
    assert section._reference_combo.toolTip() == "f = 0.000, λ = 1215.670 Å"


def test_set_line_items_selects_reference_without_emitting(qtbot: QtBot) -> None:
    """Rebuilding the combo derives the reference silently (is_reference, else first)."""
    section = IdentifyPresetLinesSection()
    qtbot.addWidget(section)
    emitted: list[str] = []
    section.reference_line_changed.connect(emitted.append)

    section.set_line_items(
        [
            _line("line-1", "C IV", 1548.204, 0.190),
            _line("line-2", "C IV", 1550.781, 0.095, is_reference=True),
        ]
    )
    assert emitted == []
    assert section._current_reference_line_id == "line-2"
    assert (
        section._reference_combo.itemData(
            section._reference_combo.currentIndex(), Qt.ItemDataRole.UserRole
        )
        == "line-2"
    )

    section.set_line_items(
        [_line("line-3", "Mg II", 2796.354, 0.608), _line("line-4", "Mg II", 2803.531, 0.303)]
    )
    assert emitted == []
    assert section._current_reference_line_id == "line-3"


def test_user_selection_emits_reference_line_changed(qtbot: QtBot) -> None:
    """A user-driven index change emits the selected line id."""
    section = IdentifyPresetLinesSection()
    qtbot.addWidget(section)
    section.set_line_items(
        [
            _line("line-1", "C IV", 1548.204, 0.190, is_reference=True),
            _line("line-2", "C IV", 1550.781, 0.095),
        ]
    )

    with qtbot.waitSignal(section.reference_line_changed, timeout=1000) as blocker:
        section._reference_combo.setCurrentIndex(1)

    assert blocker.args == ["line-2"]
    assert section._current_reference_line_id == "line-2"


def test_multiplet_partners_of_reference_are_highlighted(qtbot: QtBot) -> None:
    """Items sharing the reference multiplet carry the selection background."""
    section = IdentifyPresetLinesSection()
    qtbot.addWidget(section)
    section.set_line_items(
        [
            _line("civ-1", "C IV", 1548.204, 0.190, is_reference=True, multiplet_id="civ"),
            _line("civ-2", "C IV", 1550.781, 0.095, multiplet_id="civ"),
            _line("mgii-1", "Mg II", 2796.354, 0.608, multiplet_id="mgii"),
        ]
    )
    expected = QColor(Colors.ACCENT_SELECTION_LIGHT)
    expected.setAlpha(100)

    def background(row: int) -> object:
        item = section._reference_model.item(row)
        assert item is not None
        return item.data(Qt.ItemDataRole.BackgroundRole)

    assert background(0) == expected
    assert background(1) == expected
    assert background(2) is None

    section._reference_combo.setCurrentIndex(2)
    assert background(0) is None
    assert background(1) is None
    assert background(2) == expected


def test_empty_line_items_clear_and_disable_reference_combo(qtbot: QtBot) -> None:
    """Without a preset selection the reference combo is empty and disabled."""
    section = IdentifyPresetLinesSection()
    qtbot.addWidget(section)
    assert not section._reference_combo.isEnabled()

    section.set_line_items([_line("line-1", "C IV", 1548.204, 0.190)])
    assert section._reference_combo.isEnabled()

    section.set_line_items([])
    assert section._reference_combo.count() == 0
    assert not section._reference_combo.isEnabled()


def test_reference_combo_popup_lists_large_presets_without_scrolling(qtbot: QtBot) -> None:
    """The popup enumerates all preset lines instead of scrolling at Qt's default 10."""
    section = IdentifyPresetLinesSection()
    qtbot.addWidget(section)

    assert section._reference_combo.maxVisibleItems() >= 50


def test_reference_label_is_buddied_and_combo_named_accessibly(qtbot: QtBot) -> None:
    """The reference selector exposes its label through buddy and accessible name."""
    section = IdentifyPresetLinesSection()
    qtbot.addWidget(section)

    label = section.findChild(QLabel, "identifyReferenceLineLabel")
    assert label is not None
    assert label.buddy() is section._reference_combo
    assert label.text() == "Reference line"
    assert section._reference_combo.accessibleName() == "Reference line"


def test_new_candidate_half_width_is_typed_buddied_and_scoped(qtbot: QtBot) -> None:
    """The advanced editor should expose its future-candidate scope accessibly."""
    section = IdentifyPresetLinesSection()
    qtbot.addWidget(section)
    label = section.findChild(QLabel, "identifyNewCandidateAnalysisHalfWidthLabel")
    spinbox = section.findChild(
        NewCandidateAnalysisHalfWidthSpinBox, "identifyNewCandidateAnalysisHalfWidthSpinBox"
    )
    assert label is not None
    assert spinbox is not None
    assert label.buddy() is spinbox
    assert label.text() == "New-candidate range"
    assert spinbox.accessibleName() == "New-candidate analysis range"
    assert "Shift previews and newly added candidates" in spinbox.accessibleDescription()
    assert "Existing temporary lines" in spinbox.accessibleDescription()

    accepted: list[NewCandidateAnalysisHalfWidth] = []
    section.new_candidate_analysis_half_width_changed.connect(accepted.append)
    editor = spinbox.lineEdit()
    editor.selectAll()
    qtbot.keyClicks(editor, "340")
    qtbot.keyClick(editor, Qt.Key.Key_Return)

    assert accepted == [NewCandidateAnalysisHalfWidth(340.0)]
    assert spinbox.accepted_value == NewCandidateAnalysisHalfWidth(340.0)


def test_new_candidate_half_width_rejects_without_silent_clamp(qtbot: QtBot) -> None:
    """An out-of-range edit should retain the last valid domain value and explain why."""
    section = IdentifyPresetLinesSection()
    qtbot.addWidget(section)
    section.show()
    section.set_new_candidate_analysis_half_width(NewCandidateAnalysisHalfWidth(500.0))
    spinbox = section.findChild(
        NewCandidateAnalysisHalfWidthSpinBox, "identifyNewCandidateAnalysisHalfWidthSpinBox"
    )
    error = section.findChild(QLabel, "identifyNewCandidateHalfWidthError")
    assert spinbox is not None
    assert error is not None

    editor = spinbox.lineEdit()
    editor.selectAll()
    qtbot.keyClicks(editor, "5000")
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    qtbot.wait(0)

    assert spinbox.accepted_value == NewCandidateAnalysisHalfWidth(500.0)
    assert spinbox.value() == 500.0
    assert "10" in error.text()
    assert "2000" in error.text()
    assert error.isVisible() is True
