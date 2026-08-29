"""Tests for f-value based sorting in group_lines_by_multiplet.

マルチプレット代表ライン選定のためのf-value基準ソートをテストする。
AbsorptionLineに直接格納されたoscillator_strengthを使用する。
"""

from __future__ import annotations

from chappy.core.absorption.models import AbsorptionLine
from chappy.core.absorption_display import group_lines_by_multiplet


def _make_line(
    line_id: str,
    *,
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
        center_z=1.0,
        window_kms=150.0,
        multiplet_ids=multiplet_ids if multiplet_ids is not None else [],
        multiplet_label="",
        transition_name=f"{species} {rest_wavelength:.1f}",
        oscillator_strength=oscillator_strength,
        gamma_value=1e8,
    )


class TestGroupLinesByMultipletFValue:
    """f-value を考慮したソートロジックテスト."""

    def test_doublet_highest_f_value_comes_first(self) -> None:
        """f-value が大きいラインが先頭になる."""
        # Mg II 2803 has lower f-value (0.3054)
        # Mg II 2796 has higher f-value (0.6123)
        # AbsorptionLine doublet - 2803 first in input, but 2796 should be first after sort
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

        result = group_lines_by_multiplet([line_2803, line_2796])

        assert len(result) == 1
        assert len(result[0]) == 2
        # Higher f-value (2796: 0.6123) should be first
        assert result[0][0].line_id == "abs_2796"
        assert result[0][1].line_id == "abs_2803"

    def test_f_value_missing_fallback_to_wavelength_sort(self) -> None:
        """f-value が0の場合、wavelength昇順でソート（フォールバック）."""
        # 2803 first in input, but 2796 should be first after sort (smaller wavelength)
        line_2803 = _make_line(
            "abs_2803",
            species="Mg II",
            rest_wavelength=2803.531,
            multiplet_ids=["abs_2796"],
            oscillator_strength=0.0,  # No f-value
        )
        line_2796 = _make_line(
            "abs_2796",
            species="Mg II",
            rest_wavelength=2796.352,
            multiplet_ids=["abs_2803"],
            oscillator_strength=0.0,  # No f-value
        )

        result = group_lines_by_multiplet([line_2803, line_2796])

        assert len(result) == 1
        assert len(result[0]) == 2
        # Smaller wavelength (2796.352) should be first
        assert result[0][0].line_id == "abs_2796"
        assert result[0][1].line_id == "abs_2803"

    def test_mixed_valid_and_missing_f_values(self) -> None:
        """有効f-valueを持つラインが前方、欠損は後方."""
        # Two absorption lines - one with f-value, one without
        line_2803 = _make_line(
            "abs_2803",
            species="Mg II",
            rest_wavelength=2803.531,
            multiplet_ids=["abs_2796"],
            oscillator_strength=0.0,  # No f-value
        )
        line_2796 = _make_line(
            "abs_2796",
            species="Mg II",
            rest_wavelength=2796.352,
            multiplet_ids=["abs_2803"],
            oscillator_strength=0.6123,  # Valid f-value
        )

        result = group_lines_by_multiplet([line_2803, line_2796])

        assert len(result) == 1
        assert len(result[0]) == 2
        # Line with valid f-value should be first
        assert result[0][0].line_id == "abs_2796"
        # Line without f-value should be second
        assert result[0][1].line_id == "abs_2803"

    def test_same_f_value_sorted_by_wavelength(self) -> None:
        """同じf-valueの場合、wavelength昇順でタイブレーク."""
        line_b = _make_line(
            "abs_b",
            species="H I",
            rest_wavelength=1001.0,
            multiplet_ids=["abs_a"],
            oscillator_strength=0.5,
        )
        line_a = _make_line(
            "abs_a",
            species="H I",
            rest_wavelength=1000.0,
            multiplet_ids=["abs_b"],
            oscillator_strength=0.5,
        )

        result = group_lines_by_multiplet([line_b, line_a])

        assert len(result) == 1
        assert len(result[0]) == 2
        # Same f-value (0.5), so sort by wavelength
        assert result[0][0].line_id == "abs_a"  # 1000.0
        assert result[0][1].line_id == "abs_b"  # 1001.0

    def test_grouping_still_works(self) -> None:
        """グルーピングは正しく動作する."""
        line1 = _make_line(
            "line1",
            species="Mg II",
            rest_wavelength=2796.35,
            multiplet_ids=["line2"],
            oscillator_strength=0.6,
        )
        line2 = _make_line(
            "line2",
            species="Mg II",
            rest_wavelength=2803.53,
            multiplet_ids=["line1"],
            oscillator_strength=0.3,
        )

        result = group_lines_by_multiplet([line1, line2])

        assert len(result) == 1
        assert len(result[0]) == 2
        # Should still group correctly
        assert {g.line_id for g in result[0]} == {"line1", "line2"}
