"""Regression tests for CSV writer energy conversion."""

from __future__ import annotations

import csv
from typing import TYPE_CHECKING

from spectral_database.csv_writer import write_csv
from spectral_database.data_models import LineRecord
from spectral_database.multiplet import process_multiplets

if TYPE_CHECKING:
    from pathlib import Path


def _minimal_record(lower_energy: float | None, upper_energy: float | None) -> LineRecord:
    """Build a LineRecord with just enough data for CSV export."""
    return LineRecord(
        line_id="nist:test",
        name="Test Line",
        species="H I",
        wavelength=1215.67,
        f_value=0.1,
        gamma=1.0,
        gamma_upper=1.0,
        gamma_lower=0.0,
        element_symbol="H",
        charge_state=0,
        lower_level_energy=lower_energy,
        upper_level_energy=upper_energy,
    )


def test_write_csv_includes_zero_lower_level_energy(tmp_path: Path) -> None:
    """Ensure Ei_eV retains zero values instead of empty strings."""
    record = _minimal_record(lower_energy=0.0, upper_energy=8065.54)
    output = tmp_path / "lines.csv"

    write_csv(str(output), [record])

    with output.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    header = rows[0]
    ei_idx = header.index("Ei_eV")
    ek_idx = header.index("Ek_eV")

    assert rows[1][ei_idx] == "0.000000"
    assert rows[1][ek_idx] == "8065.540000"


def test_write_csv_hides_absorption_multiplet_id_by_default(tmp_path: Path) -> None:
    """By default, the debug absorption_multiplet_id column is omitted."""
    record = _minimal_record(lower_energy=None, upper_energy=None)
    record.absorption_multiplet_id = "debug-multiplet"
    output = tmp_path / "lines.csv"

    write_csv(str(output), [record])

    with output.open(newline="", encoding="utf-8") as f:
        header = next(csv.reader(f))

    assert "absorption_multiplet_id" not in header


def test_write_csv_includes_absorption_multiplet_id_when_opted_in(tmp_path: Path) -> None:
    """The debug column is available when explicitly requested."""
    record = _minimal_record(lower_energy=None, upper_energy=None)
    record.absorption_multiplet_id = "mp-001"
    output = tmp_path / "lines.csv"

    write_csv(str(output), [record], include_absorption_multiplet_id=True)

    with output.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    idx = rows[0].index("absorption_multiplet_id")
    assert rows[1][idx] == "mp-001"


def test_write_csv_hides_gi_gk_by_default(tmp_path: Path) -> None:
    """By default, the degeneracy column stays hidden for end users."""
    record = _minimal_record(lower_energy=None, upper_energy=None)
    record.degeneracy = "2/1"
    output = tmp_path / "lines.csv"

    write_csv(str(output), [record])

    with output.open(newline="", encoding="utf-8") as f:
        header = next(csv.reader(f))

    assert "gi_gk" not in header


def test_write_csv_uses_f_value_header(tmp_path: Path) -> None:
    """fカラムはf_valueにリネームされている."""
    record = _minimal_record(lower_energy=None, upper_energy=None)
    output = tmp_path / "fvalue.csv"

    write_csv(str(output), [record])

    with output.open(newline="", encoding="utf-8") as f:
        header = next(csv.reader(f))

    assert "f_value" in header
    assert "f" not in header


def test_write_csv_includes_gi_gk_when_opted_in(tmp_path: Path) -> None:
    """The degeneracy column is emitted when explicitly requested."""
    record = _minimal_record(lower_energy=None, upper_energy=None)
    record.degeneracy = "4"
    output = tmp_path / "lines.csv"

    write_csv(str(output), [record], include_gi_gk=True)

    with output.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    idx = rows[0].index("gi_gk")
    assert rows[1][idx] == "4"


def test_write_csv_includes_aki_when_opted_in(tmp_path: Path) -> None:
    """Raw Aki 列はオプトイン時のみ出力される."""
    record = _minimal_record(lower_energy=None, upper_energy=None)
    record.aki_value = 2.5
    output = tmp_path / "aki.csv"

    write_csv(str(output), [record], include_aki=True)

    with output.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    header = rows[0]
    aki_idx = header.index("aki_value")
    gamma_idx = header.index("gamma")
    assert gamma_idx < aki_idx
    assert rows[1][aki_idx] == "2.5"


