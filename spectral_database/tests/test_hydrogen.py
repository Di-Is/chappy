"""Tests for hydrogen series aggregation utilities."""

from __future__ import annotations

import math
from fractions import Fraction

from astropy.table import Table
from spectral_database.data_models import FilterOptions, LineRecord
from spectral_database.filters import to_records
from spectral_database.hydrogen import extract_principal_quantum, synthesize_hydrogen_series


def test_synthesize_hydrogen_series_groups_transitions() -> None:
    """Ensure hydrogen synthesis groups transitions by principal quantum number."""
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

    group = [
        record
        for record in records
        if extract_principal_quantum(record.lower_level_conf or record._lower_term) == 2
        and extract_principal_quantum(record.upper_level_conf or record._upper_term) == 3
    ]

    accuracy_pool = ["A", "C", "B", "D"]
    for idx, record in enumerate(group):
        record.accuracy = accuracy_pool[min(idx, len(accuracy_pool) - 1)]

    ly_group = [
        record
        for record in records
        if extract_principal_quantum(record.lower_level_conf or record._lower_term) == 1
        and extract_principal_quantum(record.upper_level_conf or record._upper_term) == 2
    ]

    for record in ly_group:
        record.accuracy = "B"

    synthesized = synthesize_hydrogen_series(records)

    names = {record.name for record in synthesized}
    assert {"Lyα", "Hα"} <= names

    h_alpha = next(record for record in synthesized if record.name == "Hα")
    assert h_alpha.lower_level_conf == "2"
    assert h_alpha.upper_level_conf == "3"

    unique_lower_g: dict[tuple[str | None, str | None, str | None], float] = {}
    unique_upper_g: dict[tuple[str | None, str | None, str | None], float] = {}
    weights: list[tuple[float, float]] = []  # (weight, wavelength)
    gamma_weights: list[tuple[float, float]] = []  # (weight, gamma)
    gamma_upper_weights: list[tuple[float, float]] = []
    gamma_lower_weights: list[tuple[float, float]] = []
    lower_energy_weights: list[tuple[float, float]] = []
    upper_energy_weights: list[tuple[float, float]] = []

    def lower_g(record: LineRecord) -> float:
        if record.lower_level_j:
            j_value = float(Fraction(record.lower_level_j))
            return 2.0 * j_value + 1.0
        if record.degeneracy:
            part = record.degeneracy.split("-")[0].strip()
            return float(part)
        msg = "Missing lower-level degeneracy data"
        raise AssertionError(msg)

    def upper_g(record: LineRecord) -> float:
        if record.upper_level_j:
            j_value = float(Fraction(record.upper_level_j))
            return 2.0 * j_value + 1.0
        if record.degeneracy:
            parts = record.degeneracy.split("-")
            if len(parts) > 1:
                return float(parts[1].strip())
        msg = "Missing upper-level degeneracy data"
        raise AssertionError(msg)

    for record in group:
        g = lower_g(record)
        weight = g * record.f_value
        weights.append((weight, record.wavelength))
        gamma_weights.append((weight, record.gamma))
        if record.gamma_upper is not None:
            gamma_upper_weights.append((weight, record.gamma_upper))
        if record.gamma_lower is not None:
            gamma_lower_weights.append((weight, record.gamma_lower))
        if record.lower_level_energy is not None:
            lower_energy_weights.append((weight, record.lower_level_energy))
        if record.upper_level_energy is not None:
            upper_energy_weights.append((weight, record.upper_level_energy))
        key = (record.lower_level_conf, record.lower_level_term, record.lower_level_j)
        unique_lower_g.setdefault(key, g)

        upper_key = (record.upper_level_conf, record.upper_level_term, record.upper_level_j)
        try:
            gk = upper_g(record)
        except AssertionError:
            gk = None
        if gk is not None:
            unique_upper_g.setdefault(upper_key, gk)

    total_g = sum(unique_lower_g.values())
    total_weight = sum(w for w, _ in weights)
    total_gk = sum(unique_upper_g.values())
    expected_f = total_weight / total_g
    assert math.isclose(h_alpha.f_value, expected_f, rel_tol=1e-12)

    expected_gamma = sum(w * value for w, value in gamma_weights) / total_weight
    assert math.isclose(h_alpha.gamma, expected_gamma, rel_tol=1e-12)
    assert math.isclose(h_alpha.aki_value or 0.0, expected_gamma, rel_tol=1e-12)

    c = 299_792_458.0
    expected_freq = sum(w * (c / (wl * 1e-10)) for w, wl in weights) / total_weight
    expected_lambda = c / expected_freq / 1e-10
    assert math.isclose(h_alpha.wavelength, expected_lambda, rel_tol=1e-12)
    assert math.isclose(h_alpha.wavelength_ritz or 0.0, expected_lambda, rel_tol=1e-12)

    if gamma_upper_weights:
        gamma_upper_weight_sum = sum(w for w, _ in gamma_upper_weights)
        expected_gamma_upper = (
            sum(w * value for w, value in gamma_upper_weights) / gamma_upper_weight_sum
        )
        assert h_alpha.gamma_upper is not None
        assert math.isclose(h_alpha.gamma_upper, expected_gamma_upper, rel_tol=1e-12)
    if gamma_lower_weights:
        gamma_lower_weight_sum = sum(w for w, _ in gamma_lower_weights)
        expected_gamma_lower = (
            sum(w * value for w, value in gamma_lower_weights) / gamma_lower_weight_sum
        )
        assert h_alpha.gamma_lower is not None
        assert math.isclose(h_alpha.gamma_lower, expected_gamma_lower, rel_tol=1e-12)

    if lower_energy_weights:
        lower_energy_weight_sum = sum(w for w, _ in lower_energy_weights)
        expected_lower_energy = (
            sum(w * value for w, value in lower_energy_weights) / lower_energy_weight_sum
        )
        assert h_alpha.lower_level_energy is not None
        assert math.isclose(h_alpha.lower_level_energy, expected_lower_energy, rel_tol=1e-12)
    if upper_energy_weights:
        upper_energy_weight_sum = sum(w for w, _ in upper_energy_weights)
        expected_upper_energy = (
            sum(w * value for w, value in upper_energy_weights) / upper_energy_weight_sum
        )
        assert h_alpha.upper_level_energy is not None
        assert math.isclose(h_alpha.upper_level_energy, expected_upper_energy, rel_tol=1e-12)

    gi_int = round(total_g)
    gk_int = round(total_gk)
    assert h_alpha.degeneracy == f"{gi_int} - {gk_int}"
    assert h_alpha.wavelength_source == "aggregated"
    assert f"Σgi={gi_int}" in (h_alpha.comment or "")
    assert f"Σgk={gk_int}" in (h_alpha.comment or "")
    assert f"{len(group)} components" in (h_alpha.comment or "")
    assert h_alpha.accuracy == "C"

    ly_alpha = next(record for record in synthesized if record.name == "Lyα")
    assert ly_alpha.lower_level_conf == "1"
    assert ly_alpha.upper_level_conf == "2"
    ly_unique_lower_g: dict[tuple[str | None, str | None, str | None], float] = {}
    ly_unique_upper_g: dict[tuple[str | None, str | None, str | None], float] = {}
    ly_weights: list[tuple[float, float]] = []
    ly_gamma_weights: list[tuple[float, float]] = []

    for record in ly_group:
        g = lower_g(record)
        weight = g * record.f_value
        ly_weights.append((weight, record.wavelength))
        ly_gamma_weights.append((weight, record.gamma))
        key = (record.lower_level_conf, record.lower_level_term, record.lower_level_j)
        ly_unique_lower_g.setdefault(key, g)

        upper_key = (record.upper_level_conf, record.upper_level_term, record.upper_level_j)
        try:
            gk = upper_g(record)
        except AssertionError:
            gk = None
        if gk is not None:
            ly_unique_upper_g.setdefault(upper_key, gk)

    ly_total_g = sum(ly_unique_lower_g.values())
    ly_total_gk = sum(ly_unique_upper_g.values())
    ly_total_weight = sum(w for w, _ in ly_weights)
    ly_expected_f = ly_total_weight / ly_total_g
    assert math.isclose(ly_alpha.f_value, ly_expected_f, rel_tol=1e-12)

    ly_expected_gamma = sum(w * value for w, value in ly_gamma_weights) / ly_total_weight
    assert math.isclose(ly_alpha.gamma, ly_expected_gamma, rel_tol=1e-12)

    assert ly_alpha.degeneracy == f"{round(ly_total_g)} - {round(ly_total_gk)}"
    assert ly_alpha.wavelength_source == "aggregated"
    assert ly_alpha.accuracy == "B"

    # Verify singlet Lyα does NOT have multiplet ID
    assert ly_alpha.absorption_multiplet_id is None

    # Verify Balmer series (Hα) does NOT get Lyman multiplet ID
    assert h_alpha.absorption_multiplet_id is None

    assert not any(record.name.endswith("-mlt") for record in synthesized)


