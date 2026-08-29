"""Tests for velocity plot subplot order matching side panel line order."""

from chappy.core.absorption.models import AbsorptionLine
from chappy.core.absorption_display import sort_lines_for_display
from chappy.core.absorption_display import group_lines_by_multiplet


def _make_line(
    line_id: str,
    *,
    center_z: float = 1.0,
    rest_wavelength: float = 1215.67,
    species: str = "H I",
    multiplet_ids: list[str] | None = None,
    oscillator_strength: float = 0.1,
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
        oscillator_strength=oscillator_strength,
        gamma_value=1e8,
    )


def _flatten_multiplet_groups(lines: list[AbsorptionLine]) -> list[AbsorptionLine]:
    """Apply the same sorting logic as the UI components.

    This is the expected sorting algorithm used by both:
    - Optimize tree render workflow
    - OptimizeVelocityPlotController.build_context()
    """
    sorted_lines = sort_lines_for_display(lines)
    groups = group_lines_by_multiplet(sorted_lines)
    return [line for group in groups for line in group]


class TestVelocityPlotLineOrderConsistency:
    """Tests ensuring velocity plot order matches side panel order."""

    def test_single_line_order_preserved(self) -> None:
        """Single line should remain in the same position."""
        line = _make_line("line1", center_z=0.5, rest_wavelength=1215.67)

        result = _flatten_multiplet_groups([line])

        assert len(result) == 1
        assert result[0].line_id == "line1"

    def test_multiple_lines_sorted_by_center_z(self) -> None:
        """Lines with different center_z should be sorted ascending."""
        line_high_z = _make_line("line_high", center_z=2.0, rest_wavelength=1215.67)
        line_low_z = _make_line("line_low", center_z=1.0, rest_wavelength=1215.67)

        # Input order: high_z first
        result = _flatten_multiplet_groups([line_high_z, line_low_z])

        assert len(result) == 2
        assert result[0].line_id == "line_low"  # Lower z first
        assert result[1].line_id == "line_high"

    def test_same_z_sorted_by_wavelength(self) -> None:
        """Lines with same center_z should be sorted by rest_wavelength."""
        line_long = _make_line("line_long", center_z=1.0, rest_wavelength=2000.0)
        line_short = _make_line("line_short", center_z=1.0, rest_wavelength=1215.67)

        # Input order: long wavelength first
        result = _flatten_multiplet_groups([line_long, line_short])

        assert len(result) == 2
        assert result[0].line_id == "line_short"  # Shorter wavelength first
        assert result[1].line_id == "line_long"

    def test_multiplet_doublet_f_value_ordering(self) -> None:
        """Within multiplet, lines should be sorted by f-value descending."""
        # Mg II doublet: 2796 has higher f-value than 2803
        line_2803 = _make_line(
            "abs_2803",
            species="Mg II",
            rest_wavelength=2803.531,
            multiplet_ids=["abs_2796"],
            oscillator_strength=0.3054,
        )
        line_2796 = _make_line(
            "abs_2796",
            species="Mg II",
            rest_wavelength=2796.352,
            multiplet_ids=["abs_2803"],
            oscillator_strength=0.6123,
        )

        # Input order: 2803 first (lower f-value)
        result = _flatten_multiplet_groups([line_2803, line_2796])

        assert len(result) == 2
        # Higher f-value (2796: 0.6123) should come first
        assert result[0].line_id == "abs_2796"
        assert result[1].line_id == "abs_2803"

    def test_empty_list_returns_empty(self) -> None:
        """Empty input should return empty list."""
        result = _flatten_multiplet_groups([])

        assert result == []

    def test_no_multiplet_individual_ordering(self) -> None:
        """Lines without multiplet refs should be sorted individually."""
        line_a = _make_line("line_a", center_z=1.0, rest_wavelength=1550.0)
        line_b = _make_line("line_b", center_z=1.0, rest_wavelength=1215.67)
        line_c = _make_line("line_c", center_z=0.5, rest_wavelength=2000.0)

        result = _flatten_multiplet_groups([line_a, line_b, line_c])

        assert len(result) == 3
        # Expected: c (z=0.5), b (z=1.0, wav=1215), a (z=1.0, wav=1550)
        assert result[0].line_id == "line_c"
        assert result[1].line_id == "line_b"
        assert result[2].line_id == "line_a"

    def test_mixed_multiplet_and_individual_lines(self) -> None:
        """Multiplets should be grouped together, individuals sorted separately."""
        mg_2803 = _make_line(
            "mg_2803",
            center_z=1.0,
            species="Mg II",
            rest_wavelength=2803.531,
            multiplet_ids=["mg_2796"],
            oscillator_strength=0.3054,
        )
        mg_2796 = _make_line(
            "mg_2796",
            center_z=1.0,
            species="Mg II",
            rest_wavelength=2796.352,
            multiplet_ids=["mg_2803"],
            oscillator_strength=0.6123,
        )
        lya = _make_line("lya", center_z=0.5, rest_wavelength=1215.67)

        result = _flatten_multiplet_groups([mg_2803, lya, mg_2796])

        assert len(result) == 3
        assert result[0].line_id == "lya"
        assert result[1].line_id == "mg_2796"
        assert result[2].line_id == "mg_2803"


