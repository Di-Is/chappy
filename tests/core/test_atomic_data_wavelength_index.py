"""Tests for AtomicLineData wavelength index functionality.

f-value基準のマルチプレット代表ライン選定のための
波長インデックス機能をテストする。
"""

from __future__ import annotations

import pytest

from chappy.core.atomic_data import AtomicLine, AtomicLineData


def _line(
    line_id: str,
    species: str,
    wavelength: float,
    oscillator_strength: float,
    *,
    gamma_value: float = 1.0e8,
    element_symbol: str = "Mg",
    charge_state: int = 1,
) -> AtomicLine:
    """Create an atomic line for in-memory index tests."""
    return AtomicLine(
        line_identifier=line_id,
        species=species,
        wavelength_angstrom=wavelength,
        oscillator_strength=oscillator_strength,
        gamma_value=gamma_value,
        element_symbol=element_symbol,
        charge_state=charge_state,
        transition_name=line_id,
    )


class TestAtomicLineDataWavelengthIndex:
    """AtomicLineData の波長インデックス機能テスト."""

    def test_get_line_by_species_wavelength_exact_match(self) -> None:
        """正確な species と wavelength でラインを取得できる."""
        data = AtomicLineData(
            [
                _line("mg2_2796", "Mg II", 2796.352, 0.6123),
                _line("mg2_2803", "Mg II", 2803.531, 0.3054),
            ]
        )

        line = data.get_line_by_species_wavelength("Mg II", 2796.352)
        assert line is not None
        assert line.line_id == "mg2_2796"
        assert line.oscillator_strength == pytest.approx(0.6123)

        line = data.get_line_by_species_wavelength("Mg II", 2803.531)
        assert line is not None
        assert line.line_id == "mg2_2803"
        assert line.oscillator_strength == pytest.approx(0.3054)

    def test_get_line_by_species_wavelength_not_found(self) -> None:
        """存在しない species/wavelength は None を返す."""
        data = AtomicLineData([_line("mg2_2796", "Mg II", 2796.352, 0.6123)])

        assert data.get_line_by_species_wavelength("C IV", 2796.352) is None
        assert data.get_line_by_species_wavelength("Mg II", 1000.0) is None
        assert data.get_line_by_species_wavelength("Fe II", 9999.0) is None

    def test_wavelength_index_collision_keeps_highest_f_value(self) -> None:
        """同一 (species, wavelength) に複数ラインがある場合、f-value最大を保持."""
        data = AtomicLineData(
            [
                _line("mg2_2796_low", "Mg II", 2796.352, 0.3000),
                _line("mg2_2796_high", "Mg II", 2796.352, 0.6123),
            ]
        )

        line = data.get_line_by_species_wavelength("Mg II", 2796.352)
        assert line is not None
        assert line.line_id == "mg2_2796_high"
        assert line.oscillator_strength == pytest.approx(0.6123)

    def test_wavelength_rounding_precision_0_001_angstrom(self) -> None:
        """丸め精度 0.001Å（小数第3位）のテスト."""
        data = AtomicLineData([_line("line_a", "Mg II", 2796.3524, 0.5)])

        line = data.get_line_by_species_wavelength("Mg II", 2796.352)
        assert line is not None
        assert line.line_id == "line_a"

        line = data.get_line_by_species_wavelength("Mg II", 2796.353)
        assert line is None

    def test_wavelength_index_excludes_invalid_lines(self) -> None:
        """f-value=0 のラインは is_valid=False のためインデックスに含まれない."""
        data = AtomicLineData(
            [
                _line("zero_f", "H I", 1000.0, 0.0, element_symbol="H", charge_state=0),
                _line("valid_f", "H I", 1001.0, 0.1, element_symbol="H", charge_state=0),
            ]
        )

        assert data.get_line_by_species_wavelength("H I", 1000.0) is None

        line = data.get_line_by_species_wavelength("H I", 1001.0)
        assert line is not None
        assert line.line_id == "valid_f"

    def test_wavelength_index_empty_data(self) -> None:
        """空のデータでもインデックスは正常に動作."""
        data = AtomicLineData()

        assert data.get_line_by_species_wavelength("Mg II", 2796.352) is None
