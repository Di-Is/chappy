"""Tests for the atomic data loader handling the new spectral CSV schema."""

from __future__ import annotations

from pathlib import Path

import pytest

from chappy.core.atomic_data import SearchFilters, charge_to_stage, stage_to_charge
from chappy.infrastructure.atomic_lines import load_atomic_data


def _write_csv(path: Path, rows: list[str]) -> None:
    header = ["# name: Test Catalog", "# version: 1.0.0"]
    content = "\n".join(header + rows)
    path.write_text(content, encoding="utf-8")


def test_parse_new_schema_extracts_extended_fields(tmp_path: Path) -> None:
    csv_path = tmp_path / "lines.csv"
    _write_csv(
        csv_path,
        [
            (
                "line_id,name,wavelength,wavelength_source,wavelength_ritz,wavelength_ritz_unc,"
                "wavelength_observed,wavelength_observed_unc,f_value,gamma,element_symbol,charge_state,"
                "Ei_eV,Ek_eV,lower_conf,lower_term,lower_J,upper_conf,upper_term,upper_J,upper_term_LS,"
                "accuracy,multiplet_id,component_index,mutiplet_name,tp_ref,line_ref,comment"
            ),
            (
                "nist:a1,H I 1215,1215.6701,ritz,1215.6701,0.0001,1215.6700,0.0002,0.4162,6.26e8,"
                "H,0,0.000,10.200,1s,2S,1/2,2p,2P*,3/2,2P,A+,hash123,2,H I 1215 doublet,TP-123,WL-123,Sample note"
            ),
        ],
    )

    data = load_atomic_data(csv_path)
    assert len(data.lines) == 1

    line = data.lines[0]
    assert line.line_id == "nist:a1"
    assert line.transition_name == "H I 1215"
    assert line.element_symbol == "H"
    assert line.charge_state == 0
    assert line.ionization_stage == charge_to_stage(0)
    assert line.multiplet_id == "hash123"
    assert line.multiplet_label == "H I 1215 doublet"
    assert line.component_index == 2
    assert line.wavelength_source == "ritz"
    assert line.wavelength_ritz == 1215.6701
    assert line.wavelength_observed == 1215.67
    assert line.energy_lower_ev == 0.0
    assert line.energy_upper_ev == 10.2
    assert line.energy_gap_ev == pytest.approx(10.2)
    assert line.lower_configuration == "1s"
    assert line.upper_term_ls == "2P"
    assert line.accuracy_code == "A+"
    assert line.transition_probability_ref == "TP-123"
    assert line.wavelength_ref == "WL-123"
    assert line.comments == "Sample note"


def test_element_symbol_preserves_standard_casing(tmp_path: Path) -> None:
    csv_path = tmp_path / "lines.csv"
    _write_csv(
        csv_path,
        [
            (
                "line_id,name,species,wavelength,f_value,gamma,element_symbol,charge_state,"
                "multiplet_name,comment"
            ),
            "co_line,Co II 1234,,1234.0,0.5,1.0e8,co,1,,",
            "fe_line,Fe II 2600,FE II,2600.0,0.3,2.0e8,,1,,",
        ],
    )

    data = load_atomic_data(csv_path)
    by_id = {line.line_id: line for line in data.lines}

    assert by_id["co_line"].element_symbol == "Co"
    assert by_id["fe_line"].element_symbol == "Fe"


def test_stage_conversion_roundtrip() -> None:
    for state in range(0, 5):
        stage = charge_to_stage(state)
        assert stage_to_charge(stage) == state


def test_search_filters_support_element_charge_and_wavelength(tmp_path: Path) -> None:
    csv_path = tmp_path / "lines.csv"
    _write_csv(
        csv_path,
        [
            "line_id,name,wavelength,f_value,gamma,element_symbol,charge_state,multiplet_name,comment",
            "id_h1,H I 1215,1215.67,0.4,1.0e8,H,0,,",
            "id_c2,C II 1334,1334.53,0.13,8.0e7,C,1,,",
            "id_c4,C IV 1548,1548.20,0.19,2.6e8,C,3,,",
        ],
    )

    data = load_atomic_data(csv_path)

    filters = SearchFilters(element_filter="C")
    carbon_lines = data.search_lines(filters)
    assert {line.line_id for line in carbon_lines} == {"id_c2", "id_c4"}

    filters = SearchFilters(charge_state=3)
    stage_lines = data.search_lines(filters)
    assert [line.line_id for line in stage_lines] == ["id_c4"]

    filters = SearchFilters(wavelength_min=1300.0, wavelength_max=1600.0)
    range_lines = data.search_lines(filters)
    assert {line.line_id for line in range_lines} == {"id_c2", "id_c4"}
