"""Tests for f-value based representative ranking in LineSelectionDialog.

マルチプレット代表ライン選定のためのf-value基準ランキングをテストする。
"""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from chappy.core.atomic_data import AtomicLine, AtomicLineData
from chappy.gui.dialogs.line_selection_dialog import LineSelectionDialog
from chappy.presentation.line_selection.presenter import LineSelectionPresenter
from scripts.i18n_lupdate import run_lupdate


def _make_atomic_line(
    line_id: str,
    *,
    wavelength: float = 1215.67,
    oscillator_strength: float = 0.5,
    component_index: int | None = None,
) -> AtomicLine:
    """Create a minimal AtomicLine for testing."""
    return AtomicLine(
        line_identifier=line_id,
        species="H I",
        wavelength_angstrom=wavelength,
        oscillator_strength=oscillator_strength,
        gamma_value=1.0e8,
        element_symbol="H",
        charge_state=0,
        transition_name=f"Test {line_id}",
        component_index=component_index,
    )


class _ModeStateStub:
    """Mode state object exposing only attributes used in LineSelectionDialog."""

    def __init__(self) -> None:
        """Initialize a stub with required dialog attributes."""
        self.fitting_groups: dict[str, object] = {"group-a": object(), "group-b": object()}


def _make_valid_stub_mode_state() -> _ModeStateStub:
    """Create a dialog mode state stub that satisfies required attributes."""
    return _ModeStateStub()


class TestRepresentativeRankFValue:
    """_representative_rank の f-value 優先度テスト."""

    def test_f_value_priority_after_component_index(self) -> None:
        """f-value は component_index の次に優先される."""
        # Same component_index (None), different f-values
        line_low_f = _make_atomic_line("low", oscillator_strength=0.3)
        line_high_f = _make_atomic_line("high", oscillator_strength=0.6)

        rank_low = LineSelectionPresenter.representative_rank(line_low_f)
        rank_high = LineSelectionPresenter.representative_rank(line_high_f)

        # Higher f-value should rank lower (first in sorted order)
        assert rank_high < rank_low

    def test_higher_f_value_ranks_first(self) -> None:
        """f-value が大きい方が先にランクされる."""
        lines = [
            _make_atomic_line("a", wavelength=2803.0, oscillator_strength=0.3),
            _make_atomic_line("b", wavelength=2796.0, oscillator_strength=0.6),
            _make_atomic_line("c", wavelength=2800.0, oscillator_strength=0.5),
        ]

        sorted_lines = sorted(lines, key=LineSelectionPresenter.representative_rank)

        # Sorted by f-value descending: b(0.6), c(0.5), a(0.3)
        assert sorted_lines[0].line_id == "b"
        assert sorted_lines[1].line_id == "c"
        assert sorted_lines[2].line_id == "a"

    def test_component_index_takes_precedence_over_f_value(self) -> None:
        """component_index は f-value より優先される."""
        line_high_f_no_component = _make_atomic_line(
            "high_no_comp", oscillator_strength=0.9, component_index=None
        )
        line_low_f_with_component = _make_atomic_line(
            "low_with_comp", oscillator_strength=0.1, component_index=1
        )

        rank_high_no_comp = LineSelectionPresenter.representative_rank(line_high_f_no_component)
        rank_low_with_comp = LineSelectionPresenter.representative_rank(line_low_f_with_component)

        # Line with component_index should rank first (lower tuple)
        assert rank_low_with_comp < rank_high_no_comp

    def test_same_f_value_sorted_by_wavelength(self) -> None:
        """同じ f-value の場合、wavelength でタイブレーク."""
        line_a = _make_atomic_line("a", wavelength=2803.0, oscillator_strength=0.5)
        line_b = _make_atomic_line("b", wavelength=2796.0, oscillator_strength=0.5)

        rank_a = LineSelectionPresenter.representative_rank(line_a)
        rank_b = LineSelectionPresenter.representative_rank(line_b)

        # Same f-value, so wavelength decides: b(2796) < a(2803)
        assert rank_b < rank_a

    def test_rank_tuple_structure(self) -> None:
        """戻り値のタプル構造を検証."""
        line = _make_atomic_line(
            "test", wavelength=1215.67, oscillator_strength=0.416, component_index=2
        )

        rank = LineSelectionPresenter.representative_rank(line)

        # Should be 4-tuple: (component, -f_value, wavelength, line_id)
        assert isinstance(rank, tuple)
        assert len(rank) == 4
        assert rank[0] == 2.0  # component_index
        assert rank[1] == pytest.approx(-0.416)  # -f_value
        assert rank[2] == pytest.approx(1215.67)  # wavelength
        assert rank[3] == "test"  # line_id


