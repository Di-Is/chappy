"""Tests for multiplet grouping utility function."""

from __future__ import annotations

from chappy.core.absorption.models import AbsorptionLine
from chappy.core.absorption_display import group_lines_by_multiplet


def _make_line(
    line_id: str,
    *,
    center_z: float = 1.0,
    rest_wavelength: float = 1215.67,
    species: str = "H I",
    multiplet_ids: list[str] | None = None,
) -> AbsorptionLine:
    """Create a minimal AbsorptionLine for testing."""
    return AbsorptionLine(
        line_id=line_id,
        species=species,
        rest_wavelength=rest_wavelength,
        center_z=center_z,
        window_kms=150.0,
        multiplet_ids=multiplet_ids if multiplet_ids is not None else [],
        multiplet_label="",
        transition_name=f"{species} {rest_wavelength:.1f}",
        oscillator_strength=0.1,
        gamma_value=1e8,
    )


class TestGroupLinesByMultiplet:
    """Tests for group_lines_by_multiplet function."""

    def test_empty_list_returns_empty(self) -> None:
        """Empty input should return empty list."""
        result = group_lines_by_multiplet([])

        assert result == []
        assert isinstance(result, list)

    def test_single_line_without_multiplet_grouped_alone(self) -> None:
        """Single line without multiplet_ids should be grouped alone."""
        line = _make_line("line1", multiplet_ids=[])

        result = group_lines_by_multiplet([line])

        assert len(result) == 1
        assert len(result[0]) == 1
        assert result[0][0].line_id == "line1"

    def test_two_line_doublet_symmetric_references(self) -> None:
        """Two lines with symmetric cross-references should group together."""
        line1 = _make_line(
            "line1", species="Mg II", rest_wavelength=2796.35, multiplet_ids=["line2"]
        )
        line2 = _make_line(
            "line2", species="Mg II", rest_wavelength=2803.53, multiplet_ids=["line1"]
        )

        result = group_lines_by_multiplet([line1, line2])

        assert len(result) == 1
        assert len(result[0]) == 2
        assert {g.line_id for g in result[0]} == {"line1", "line2"}

    def test_two_line_doublet_asymmetric_reference(self) -> None:
        """Union-Find should handle asymmetric references (Risk-7)."""
        # line1 → line2, but line2 does not reference line1
        line1 = _make_line(
            "line1", species="Mg II", rest_wavelength=2796.35, multiplet_ids=["line2"]
        )
        line2 = _make_line(
            "line2",
            species="Mg II",
            rest_wavelength=2803.53,
            multiplet_ids=[],  # No back-reference
        )

        result = group_lines_by_multiplet([line1, line2])

        assert len(result) == 1
        assert len(result[0]) == 2
        assert {g.line_id for g in result[0]} == {"line1", "line2"}

    def test_three_line_triplet(self) -> None:
        """Three or more lines should group as one."""
        line1 = _make_line("line1", multiplet_ids=["line2", "line3"])
        line2 = _make_line("line2", multiplet_ids=["line1", "line3"])
        line3 = _make_line("line3", multiplet_ids=["line1", "line2"])

        result = group_lines_by_multiplet([line1, line2, line3])

        assert len(result) == 1
        assert len(result[0]) == 3
        assert {g.line_id for g in result[0]} == {"line1", "line2", "line3"}

    def test_mixed_multiplet_and_single_lines(self) -> None:
        """Mix of multiplet and single lines should group correctly."""
        # Doublet: line1, line2
        line1 = _make_line("line1", center_z=1.0, rest_wavelength=2796.35, multiplet_ids=["line2"])
        line2 = _make_line("line2", center_z=1.0, rest_wavelength=2803.53, multiplet_ids=["line1"])
        # Single line
        line3 = _make_line("line3", center_z=2.0, rest_wavelength=1215.67, multiplet_ids=[])

        result = group_lines_by_multiplet([line1, line2, line3])

        assert len(result) == 2
        # Find the doublet group and single group
        group_sizes = sorted(len(g) for g in result)
        assert group_sizes == [1, 2]

    def test_group_order_preserved_by_first_line(self) -> None:
        """Groups should appear in order of their first line in input."""
        # Single line first
        line_single = _make_line("single", center_z=0.5, multiplet_ids=[])
        # Doublet second
        line_d1 = _make_line("d1", center_z=1.0, multiplet_ids=["d2"])
        line_d2 = _make_line("d2", center_z=1.0, multiplet_ids=["d1"])

        result = group_lines_by_multiplet([line_single, line_d1, line_d2])

        assert len(result) == 2
        # First group should be the single line (appears first in input)
        assert len(result[0]) == 1
        assert result[0][0].line_id == "single"
        # Second group should be the doublet
        assert len(result[1]) == 2

    def test_lines_not_in_input_ignored(self) -> None:
        """References to lines not in input should be ignored."""
        # line1 references line2 and line_missing, but line_missing is not in input
        line1 = _make_line("line1", multiplet_ids=["line2", "line_missing"])
        line2 = _make_line("line2", multiplet_ids=["line1"])

        result = group_lines_by_multiplet([line1, line2])

        # Should still group line1 and line2 together
        assert len(result) == 1
        assert len(result[0]) == 2
        assert {g.line_id for g in result[0]} == {"line1", "line2"}

    def test_multiple_independent_multiplets(self) -> None:
        """Multiple independent multiplets should form separate groups."""
        # First doublet: d1a, d1b
        d1a = _make_line("d1a", center_z=1.0, multiplet_ids=["d1b"])
        d1b = _make_line("d1b", center_z=1.0, multiplet_ids=["d1a"])
        # Second doublet: d2a, d2b
        d2a = _make_line("d2a", center_z=2.0, multiplet_ids=["d2b"])
        d2b = _make_line("d2b", center_z=2.0, multiplet_ids=["d2a"])

        result = group_lines_by_multiplet([d1a, d1b, d2a, d2b])

        assert len(result) == 2
        # Both groups should have 2 lines
        assert all(len(g) == 2 for g in result)
        # Verify group contents
        group_ids = [frozenset(line.line_id for line in g) for g in result]
        assert frozenset({"d1a", "d1b"}) in group_ids
        assert frozenset({"d2a", "d2b"}) in group_ids

    def test_group_lines_sorted_by_rest_wavelength(self) -> None:
        """Lines within a group should be sorted by rest_wavelength."""
        line_long = _make_line("line_long", rest_wavelength=2803.53, multiplet_ids=["line_short"])
        line_short = _make_line("line_short", rest_wavelength=2796.35, multiplet_ids=["line_long"])

        # Input order: long, short
        result = group_lines_by_multiplet([line_long, line_short])

        assert len(result) == 1
        # Within the group, should be sorted by rest_wavelength
        assert result[0][0].line_id == "line_short"  # 2796.35
        assert result[0][1].line_id == "line_long"  # 2803.53
