"""Element-order tests for the atomic-line repository."""

from __future__ import annotations

from chappy.core.atomic_data import AtomicLine, AtomicLineData


def _line(identifier: str, element: str) -> AtomicLine:
    return AtomicLine(
        line_identifier=identifier,
        species=f"{element} I",
        wavelength_angstrom=1000.0,
        oscillator_strength=0.1,
        gamma_value=1.0,
        element_symbol=element,
        charge_state=0,
    )


def test_available_elements_follow_atomic_number_with_deuterium_after_hydrogen() -> None:
    data = AtomicLineData(
        [
            _line("fe", "Fe"),
            _line("b", "B"),
            _line("he", "He"),
            _line("d", "D"),
            _line("be", "Be"),
            _line("h", "H"),
        ]
    )

    assert data.get_available_elements() == ["H", "D", "HE", "BE", "B", "FE"]


def test_unknown_catalog_symbols_remain_searchable_after_known_elements() -> None:
    data = AtomicLineData([_line("zz", "Zz"), _line("c", "C"), _line("xx", "Xx"), _line("h", "H")])

    assert data.get_available_elements() == ["H", "C", "XX", "ZZ"]
