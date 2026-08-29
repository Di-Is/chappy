"""Hydrogen-series utilities for synthesizing Lyman/Balmer-style lines.

This module collects helpers to extract principal quantum numbers from
configuration strings and to aggregate resolved H I transitions into
series lines such as Lyα and Hα. Aggregated lines provide historical
short-hand labels while avoiding the scientifically dubious practice of
including principal-quantum-only NIST rows directly.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction
from typing import TYPE_CHECKING

from spectral_database.data_models import LineRecord
from spectral_database.identifiers import hashed_line_id

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

_SPEED_OF_LIGHT_M_PER_S = 299_792_458.0
_ANGSTROM_TO_M = 1e-10

_GREEK_SERIES_SYMBOLS = [
    "α",
    "β",
    "γ",
    "δ",
    "ε",
    "ζ",
    "η",
    "θ",
    "ι",
    "κ",
    "λ",
    "μ",
    "ν",
    "ξ",
    "ο",
    "π",
    "ρ",
    "σ",
    "τ",
    "υ",
    "φ",
    "χ",
    "ψ",
    "ω",
]

_HYDROGEN_SERIES_PREFIXES: dict[int, str] = {1: "Ly", 2: "H", 3: "Pa", 4: "Br"}

_ACCURACY_PRIORITY: dict[str, int] = {
    "A": 0,
    "A+": 0,
    "A-": 1,
    "B": 2,
    "B+": 2,
    "B-": 3,
    "C": 4,
    "C+": 4,
    "C-": 5,
    "D": 6,
    "D+": 6,
    "D-": 7,
    "E": 8,
    "F": 9,
}


def extract_principal_quantum(conf: str | None) -> int | None:
    """Return the leading principal quantum number extracted from ``conf``."""
    if not conf:
        return None
    text = conf.strip()
    if not text:
        return None
    digits: list[str] = []
    for ch in text:
        if ch.isdigit():
            digits.append(ch)
        else:
            break
    if not digits:
        return None
    try:
        return int("".join(digits))
    except ValueError:
        return None


def format_hydrogen_series_label(n_lower: int, n_upper: int) -> str | None:
    """Return Lyα/Hα-style label for a pair of principal quantum numbers."""
    if n_upper <= n_lower:
        return None
    prefix = _HYDROGEN_SERIES_PREFIXES.get(n_lower)
    if not prefix:
        return None
    order_index = n_upper - n_lower - 1
    if order_index < 0:
        return None
    if order_index < len(_GREEK_SERIES_SYMBOLS):
        return f"{prefix}{_GREEK_SERIES_SYMBOLS[order_index]}"
    return f"{prefix}(n={n_upper})"


@dataclass(frozen=True)
class _HydrogenSeriesKey:
    n_lower: int
    n_upper: int


def _parse_j_value(j_text: str | None) -> float | None:
    if not j_text:
        return None
    cleaned = j_text.replace("J=", "").replace("j=", "").strip()
    if not cleaned:
        return None
    try:
        return float(Fraction(cleaned))
    except (ValueError, ZeroDivisionError):
        try:
            return float(cleaned)
        except ValueError:
            return None


def _lower_level_degeneracy(record: LineRecord) -> float | None:
    j_value = _parse_j_value(record.lower_level_j)
    if j_value is not None:
        return 2.0 * j_value + 1.0

    if record.degeneracy:
        parts = record.degeneracy.split("-")
        if parts:
            try:
                return float(parts[0].strip())
            except ValueError:
                return None
    return None


def _upper_level_degeneracy(record: LineRecord) -> float | None:
    j_value = _parse_j_value(record.upper_level_j)
    if j_value is not None:
        return 2.0 * j_value + 1.0

    if record.degeneracy:
        parts = record.degeneracy.split("-")
        if len(parts) > 1:
            try:
                return float(parts[1].strip())
            except ValueError:
                return None
    return None


def _lower_level_key(
    record: LineRecord,
) -> tuple[str | None, str | None, str | None, str | None, float | None]:
    return (
        record.lower_level_conf,
        record.lower_level_term,
        record.lower_level_j,
        record._lower_term,
        record.lower_level_energy,
    )


def _weighted_average(pairs: Sequence[tuple[LineRecord, float]], attr: str) -> float | None:
    numerator = 0.0
    weight_sum = 0.0
    for record, weight in pairs:
        value = getattr(record, attr)
        if value is None:
            continue
        numerator += weight * value
        weight_sum += weight
    if weight_sum == 0.0:
        return None
    return numerator / weight_sum


def synthesize_hydrogen_series(records: Iterable[LineRecord]) -> list[LineRecord]:
    """Aggregate resolved H I transitions into Lyα/Hα/etc. series lines.

    Args:
        records: Iterable of existing :class:`LineRecord` instances.

    Returns:
        Newly constructed :class:`LineRecord` objects representing aggregated
        series transitions. The caller is responsible for merging them with
        the original dataset.
    """
    grouped: dict[_HydrogenSeriesKey, list[LineRecord]] = defaultdict(list)
    for record in records:
        if record.element_symbol != "H" or record.charge_state != 0:
            continue

        n_lower = extract_principal_quantum(record.lower_level_conf or record._lower_term)
        n_upper = extract_principal_quantum(record.upper_level_conf or record._upper_term)
        if n_lower is None or n_upper is None or n_upper <= n_lower:
            continue

        key = _HydrogenSeriesKey(n_lower=n_lower, n_upper=n_upper)
        grouped[key].append(record)

    synthesized: list[LineRecord] = []
    for key, lines in grouped.items():
        lower_level_g: dict[
            tuple[str | None, str | None, str | None, str | None, float | None], float
        ] = {}
        upper_level_g: dict[
            tuple[str | None, str | None, str | None, str | None, float | None], float
        ] = {}
        weighted_lines: list[tuple[LineRecord, float]] = []
        for line in lines:
            f_val = line.f_value
            if f_val is None or f_val <= 0.0:
                continue
            g_val = _lower_level_degeneracy(line)
            if g_val is None or g_val <= 0.0:
                continue
            weight = g_val * f_val
            if weight <= 0.0:
                continue
            lower_key = _lower_level_key(line)
            if lower_key not in lower_level_g:
                lower_level_g[lower_key] = g_val
            upper_key = (
                line.upper_level_conf,
                line.upper_level_term,
                line.upper_level_j,
                line._upper_term,
                line.upper_level_energy,
            )
            gk_val = _upper_level_degeneracy(line)
            if gk_val is not None and gk_val > 0.0 and upper_key not in upper_level_g:
                upper_level_g[upper_key] = gk_val
            weighted_lines.append((line, weight))

        if not weighted_lines:
            continue

        total_g = sum(lower_level_g.values())
        if total_g <= 0.0:
            continue

        total_gf = sum(weight for _, weight in weighted_lines)
        if total_gf <= 0.0:
            continue

        total_gk = sum(upper_level_g.values()) if upper_level_g else None

        worst_accuracy: str | None = None
        worst_rank = -1
        for line, _ in weighted_lines:
            acc_raw = (line.accuracy or "").strip()
            if not acc_raw:
                continue
            rank = _ACCURACY_PRIORITY.get(acc_raw.upper(), 100)
            if rank > worst_rank:
                worst_accuracy = acc_raw
                worst_rank = rank

        if worst_accuracy is None:
            non_empty = [
                (line.accuracy or "").strip()
                for line, _ in weighted_lines
                if (line.accuracy or "").strip()
            ]
            if non_empty:
                worst_accuracy = sorted(non_empty)[-1]

        # Frequency-weighted mean to respect 1 / lambda relationship with (gf) weights.
        freq_numerator = 0.0
        freq_weight_sum = 0.0
        for line, weight in weighted_lines:
            wavelength_m = line.wavelength * _ANGSTROM_TO_M
            if wavelength_m <= 0.0:
                continue
            freq = _SPEED_OF_LIGHT_M_PER_S / wavelength_m
            freq_numerator += weight * freq
            freq_weight_sum += weight
        if freq_weight_sum <= 0.0:
            continue

        freq_weighted = freq_numerator / freq_weight_sum
        wavelength_weighted = _SPEED_OF_LIGHT_M_PER_S / freq_weighted / _ANGSTROM_TO_M

        f_effective = total_gf / total_g

        gamma_weighted = _weighted_average(weighted_lines, "gamma")
        gamma_upper_weighted = _weighted_average(weighted_lines, "gamma_upper")
        gamma_lower_weighted = _weighted_average(weighted_lines, "gamma_lower")
        lower_energy_weighted = _weighted_average(weighted_lines, "lower_level_energy")
        upper_energy_weighted = _weighted_average(weighted_lines, "upper_level_energy")

        transition_types = {
            line.transition_type for line, _ in weighted_lines if line.transition_type
        }
        transition_type = transition_types.pop() if len(transition_types) == 1 else None

        degeneracy_value: str | None = None
        if total_g > 0.0 and total_gk:
            gi_int = round(total_g)
            gk_int = round(total_gk)
            degeneracy_value = f"{gi_int} - {gk_int}"
        elif total_g > 0.0:
            gi_int = round(total_g)
            degeneracy_value = f"{gi_int} -"
        elif total_gk:
            gk_int = round(total_gk)
            degeneracy_value = f"- {gk_int}"

        line_name = format_hydrogen_series_label(key.n_lower, key.n_upper)
        if not line_name:
            line_name = f"H I {wavelength_weighted:.1f}"

        lower_conf = str(key.n_lower)
        upper_conf = str(key.n_upper)

        # Stable identifier derived from the synthetic config labels.
        line_id = hashed_line_id(
            element_symbol="H",
            charge_state=0,
            lower_conf=lower_conf,
            lower_term="SERIES",
            lower_j=None,
            lower_raw=lower_conf,
            upper_conf=upper_conf,
            upper_term="SERIES",
            upper_j=None,
            upper_raw=upper_conf,
        )

        # Create the aggregated hydrogen-series record.
        synthesized.append(
            LineRecord(
                line_id=line_id,
                name=line_name,
                species="H I",
                wavelength=wavelength_weighted,
                f_value=f_effective,
                gamma=gamma_weighted or 0.0,
                element_symbol="H",
                charge_state=0,
                aki_value=gamma_weighted,
                degeneracy=degeneracy_value,
                transition_type=transition_type,
                lower_level_energy=lower_energy_weighted,
                upper_level_energy=upper_energy_weighted,
                wavelength_source="aggregated",
                wavelength_ritz=wavelength_weighted,
                wavelength_ritz_unc=None,
                wavelength_observed=None,
                wavelength_observed_unc=None,
                accuracy=worst_accuracy,
                lower_level_conf=lower_conf,
                lower_level_term=None,
                lower_level_j=None,
                upper_level_conf=upper_conf,
                upper_level_term=None,
                upper_level_j=None,
                comment=(
                    f"Aggregated hydrogen series (Σgi={round(total_g)}"
                    + (f", Σgk={round(total_gk)}" if total_gk is not None else "")
                    + f"; {len(lines)} components)"
                ),
                tp_ref=None,
                line_ref=None,
                _lower_term=lower_conf,
                _upper_term=upper_conf,
                gamma_upper=gamma_upper_weighted,
                gamma_lower=gamma_lower_weighted,
            )
        )

    return synthesized
