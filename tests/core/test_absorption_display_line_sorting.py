"""Tests for line sorting utility functions."""

from __future__ import annotations

import pytest

from chappy.core.absorption.models import AbsorptionLine
from chappy.core.absorption_display import sort_lines_for_display


def _make_line(
    line_id: str, *, center_z: float = 1.0, rest_wavelength: float = 1215.67, species: str = "H I"
) -> AbsorptionLine:
    """Create a minimal AbsorptionLine for testing."""
    return AbsorptionLine(
        line_id=line_id,
        species=species,
        rest_wavelength=rest_wavelength,
        center_z=center_z,
        window_kms=150.0,
        multiplet_label="",
        transition_name=f"{species} {rest_wavelength:.1f}",
        oscillator_strength=0.1,
        gamma_value=1e8,
    )


class TestSortLinesForDisplay:
    """Tests for sort_lines_for_display function."""

    def test_sort_lines_by_center_z_ascending(self) -> None:
        """Lines should be sorted by center_z in ascending order."""
        line_high_z = _make_line("line_high", center_z=2.5)
        line_low_z = _make_line("line_low", center_z=1.0)
        line_mid_z = _make_line("line_mid", center_z=1.8)

        lines = [line_high_z, line_low_z, line_mid_z]
        result = sort_lines_for_display(lines)

        assert [line.line_id for line in result] == ["line_low", "line_mid", "line_high"]

    def test_sort_lines_with_same_center_z_by_rest_wavelength(self) -> None:
        """When center_z is equal, sort by rest_wavelength."""
        line_long_wl = _make_line("line_long", center_z=1.5, rest_wavelength=2796.35)
        line_short_wl = _make_line("line_short", center_z=1.5, rest_wavelength=1215.67)
        line_mid_wl = _make_line("line_mid", center_z=1.5, rest_wavelength=1548.20)

        lines = [line_long_wl, line_short_wl, line_mid_wl]
        result = sort_lines_for_display(lines)

        assert [line.line_id for line in result] == ["line_short", "line_mid", "line_long"]

    def test_sort_lines_with_same_z_and_wavelength_by_line_id(self) -> None:
        """When center_z and rest_wavelength are equal, sort by line_id for stability."""
        line_c = _make_line("line_c", center_z=1.5, rest_wavelength=1215.67)
        line_a = _make_line("line_a", center_z=1.5, rest_wavelength=1215.67)
        line_b = _make_line("line_b", center_z=1.5, rest_wavelength=1215.67)

        lines = [line_c, line_a, line_b]
        result = sort_lines_for_display(lines)

        assert [line.line_id for line in result] == ["line_a", "line_b", "line_c"]

    def test_sort_empty_sequence_returns_empty_list(self) -> None:
        """Empty input should return empty list."""
        result = sort_lines_for_display([])

        assert result == []
        assert isinstance(result, list)

    def test_sort_single_line_returns_list_with_one_element(self) -> None:
        """Single line input should return list with that line."""
        line = _make_line("only_line", center_z=1.5)

        result = sort_lines_for_display([line])

        assert len(result) == 1
        assert result[0].line_id == "only_line"

    def test_sort_does_not_modify_input_sequence(self) -> None:
        """Input sequence should not be modified."""
        line_high_z = _make_line("line_high", center_z=2.5)
        line_low_z = _make_line("line_low", center_z=1.0)
        original_lines = [line_high_z, line_low_z]
        original_order = [line.line_id for line in original_lines]

        sort_lines_for_display(original_lines)

        assert [line.line_id for line in original_lines] == original_order

    def test_sort_returns_new_list(self) -> None:
        """Return value should be a new list, not the input."""
        lines = [_make_line("line1"), _make_line("line2")]

        result = sort_lines_for_display(lines)

        assert result is not lines

    def test_sort_mixed_criteria(self) -> None:
        """Test sorting with mixed primary and secondary keys."""
        # z=1.0, wl=2796 should come after z=1.0, wl=1215
        # z=2.0 should come after z=1.0 regardless of wavelength
        line1 = _make_line("A", center_z=2.0, rest_wavelength=1000.0)
        line2 = _make_line("B", center_z=1.0, rest_wavelength=2796.35)
        line3 = _make_line("C", center_z=1.0, rest_wavelength=1215.67)

        lines = [line1, line2, line3]
        result = sort_lines_for_display(lines)

        # center_z ascending: 1.0 < 2.0
        # For same center_z (1.0): rest_wavelength ascending: 1215.67 < 2796.35
        assert [line.line_id for line in result] == ["C", "B", "A"]