def test_write_csv_includes_gamma_components_when_opted_in(tmp_path: Path) -> None:
    """Diagnostic gamma decomposition columns appear when requested."""
    record = _minimal_record(lower_energy=None, upper_energy=None)
    record.gamma_upper = 3.0
    record.gamma_lower = 0.5
    record.gamma = 3.5
    output = tmp_path / "gamma.csv"

    write_csv(str(output), [record], include_gamma_components=True)

    with output.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    header = rows[0]
    gamma_idx = header.index("gamma")
    gamma_upper_idx = header.index("gamma_upper")
    gamma_lower_idx = header.index("gamma_lower")

    assert gamma_idx < gamma_upper_idx < gamma_lower_idx
    assert rows[1][gamma_idx] == "3.5"
    assert rows[1][gamma_upper_idx] == "3"
    assert rows[1][gamma_lower_idx] == "0.5"


def test_write_csv_includes_mutiplet_name(tmp_path: Path) -> None:
    """Multiplet行ではmutiplet_name列にラベルが出力される。."""
    records = [
        LineRecord(
            line_id="civ:lower->upper:1548",
            name="C IV 1548",
            species="C IV",
            wavelength=1548.19,
            f_value=0.19,
            gamma=1.0,
            element_symbol="C",
            charge_state=3,
            lower_level_conf="2s2 2p",
            lower_level_term="2P",
            lower_level_j="1/2",
            upper_level_conf="2s2 3d",
            upper_level_term="2D",
            upper_level_j="3/2",
        ),
        LineRecord(
            line_id="civ:lower->upper:1551",
            name="C IV 1551",
            species="C IV",
            wavelength=1550.77,
            f_value=0.095,
            gamma=1.0,
            element_symbol="C",
            charge_state=3,
            lower_level_conf="2s2 2p",
            lower_level_term="2P",
            lower_level_j="1/2",
            upper_level_conf="2s2 3d",
            upper_level_term="2D",
            upper_level_j="5/2",
        ),
        LineRecord(
            line_id="si:single",
            name="Si II 1260",
            species="Si II",
            wavelength=1260.42,
            f_value=0.1,
            gamma=1.0,
            element_symbol="Si",
            charge_state=1,
            lower_level_conf="3s2 3p",
            lower_level_term="2P",
            lower_level_j="1/2",
            upper_level_conf="3s2 3d",
            upper_level_term="2D",
            upper_level_j="3/2",
        ),
    ]

    process_multiplets(records)

    output = tmp_path / "lines.csv"
    write_csv(str(output), records)

    with output.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    header = rows[0]
    mutiplet_idx = header.index("mutiplet_name")
    tp_ref_idx = header.index("tp_ref")
    comment_idx = header.index("comment")

    assert mutiplet_idx < tp_ref_idx < comment_idx

    expected_label = "C IV 1548/1551"
    assert rows[1][mutiplet_idx] == expected_label
    assert rows[2][mutiplet_idx] == expected_label
    assert rows[3][mutiplet_idx] == ""

    assert "n_components" not in header
    component_index_idx = header.index("component_index")
    multiplet_id_idx = header.index("multiplet_id")

    assert rows[1][component_index_idx] == "1"
    assert rows[1][multiplet_id_idx] != ""

    assert rows[2][component_index_idx] == "2"
    assert rows[2][multiplet_id_idx] == rows[1][multiplet_id_idx]

    assert rows[3][component_index_idx] == ""
    assert rows[3][multiplet_id_idx] == ""