def test_member_row_checkbox_toggle_selects_whole_multiplet(qapp: object) -> None:
    """Checking a member row selects every component of its multiplet."""
    from PySide6.QtCore import Qt

    def _multiplet_line(line_id: str, wavelength: float, f_value: float, index: int) -> AtomicLine:
        return AtomicLine(
            line_identifier=line_id,
            species="C IV",
            wavelength_angstrom=wavelength,
            oscillator_strength=f_value,
            gamma_value=1.0e8,
            element_symbol="C",
            charge_state=3,
            transition_name=f"C IV {wavelength:.0f}",
            multiplet_id="civ",
            multiplet_label="C IV",
            component_index=index,
        )

    rep = _multiplet_line("rep", 1548.2, 0.6, 0)
    member = _multiplet_line("member", 1550.8, 0.3, 1)
    dialog = LineSelectionDialog(atomic_data=AtomicLineData([rep, member]))

    member_row = next(
        row
        for row in range(dialog._table.rowCount())
        if dialog._table.item(row, 0).data(Qt.ItemDataRole.UserRole) == "member"
    )
    member_checkbox = dialog._table.item(member_row, 0)
    assert member_checkbox.flags() & Qt.ItemFlag.ItemIsUserCheckable

    member_checkbox.setCheckState(Qt.CheckState.Checked)
    assert dialog._session.selected_ids == frozenset({"rep", "member"})

    member_checkbox = dialog._table.item(member_row, 0)
    member_checkbox.setCheckState(Qt.CheckState.Unchecked)
    assert dialog._session.selected_ids == frozenset()


def test_line_selection_dialog_rejects_mode_state_without_required_attributes(
    qapp: object,
) -> None:
    """Mode state missing required attributes should fail fast."""

    class _BadModeState:
        """Object with no relevant mode-state attributes."""

        pass

    with pytest.raises(TypeError, match="LineSelectionDialog"):
        LineSelectionDialog(mode_state=_BadModeState(), atomic_data=AtomicLineData())


def test_line_selection_dialog_requires_atomic_data(qapp: object) -> None:
    """Atomic data is a required composition dependency."""
    with pytest.raises(TypeError, match="atomic_data"):
        LineSelectionDialog()


def test_line_selection_dialog_accepts_mode_state_with_required_attributes(qapp: object) -> None:
    """Mode state with required attributes should be accepted."""
    mode_state = _make_valid_stub_mode_state()
    dialog = LineSelectionDialog(mode_state=mode_state, atomic_data=AtomicLineData())
    assert dialog.mode_state is mode_state


def test_lupdate_extracts_line_selection_common_button_sources(tmp_path: Path) -> None:
    """Verify lupdate extracts migrated LineSelectionDialog source texts."""
    if shutil.which("pyside6-lupdate") is None:
        pytest.skip("pyside6-lupdate is not available")

    ts_path = tmp_path / "line_selection_dialog_ja.ts"
    run_lupdate(
        source_dirs=[
            Path("src/chappy/gui/dialogs/line_selection_dialog.py"),
            Path("src/chappy/gui/dialogs/line_selection_dialog_builder.py"),
        ],
        ts_output=ts_path,
    )

    root = ET.parse(ts_path).getroot()
    sources = {
        source.text
        for source in root.findall("./context/message/source")
        if source.text is not None
    }
    expected_sources = {
        "Cancel",
        "Line Database Search",
        "Add selected lines",
        "{count} lines",
        "Minimum wavelength exceeds the maximum.",
        "No lines selected",
    }
    assert expected_sources <= sources
    assert not any("GUI__" in source for source in sources)
    assert not any("DLG__" in source for source in sources)