def test_lyman_series_generates_one_unlinked_record_per_transition() -> None:
    """Verify Lyα through Lyε each produce one unlinked aggregate record."""
    # Create mock H I records for Lyman series (n=1 -> 2,3,4,5,6)
    records: list[LineRecord] = []
    wavelengths = [1215.67, 1025.72, 972.54, 949.74, 937.80]  # Lyα, β, γ, δ, ε
    n_uppers = [2, 3, 4, 5, 6]

    for wl, n_upper in zip(wavelengths, n_uppers, strict=True):
        records.append(
            LineRecord(
                line_id=f"test_ly_{n_upper}",
                name=f"H I {wl:.2f}",
                species="H I",
                wavelength=wl,
                f_value=0.1,
                gamma=1e8,
                element_symbol="H",
                charge_state=0,
                lower_level_conf="1s",
                lower_level_term="2S",
                lower_level_j="1/2",
                upper_level_conf=f"{n_upper}p",
                upper_level_term="2P",
                upper_level_j="3/2",
                degeneracy="2 - 4",
                _lower_term="1s|2S|1/2",
                _upper_term=f"{n_upper}p|2P|3/2",
            )
        )

    synthesized = synthesize_hydrogen_series(records)

    lyman_names = {"Lyα", "Lyβ", "Lyγ", "Lyδ", "Lyε"}
    lyman_records = [r for r in synthesized if r.name in lyman_names]
    assert len(lyman_records) == 5
    assert {record.name for record in lyman_records} == lyman_names
    for line in lyman_records:
        assert line.absorption_multiplet_id is None
    assert not any(record.name.endswith("-mlt") for record in synthesized)


def test_higher_lyman_series_records_remain_unlinked() -> None:
    """Verify higher Lyman aggregates also have no series-wide linkage."""
    # Test Lyζ (n=7) and higher principal quantum numbers
    records = [
        LineRecord(
            line_id=f"test_ly_n{n_upper}",
            name=f"H I test {n_upper}",
            species="H I",
            wavelength=930.0 - (n_upper - 7) * 5,
            f_value=0.01,
            gamma=1e8,
            element_symbol="H",
            charge_state=0,
            lower_level_conf="1s",
            lower_level_term="2S",
            lower_level_j="1/2",
            upper_level_conf=f"{n_upper}p",
            upper_level_term="2P",
            upper_level_j="3/2",
            degeneracy="2 - 4",
            _lower_term="1s|2S|1/2",
            _upper_term=f"{n_upper}p|2P|3/2",
        )
        for n_upper in [7, 8, 9]
    ]

    synthesized = synthesize_hydrogen_series(records)

    for line in synthesized:
        assert line.absorption_multiplet_id is None