def test_write_csv_sorts_by_element_charge_and_wavelength(tmp_path: Path) -> None:
    """CSV出力では元素と電離度ごとに波長で昇順ソートされる。."""
    records = [
        LineRecord(
            line_id="c_iii_high",
            name="C III 1909",
            species="C III",
            wavelength=1909.0,
            f_value=0.2,
            gamma=1.0,
            element_symbol="C",
            charge_state=2,
        ),
        LineRecord(
            line_id="b_i",
            name="B I 1250",
            species="B I",
            wavelength=1250.0,
            f_value=0.05,
            gamma=1.0,
            element_symbol="B",
            charge_state=0,
        ),
        LineRecord(
            line_id="c_iv_1551",
            name="C IV 1551",
            species="C IV",
            wavelength=1551.0,
            f_value=0.095,
            gamma=1.0,
            element_symbol="C",
            charge_state=3,
        ),
        LineRecord(
            line_id="c_iv_1548",
            name="C IV 1548",
            species="C IV",
            wavelength=1548.0,
            f_value=0.19,
            gamma=1.0,
            element_symbol="C",
            charge_state=3,
        ),
    ]

    output = tmp_path / "lines.csv"
    write_csv(str(output), records)

    with output.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    header = rows[0]
    wavelength_idx = header.index("wavelength")
    element_idx = header.index("element_symbol")
    charge_idx = header.index("charge_state")

    observed_order = [
        (
            row[element_idx],
            int(row[charge_idx]) if row[charge_idx] else None,
            float(row[wavelength_idx]) if row[wavelength_idx] else None,
        )
        for row in rows[1:]
    ]

    assert observed_order == [
        ("B", 0, 1250.0),
        ("C", 2, 1909.0),
        ("C", 3, 1548.0),
        ("C", 3, 1551.0),
    ]


def test_write_csv_honors_species_order_mapping(tmp_path: Path) -> None:
    """species_orderを指定するとプリセット順で並ぶ。."""
    records = [
        LineRecord(
            line_id="c_iv_1551",
            name="C IV 1551",
            species="C IV",
            wavelength=1551.0,
            f_value=0.095,
            gamma=1.0,
            element_symbol="C",
            charge_state=3,
        ),
        LineRecord(
            line_id="b_i",
            name="B I 1250",
            species="B I",
            wavelength=1250.0,
            f_value=0.05,
            gamma=1.0,
            element_symbol="B",
            charge_state=0,
        ),
        LineRecord(
            line_id="si_ii",
            name="Si II 1260",
            species="Si II",
            wavelength=1260.4,
            f_value=0.1,
            gamma=1.0,
            element_symbol="Si",
            charge_state=1,
        ),
        LineRecord(
            line_id="c_ii",
            name="C II 1334",
            species="C II",
            wavelength=1334.5,
            f_value=0.12,
            gamma=1.0,
            element_symbol="C",
            charge_state=1,
        ),
    ]

    preset_order = ["B I", "C II", "C IV", "Si II"]
    species_order: dict[str, int] = {}
    for idx, item in enumerate(preset_order):
        normalized = item.lower()
        species_order.setdefault(normalized, idx)
        element = normalized.split()[0]
        species_order.setdefault(element, idx)

    output = tmp_path / "ordered.csv"
    write_csv(str(output), records, species_order=species_order)

    with output.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    header = rows[0]
    wavelength_idx = header.index("wavelength")
    element_idx = header.index("element_symbol")
    charge_idx = header.index("charge_state")

    observed_order = [
        (
            row[element_idx],
            int(row[charge_idx]) if row[charge_idx] else None,
            float(row[wavelength_idx]) if row[wavelength_idx] else None,
        )
        for row in rows[1:]
    ]

    assert observed_order == [
        ("B", 0, 1250.0),
        ("C", 1, 1334.5),
        ("C", 3, 1551.0),
        ("Si", 1, 1260.4),
    ]


def test_single_component_rows_leave_multiplet_columns_empty(tmp_path: Path) -> None:
    """n_components=1 の場合 multiplet 関連列は空欄になる。."""
    record = LineRecord(
        line_id="si:single",
        name="Si II 1260",
        species="Si II",
        wavelength=1260.4221,
        f_value=0.1,
        gamma=1.0,
        element_symbol="Si",
        charge_state=1,
        lower_level_conf="3s2 3p",
        lower_level_term="2P",
        lower_level_j="1/2",
        upper_level_conf="3s2 3d",
        upper_level_term="2D",
        upper_level_j="3/2",
    )

    process_multiplets([record])

    output = tmp_path / "single.csv"
    write_csv(str(output), [record])

    with output.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    header = rows[0]
    assert "n_components" not in header
    component_index_idx = header.index("component_index")
    multiplet_id_idx = header.index("multiplet_id")

    assert rows[1][component_index_idx] == ""
    assert rows[1][multiplet_id_idx] == ""
