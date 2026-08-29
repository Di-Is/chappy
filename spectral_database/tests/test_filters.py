"""Tests for spectral line filtering behaviour."""

from __future__ import annotations

import math

from astropy.table import Table
from spectral_database.data_models import FilterOptions
from spectral_database.filters import collect_level_decay_totals, to_records


def _build_hydrogen_table() -> Table:
    """Create a minimal NIST-like table with and without term metadata."""
    table = Table(
        {
            "Ritz Wavelength Vacuum (Å)": [919.351334, 920.963006, 1875.612913, 40512.657],
            "Unc. Ritz": [0.000005, 0.000007, 0.00002, 0.00005],
            "f": [0.0012011, 0.0016062, 0.0010427, 0.0008321],
            "Aki": [5.1e7, 4.8e7, 2.0e6, 1.7e6],
            "Ei": [0.0, 0.0, 0.000361, 0.00037],
            "Ek": [0.001672, 0.001669, 0.000594, 0.000401],
            "Type": ["E1", "E1", "E1", "E1"],
            "Lower level": ["1s|2S|1/2", "1s|2S|1/2", "3", "4"],
            "Upper level": ["11", "10p|2P*|3/2", "4", "5"],
            "gi   gk": ["2 - 242", "2 - 200", "18 - 32", "32 - 50"],
        }
    )
    table.meta["species"] = "H I"
    return table


def test_to_records_skips_hydrogen_principal_only_levels() -> None:
    """Ensure hydrogen principal-only levels are removed when filtered."""
    table = _build_hydrogen_table()
    filters = FilterOptions()
    filters.allowed_types = {"E1"}
    filters.assume_e1_when_missing = True

    records = to_records(table, filters=filters)

    assert {r.upper_level_conf for r in records} == {"10p"}


def test_to_records_rounds_name_to_single_decimal() -> None:
    """Verify record names are rounded to a single decimal place."""
    table = Table(
        {
            "Ritz Wavelength Vacuum (Å)": [919.351342],
            "Unc. Ritz": [0.000005],
            "f": [0.0012011],
            "Aki": [3.6e6],
            "Ei": [0.0],
            "Ek": [13.48],
            "Type": ["E1"],
            "Lower level": ["1s|2S|1/2"],
            "Upper level": ["11p|2P*|3/2"],
            "gi   gk": ["2 - 6"],
        }
    )
    table.meta["species"] = "H I"

    records = to_records(table, filters=FilterOptions())

    assert len(records) == 1
    assert records[0].name == "H I 919.4"


def test_to_records_can_exclude_principal_only_levels_when_opted_out() -> None:
    """Confirm non-hydrogen tables honor the principal-only exclusion flag."""
    table = _build_hydrogen_table()
    table.meta["species"] = "He I"
    filters = FilterOptions()
    filters.allowed_types = {"E1"}
    filters.assume_e1_when_missing = True

    records = to_records(table, filters=filters)

    # Non-hydrogen retains principal-only entries by default.
    assert {r.upper_level_conf for r in records} == {"11", "10p", "4", "5"}

    filters.include_principal_only_levels = False
    records_excluding = to_records(table, filters=filters)

    assert {r.upper_level_conf for r in records_excluding} == {"10p"}


def test_to_records_aggregates_gamma_from_level_decays() -> None:
    """Check that gamma values aggregate across decay pathways."""
    table = Table(
        {
            "Ritz Wavelength Vacuum (Å)": [1025.722, 1039.230, 1215.670],
            "Unc. Ritz": [0.00001, 0.00001, 0.00001],
            "f": [0.05, 0.03, 0.1],
            "Aki": [1.0e8, 2.0e8, 5.0e7],
            "Ei": [10.2, 10.2, 0.0],
            "Ek": [12.1, 12.1, 10.2],
            "Type": ["E1", "E1", "E1"],
            "Lower level": ["2s|2S|1/2", "2p|2P|3/2", "1s|2S|1/2"],
            "Upper level": ["3p|2P|1/2", "3p|2P|1/2", "2s|2S|1/2"],
            "gi   gk": ["2 - 6", "4 - 6", "2 - 2"],
        }
    )
    table.meta["species"] = "H I"

    records = to_records(table, filters=FilterOptions())

    assert len(records) == 3

    three_p_to_two_s = next(
        r
        for r in records
        if r.upper_level_conf == "3p" and (r.lower_level_conf or "").startswith("2s")
    )
    three_p_to_two_p = next(
        r
        for r in records
        if r.upper_level_conf == "3p" and (r.lower_level_conf or "").startswith("2p")
    )
    two_s_to_one_s = next(r for r in records if r.upper_level_conf == "2s")

    assert math.isclose(three_p_to_two_s.gamma_upper or 0.0, 3.0e8, rel_tol=1e-8)
    assert math.isclose(three_p_to_two_s.gamma_lower or 0.0, 5.0e7, rel_tol=1e-8)
    assert math.isclose(three_p_to_two_s.gamma, 3.5e8, rel_tol=1e-8)

    assert math.isclose(three_p_to_two_p.gamma_upper or 0.0, 3.0e8, rel_tol=1e-8)
    assert math.isclose(three_p_to_two_p.gamma_lower or 0.0, 0.0, rel_tol=1e-8)
    assert math.isclose(three_p_to_two_p.gamma, 3.0e8, rel_tol=1e-8)

    assert math.isclose(two_s_to_one_s.gamma_upper or 0.0, 5.0e7, rel_tol=1e-8)
    assert math.isclose(two_s_to_one_s.gamma_lower or 0.0, 0.0, rel_tol=1e-8)
    assert math.isclose(two_s_to_one_s.gamma, 5.0e7, rel_tol=1e-8)


def test_collect_level_totals_supports_filtered_records() -> None:
    """Ensure level totals remain correct when some lines are filtered out."""
    table = Table(
        {
            "Ritz Wavelength Vacuum (Å)": [1500.0, 1502.0],
            "Unc. Ritz": [0.0001, 0.0001],
            "f": [0.2, 1e-5],
            "Aki": [1.0e8, 5.0e7],
            "Ei": [0.0, 0.1],
            "Ek": [1.0, 1.0],
            "Type": ["E1", "E1"],
            "Lower level": ["0|S|0", "0|S|0"],
            "Upper level": ["X|P|1", "X|P|1"],
        }
    )
    table.meta["species"] = "He I"

    totals = collect_level_decay_totals([table])
    records = to_records(table, filters=FilterOptions(min_f=0.1), level_totals=totals)

    assert len(records) == 1
    record = records[0]
    # Upper total includes both Aki entries even though one line was filtered out.
    assert math.isclose(record.gamma_upper or 0.0, 1.5e8, rel_tol=1e-8)
    assert math.isclose(record.gamma, 1.5e8, rel_tol=1e-8)
