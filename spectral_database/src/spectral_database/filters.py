"""Spectral line filtering based on physical properties.

This module provides functions to filter LineRecord objects based on
transition type, energy level, and oscillator strength criteria.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from spectral_database.data_models import LineRecord
from spectral_database.identifiers import hashed_line_id
from spectral_database.nist_client import safe_meta_get
from spectral_database.parsers import NistColumn, TableValueExtractor
from spectral_database.species import int_to_roman, roman_to_int

if TYPE_CHECKING:
    from astropy.table import Table

    from spectral_database.data_models import FilterOptions


logger = logging.getLogger(__name__)


def ion_to_charge_state(ion_str: str) -> int:
    """Convert ion string to charge state.

    Args:
        ion_str: Ion string (e.g., "Fe II", "C IV")

    Returns:
        Charge state (0=I, 1=II, ...)
    """
    # Expect formats like "Fe II", "C IV". Charge state is (roman_value - 1).
    m = re.search(r"([A-Z][a-z]?)(?:\s+([IVXLCDM]+))?", ion_str.strip())
    if not m:
        return 0
    roman = m.group(2) or "I"
    return max(roman_to_int(roman) - 1, 0)


def parse_species_from_row(
    table: Table, row_idx: int, fallback: str | None = None
) -> tuple[str, int]:
    """Parse element symbol and charge state from table row.

    Args:
        table: NIST table
        row_idx: Row index
        fallback: Fallback species string if row has no ion column

    Returns:
        Tuple of (element_symbol, charge_state)
    """
    extractor = TableValueExtractor(table)
    ion_str = extractor.extract_string(row_idx, NistColumn.ION, normalize=False)
    cand = ion_str or fallback or str(safe_meta_get(table, "species", ""))

    m = re.search(r"([A-Z][a-z]?)(?:\s+([IVXLCDM]+))?", str(cand))
    if m:
        element = m.group(1)
        charge = ion_to_charge_state(str(cand))
        return element, charge
    return "", 0


def split_level_components(level: str | None) -> tuple[str | None, str | None, str | None]:
    """Split NIST level string into configuration, term, and J.

    NIST uses pipe-separated format: "conf|term|J"

    Args:
        level: NIST level string (e.g., "1s2 2s|2S|1/2")

    Returns:
        Tuple of (conf, term, j)
    """
    text = (level or "").strip()
    if not text or text in {"--", "-"}:
        return None, None, None
    parts = [part.strip() for part in text.split("|")]
    # Pad to length 3
    while len(parts) < 3:
        parts.append("")
    conf = parts[0] or None
    term = parts[1] or None
    j = parts[2] or None
    return conf, term, j


def build_line_id(  # noqa: PLR0913
    element: str,
    charge: int,
    lower_conf: str | None,
    lower_term: str | None,
    lower_j: str | None,
    lower_raw: str | None,
    upper_conf: str | None,
    upper_term: str | None,
    upper_j: str | None,
    upper_raw: str | None,
) -> str:
    """Build a stable line ID mirroring ``multiplet_id`` formatting.

    Returns the first 16 hexadecimal characters of a SHA-256 hash computed
    from a canonical transition description. The canonical string depends on
    normalized level data and excludes wavelength so future NIST updates keep
    the identifier unchanged.
    """
    return hashed_line_id(
        element_symbol=element,
        charge_state=charge,
        lower_conf=lower_conf,
        lower_term=lower_term,
        lower_j=lower_j,
        lower_raw=lower_raw,
        upper_conf=upper_conf,
        upper_term=upper_term,
        upper_j=upper_j,
        upper_raw=upper_raw,
    )


def to_records(
    table: Table,
    filters: FilterOptions | None = None,
    level_totals: dict[_LevelKey, float] | None = None,
) -> list[LineRecord]:
    """Convert NIST table to LineRecord objects with filtering.

    Args:
        table: NIST table from astroquery
        filters: Optional filter criteria
        level_totals: Optional precomputed level totals for gamma_upper/lower

    Returns:
        List of LineRecord objects that pass filters
    """
    extractor = TableValueExtractor(table)

    records: list[LineRecord] = []
    record_keys: list[tuple[LineRecord, _LevelKey | None, _LevelKey | None, float]] = []
    totals = level_totals if level_totals is not None else {}
    should_accumulate_totals = level_totals is None
    trace = bool(safe_meta_get(table, "_trace", False))
    trace_limit = int(safe_meta_get(table, "_trace_limit", 0) or 0)
    traced = 0

    for i in range(len(table)):
        # Extract wavelengths with uncertainties
        wl, wl_source, ritz_wl, ritz_unc, obs_wl, obs_unc = (
            extractor.extract_wavelengths_with_uncertainties(i)
        )
        if wl is None:
            if trace and traced < trace_limit:
                logger.debug(
                    "skip row: no wavelength; row=%s",
                    {c: str(table[c][i]) for c in table.colnames[:8]},
                )
                traced += 1
            continue

        # Check wavelength range from metadata
        wmin_meta = safe_meta_get(table, "wmin")
        wmax_meta = safe_meta_get(table, "wmax")
        if (wmin_meta is not None and wl < float(wmin_meta)) or (
            wmax_meta is not None and wl > float(wmax_meta)
        ):
            if trace and traced < trace_limit:
                logger.debug(
                    "skip row: wavelength %.3f outside [%.3f, %.3f]",
                    wl,
                    float(wmin_meta) if wmin_meta is not None else float("nan"),
                    float(wmax_meta) if wmax_meta is not None else float("nan"),
                )
                traced += 1
            continue

        # Extract f-value
        f_val = extractor.extract_float(i, NistColumn.F_VALUE)
        if f_val is None or not (0.0 < f_val <= 2.0):
            if trace and traced < trace_limit:
                logger.debug("skip row: invalid f (f_val=%s); wl=%s", f_val, wl)
                traced += 1
            continue

        # Extract energy levels
        lower_energy = extractor.extract_float(i, NistColumn.EI)
        upper_energy = extractor.extract_float(i, NistColumn.EK)

        # If individual columns not found, try Ei Ek combined column
        if lower_energy is None or upper_energy is None:
            ei_from_combined, ek_from_combined = extractor.extract_ei_ek(i)
            if lower_energy is None:
                lower_energy = ei_from_combined
            if upper_energy is None:
                upper_energy = ek_from_combined

        if lower_energy is None or not math.isfinite(lower_energy):
            if trace and traced < trace_limit:
                logger.debug("skip row: missing Ei; wl=%s", wl)
                traced += 1
            continue
        if upper_energy is None or not math.isfinite(upper_energy):
            if trace and traced < trace_limit:
                logger.debug("skip row: missing Ek; wl=%s", wl)
                traced += 1
            continue

        type_raw = extractor.extract_string(i, NistColumn.TYPE, normalize=False)
        type_norm = type_raw.strip().upper()

        # Optional science filters will be applied after we accumulate level totals

        # Extract gamma/Aki
        aki_value = extractor.extract_float(i, NistColumn.AKI)
        if aki_value is None or not math.isfinite(aki_value):
            if trace and traced < trace_limit:
                logger.debug("skip row: missing Aki; wl=%s", wl)
                traced += 1
            continue

        # Parse species
        species_meta = str(safe_meta_get(table, "species", "") or "")
        element, charge = parse_species_from_row(table, i, species_meta)
        if not element:
            continue

        lower = extractor.extract_string(i, NistColumn.LOWER_LEVEL, normalize=False)
        upper = extractor.extract_string(i, NistColumn.UPPER_LEVEL, normalize=False)
        lower_conf, lower_term_txt, lower_j = split_level_components(lower or None)
        upper_conf, upper_term_txt, upper_j = split_level_components(upper or None)

        upper_key = _build_level_key(
            element=element,
            charge=charge,
            conf=upper_conf,
            term=upper_term_txt,
            j=upper_j,
            raw=upper,
            energy=upper_energy,
        )
        if should_accumulate_totals and upper_key is not None:
            totals[upper_key] = totals.get(upper_key, 0.0) + aki_value

        lower_key = _build_level_key(
            element=element,
            charge=charge,
            conf=lower_conf,
            term=lower_term_txt,
            j=lower_j,
            raw=lower,
            energy=lower_energy,
        )

        is_principal_only = (
            (upper_conf or "").strip().isdigit() and not upper_term_txt and not upper_j
        )
        is_hydrogen_principal_only = element == "H" and charge == 0 and is_principal_only

        if is_hydrogen_principal_only:
            if trace and traced < trace_limit:
                logger.debug("skip row: principal-only hydrogen transition; wl=%s", wl)
                traced += 1
            continue

        if not (filters and filters.include_principal_only_levels) and is_principal_only:
            if trace and traced < trace_limit:
                logger.debug("skip row: principal quantum only; wl=%s", wl)
                traced += 1
            continue

        if filters is not None:
            # Transition type filter
            if filters.allowed_types:
                ty = type_norm
                is_missing = ty in {"", "--", "—"}
                wants_e1_only = filters.allowed_types == {"E1"}
                if is_missing and wants_e1_only and filters.assume_e1_when_missing:
                    pass  # treat as E1
                elif not any(t in ty for t in filters.allowed_types):
                    if trace and traced < trace_limit:
                        logger.debug(
                            "skip row: type %s not in %s", ty, sorted(filters.allowed_types)
                        )
                        traced += 1
                    continue

            # Lower-level energy filter
            if filters.max_ei_ev is not None:
                ei = lower_energy
                if ei is None:
                    if filters.strict_ei:
                        continue
                elif ei > float(filters.max_ei_ev):
                    if trace and traced < trace_limit:
                        logger.debug(
                            "skip row: Ei %.1f eV > max_ei %.1f eV", ei, float(filters.max_ei_ev)
                        )
                        traced += 1
                    continue

            # Minimum oscillator strength filter
            if filters.min_f is not None and not (f_val >= float(filters.min_f)):
                if trace and traced < trace_limit:
                    logger.debug("skip row: f %.3g < min_f %.3g", f_val, float(filters.min_f))
                    traced += 1
                continue

        lower_group = " ".join(part for part in (lower_conf, lower_term_txt, lower_j) if part)
        upper_group = " ".join(part for part in (upper_conf, upper_term_txt, upper_j) if part)
        line_id = build_line_id(
            element=element,
            charge=charge,
            lower_conf=lower_conf,
            lower_term=lower_term_txt,
            lower_j=lower_j,
            lower_raw=lower,
            upper_conf=upper_conf,
            upper_term=upper_term_txt,
            upper_j=upper_j,
            upper_raw=upper,
        )
        ion_roman = int_to_roman(charge + 1)
        name = f"{element} {ion_roman} {wl:.1f}"
        species = f"{element} {ion_roman}"

        degeneracy = extractor.extract_string(i, NistColumn.GI_GK)
        degeneracy = _normalize_gi_gk(degeneracy)

        accuracy = extractor.extract_string(i, NistColumn.ACCURACY) or None

        # Extract TP and LINE reference codes
        tp_code, line_code = extractor.extract_ref_codes(i)

        record = LineRecord(
            line_id=line_id,
            name=name,
            species=species,
            wavelength=wl,
            f_value=f_val,
            gamma=aki_value,
            gamma_upper=None,
            gamma_lower=None,
            aki_value=aki_value,
            element_symbol=element,
            charge_state=charge,
            degeneracy=degeneracy,
            transition_type=type_norm or None,
            lower_level_energy=lower_energy,
            upper_level_energy=upper_energy,
            wavelength_source=wl_source,
            wavelength_ritz=ritz_wl,
            wavelength_ritz_unc=ritz_unc,
            wavelength_observed=obs_wl,
            wavelength_observed_unc=obs_unc,
            accuracy=accuracy,
            lower_level_conf=lower_conf,
            lower_level_term=lower_term_txt,
            lower_level_j=lower_j,
            upper_level_conf=upper_conf,
            upper_level_term=upper_term_txt,
            upper_level_j=upper_j,
            comment="",
            tp_ref=tp_code or None,
            line_ref=line_code or None,
            _lower_term=lower_group or (lower or None),
            _upper_term=upper_group or (upper or None),
        )

        record_keys.append((record, upper_key, lower_key, aki_value))

    for record, upper_key, lower_key, aki_value in record_keys:
        gamma_upper = aki_value
        if upper_key is not None:
            gamma_upper = totals.get(upper_key, gamma_upper)

        gamma_lower = 0.0
        if lower_key is not None and lower_key != upper_key:
            gamma_lower = totals.get(lower_key, 0.0)

        record.gamma_upper = gamma_upper
        record.gamma_lower = gamma_lower
        record.gamma = gamma_upper + gamma_lower
        records.append(record)

    return records


def _normalize_gi_gk(value: str | None) -> str | None:
    """Normalize degeneracy string.

    Args:
        value: Raw degeneracy string

    Returns:
        Normalized string or None
    """
    if not value:
        return None
    text = value.strip()
    if not text or text in {"--", "-", "—"}:
        return None
    return re.sub(r"\s+", " ", text)


@dataclass(frozen=True)
class _LevelKey:
    element: str
    charge: int
    conf: str | None
    term: str | None
    j: str | None
    raw: str | None
    energy: float | None


def _normalize_level_field(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    if not text or text in {"--", "-", "—"}:
        return None
    return re.sub(r"\s+", " ", text)


def _build_level_key(
    element: str,
    charge: int,
    conf: str | None,
    term: str | None,
    j: str | None,
    raw: str | None,
    energy: float | None,
) -> _LevelKey | None:
    element_norm = element.strip().upper()
    conf_norm = _normalize_level_field(conf)
    term_norm = _normalize_level_field(term)
    j_norm = _normalize_level_field(j)
    raw_norm = _normalize_level_field(raw)
    energy_norm: float | None = None
    if energy is not None and math.isfinite(energy):
        energy_norm = round(float(energy), 8)

    if not any((conf_norm, term_norm, j_norm, raw_norm, energy_norm is not None)):
        return None

    return _LevelKey(
        element=element_norm,
        charge=charge,
        conf=conf_norm,
        term=term_norm,
        j=j_norm,
        raw=raw_norm,
        energy=energy_norm,
    )


def collect_level_decay_totals(tables: list[Table]) -> dict[_LevelKey, float]:
    """Aggregate Einstein A coefficients per upper level across tables.

    Args:
        tables: NIST tables (unfiltered) used to build totals

    Returns:
        Mapping of level keys to summed Aki values.
    """
    totals: dict[_LevelKey, float] = {}
    for table in tables:
        extractor = TableValueExtractor(table)
        species_meta = str(safe_meta_get(table, "species", "") or "")

        for i in range(len(table)):
            aki_value = extractor.extract_float(i, NistColumn.AKI)
            if aki_value is None or not math.isfinite(aki_value):
                continue

            element, charge = parse_species_from_row(table, i, species_meta)
            if not element:
                continue

            upper_energy = extractor.extract_float(i, NistColumn.EK)
            if upper_energy is None or not math.isfinite(upper_energy):
                _, alt_ek = extractor.extract_ei_ek(i)
                if upper_energy is None:
                    upper_energy = alt_ek

            upper = extractor.extract_string(i, NistColumn.UPPER_LEVEL, normalize=False)
            upper_conf, upper_term_txt, upper_j = split_level_components(upper or None)

            upper_key = _build_level_key(
                element=element,
                charge=charge,
                conf=upper_conf,
                term=upper_term_txt,
                j=upper_j,
                raw=upper,
                energy=upper_energy,
            )
            if upper_key is None:
                continue

            totals[upper_key] = totals.get(upper_key, 0.0) + float(aki_value)

    return totals