class TestVelocityPlotEdgeCases:
    """Edge case tests for velocity plot line ordering."""

    def test_same_z_same_wavelength_stable_by_line_id(self) -> None:
        """Lines with identical z and wavelength should be stable-sorted by line_id."""
        line_b = _make_line("line_b", center_z=1.0, rest_wavelength=1215.67)
        line_a = _make_line("line_a", center_z=1.0, rest_wavelength=1215.67)

        result = _flatten_multiplet_groups([line_b, line_a])

        assert len(result) == 2
        assert result[0].line_id == "line_a"
        assert result[1].line_id == "line_b"

    def test_asymmetric_multiplet_reference(self) -> None:
        """Asymmetric multiplet refs (A->B but not B->A) should still group."""
        line_a = _make_line(
            "line_a",
            center_z=1.0,
            rest_wavelength=1000.0,
            multiplet_ids=["line_b"],
            oscillator_strength=0.5,
        )
        line_b = _make_line(
            "line_b",
            center_z=1.0,
            rest_wavelength=1001.0,
            multiplet_ids=[],
            oscillator_strength=0.3,
        )

        result = _flatten_multiplet_groups([line_a, line_b])

        assert len(result) == 2
        # Higher f-value (line_a: 0.5) should come first
        assert result[0].line_id == "line_a"
        assert result[1].line_id == "line_b"

    def test_triplet_f_value_ordering(self) -> None:
        """Triplet should be sorted by f-value within the group."""
        line_c = _make_line("line_c", multiplet_ids=["line_a", "line_b"], oscillator_strength=0.1)
        line_a = _make_line("line_a", multiplet_ids=["line_b", "line_c"], oscillator_strength=0.5)
        line_b = _make_line("line_b", multiplet_ids=["line_a", "line_c"], oscillator_strength=0.3)

        result = _flatten_multiplet_groups([line_c, line_a, line_b])

        assert len(result) == 3
        # Sorted by f-value descending: a(0.5), b(0.3), c(0.1)
        assert result[0].line_id == "line_a"
        assert result[1].line_id == "line_b"
        assert result[2].line_id == "line_c"

    def test_missing_f_value_falls_back_to_wavelength(self) -> None:
        """Lines with f-value=0 should fall back to wavelength sorting."""
        line_long = _make_line(
            "line_long",
            rest_wavelength=2000.0,
            multiplet_ids=["line_short"],
            oscillator_strength=0.0,
        )
        line_short = _make_line(
            "line_short",
            rest_wavelength=1000.0,
            multiplet_ids=["line_long"],
            oscillator_strength=0.0,
        )

        result = _flatten_multiplet_groups([line_long, line_short])

        assert len(result) == 2
        # With f=0, fall back to wavelength: shorter first
        assert result[0].line_id == "line_short"
        assert result[1].line_id == "line_long"
