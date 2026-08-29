"""CSV export for spectral line database.

This module handles writing LineRecord objects to CSV format
following the schema defined in spec.md §8.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

    from spectral_database.data_models import LineRecord

from spectral_database.multiplet import MultipletMetrics, calculate_multiplet_metrics


def _fmt_float(value: float | None, precision: int = 6) -> str:
    """Format float value for CSV export.

    Args:
        value: Float value or None
        precision: Decimal precision

    Returns:
        Formatted string or empty string if None/invalid
    """
    if value is None or not math.isfinite(value):
        return ""
    return f"{value:.{precision}f}"


def _fmt_sci(value: float | None, precision: int = 6) -> str:
    """Format float value in scientific notation.

    Args:
        value: Float value or None
        precision: Significant figures

    Returns:
        Formatted string or empty string if None/invalid
    """
    if value is None or not math.isfinite(value):
        return ""
    return f"{value:.{precision}g}"


def _fmt_int(value: int | None) -> str:
    """Format integer for CSV.

    Args:
        value: Integer value or None

    Returns:
        String representation or empty string
    """
    if value is None:
        return ""
    return str(value)


def _build_sort_key(
    species_order: Mapping[str, int] | None,
) -> Callable[[LineRecord], tuple[int, str, float, float]]:
    """Return a sort-key function honoring an optional species order."""
    if species_order:
        normalized = {key.lower(): value for key, value in species_order.items()}
        fallback_priority = max(normalized.values(), default=-1) + 1
    else:
        normalized = None
        fallback_priority = 0

    def sort_key(record: LineRecord) -> tuple[int, str, float, float]:
        priority = fallback_priority
        if normalized is not None:
            species_key = (record.species or "").lower()
            element_key = (record.element_symbol or "").lower()
            for key in (species_key, element_key):
                if key and key in normalized:
                    priority = normalized[key]
                    break

        element = record.element_symbol or ""
        charge = float(record.charge_state) if record.charge_state is not None else math.inf
        wavelength = (
            record.wavelength
            if record.wavelength is not None and math.isfinite(record.wavelength)
            else math.inf
        )
        return (priority, element, charge, float(wavelength))

    return sort_key


def write_csv(  # noqa: PLR0913
    path: Path | str,
    records: Iterable[LineRecord],
    meta_name: str | None = None,
    meta_version: str | None = None,
    *,
    include_absorption_multiplet_id: bool = False,
    include_gi_gk: bool = False,
    include_gamma_components: bool = False,
    include_aki: bool = False,
    multiplet_metrics: Mapping[int, MultipletMetrics] | None = None,
    species_order: Mapping[str, int] | None = None,
) -> None:
    """Write LineRecord objects to CSV file.

    Implements spec.md §8 CSV schema with all required and optional columns.

    Args:
        path: Output CSV file path
        records: Iterable of LineRecord objects
        meta_name: Optional metadata name (written as comment)
        meta_version: Optional metadata version (written as comment)
        include_absorption_multiplet_id: When True, include debug-only
            absorption_multiplet_id column
        include_gi_gk: When True, include degeneracy (gi_gk) column used for
            debugging normalization
        include_gamma_components: When True, include gamma_upper/gamma_lower
            diagnostic columns directly after gamma
        include_aki: When True, include the raw Einstein Aki value used before
            aggregation (diagnostic/reference)
        multiplet_metrics: Optional precomputed statistics keyed by ``id(record)``
            so callers can avoid recomputing counts when already available
        species_order: Optional mapping that provides an ordering priority for
            species or element symbols (case-insensitive). When supplied, rows
            are sorted following this order before falling back to the default
            element/charge/wavelength sort.
    """
    output_path = Path(path)
    record_list = list(records)
    metrics_map = (
        multiplet_metrics
        if multiplet_metrics is not None
        else calculate_multiplet_metrics(record_list)
    )

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        # Write metadata comments
        if meta_name:
            handle.write(f"# name: {meta_name}\n")
        if meta_version:
            handle.write(f"# version: {meta_version}\n")

        writer = csv.writer(handle)

        # Header row - spec.md §8 schema
        required_columns = [
            "line_id",
            "name",
            "element_symbol",
            "charge_state",
            "wavelength",
            "wavelength_source",
            "wavelength_ritz",
            "f_value",
            "gamma",
        ]

        optional_columns = [
            "wavelength_ritz_unc",
            "wavelength_observed",
            "wavelength_observed_unc",
            "Ei_eV",  # Energy in eV (converted if needed)
            "Ek_eV",
            "lower_conf",
            "lower_term",
            "lower_J",
            "upper_conf",
            "upper_term",
            "upper_J",
            "upper_term_LS",
            "accuracy",
        ]

        multiplet_columns = ["multiplet_id"]
        if include_absorption_multiplet_id:
            multiplet_columns.append("absorption_multiplet_id")
        multiplet_columns.extend(["component_index", "mutiplet_name"])

        trailing_columns = ["tp_ref", "line_ref", "comment"]

        header = required_columns.copy()
        if include_gi_gk:
            insert_at = header.index("gamma") + 1
            header.insert(insert_at, "gi_gk")
        post_gamma_columns: list[str] = []
        if include_gamma_components:
            post_gamma_columns.extend(["gamma_upper", "gamma_lower"])
        if include_aki:
            post_gamma_columns.append("aki_value")
        if post_gamma_columns:
            insert_at = header.index("gamma") + 1
            for column in post_gamma_columns:
                header.insert(insert_at, column)
                insert_at += 1
        header.extend(optional_columns)
        header.extend(multiplet_columns)
        header.extend(trailing_columns)
        writer.writerow(header)

        # Data rows
        sort_key = _build_sort_key(species_order)

        for r in sorted(record_list, key=sort_key):
            # NIST queries already return energies in eV (payload en_unit=1),
            # so keep the stored values as-is for CSV output.
            ei_ev = (
                r.lower_level_energy
                if r.lower_level_energy is not None and math.isfinite(r.lower_level_energy)
                else None
            )
            ek_ev = (
                r.upper_level_energy
                if r.upper_level_energy is not None and math.isfinite(r.upper_level_energy)
                else None
            )

            row_map = {
                "line_id": r.line_id,
                "name": r.name,
                "element_symbol": r.element_symbol or "",
                "charge_state": _fmt_int(r.charge_state),
                "wavelength": _fmt_float(r.wavelength),
                "wavelength_source": r.wavelength_source or "",
                "wavelength_ritz": _fmt_float(r.wavelength_ritz),
                "f_value": _fmt_sci(r.f_value),
                "gamma": _fmt_sci(r.gamma),
                "gamma_upper": _fmt_sci(r.gamma_upper),
                "gamma_lower": _fmt_sci(r.gamma_lower),
                "aki_value": _fmt_sci(r.aki_value),
                "gi_gk": r.degeneracy or "",
                "wavelength_ritz_unc": _fmt_float(r.wavelength_ritz_unc),
                "wavelength_observed": _fmt_float(r.wavelength_observed),
                "wavelength_observed_unc": _fmt_float(r.wavelength_observed_unc),
                "Ei_eV": _fmt_float(ei_ev),
                "Ek_eV": _fmt_float(ek_ev),
                "lower_conf": r.lower_level_conf or "",
                "lower_term": r.lower_level_term or "",
                "lower_J": r.lower_level_j or "",
                "upper_conf": r.upper_level_conf or "",
                "upper_term": r.upper_level_term or "",
                "upper_J": r.upper_level_j or "",
                "upper_term_LS": r.upper_term_ls or "",
                "accuracy": r.accuracy or "",
                "component_index": "",
                "multiplet_id": r.multiplet_id or "",
                "mutiplet_name": r.mutiplet_name or "",
                "tp_ref": r.tp_ref or "",
                "line_ref": r.line_ref or "",
                "comment": r.comment or "",
            }
            if include_absorption_multiplet_id:
                row_map["absorption_multiplet_id"] = r.absorption_multiplet_id or ""
            metric = metrics_map.get(id(r)) if metrics_map is not None else None
            component_index = metric.component_index if metric else None
            row_map["component_index"] = _fmt_int(component_index)

            row = [row_map.get(column, "") for column in header]
            writer.writerow(row)
