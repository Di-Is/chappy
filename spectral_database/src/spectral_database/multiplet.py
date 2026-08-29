"""Multiplet detection and grouping based on spec.md.

This module implements the absorption multiplet detection algorithm
described in docs/spec.md, grouping transitions by lower level and
upper LS term (J-independent).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from spectral_database.data_models import LineRecord


from spectral_database.identifiers import (
    normalize_configuration,
    normalize_j,
    normalize_term,
    truncate_sha256,
)
from spectral_database.species import int_to_roman


def build_absorption_multiplet_id(record: LineRecord) -> str | None:
    """Build absorption multiplet ID as per spec.md §5.3.

    Format: "{Species}|{lower_conf}|{lower_term}|J={lower_J} -> {upper_conf}|{upper_term_LS}"

    Args:
        record: LineRecord with level information

    Returns:
        Multiplet ID string or None if essential fields missing
    """
    species = record.species
    lower_conf = normalize_configuration(record.lower_level_conf)
    lower_term = normalize_term(record.lower_level_term)
    lower_j = normalize_j(record.lower_level_j)
    upper_conf = normalize_configuration(record.upper_level_conf)
    upper_term_ls = record.upper_term_ls  # Should be pre-computed

    # All fields required for absorption multiplet ID
    if not all([species, lower_conf, lower_term, lower_j, upper_conf, upper_term_ls]):
        return None

    return f"{species}|{lower_conf}|{lower_term}|J={lower_j} -> {upper_conf}|{upper_term_ls}"


def assign_multiplet_ids(records: list[LineRecord]) -> None:
    """Assign absorption_multiplet_id to each record.

    Also pre-computes upper_term_ls field. Records that already have an
    absorption_multiplet_id set (e.g., synthesized hydrogen series multiplets)
    are preserved.

    Args:
        records: List of LineRecord objects (modified in-place)
    """
    for record in records:
        # Pre-compute upper_term_ls (normalized LS term)
        record.upper_term_ls = normalize_term(record.upper_level_term)

        # Preserve existing absorption_multiplet_id if already set
        if record.absorption_multiplet_id is not None:
            continue

        # Assign multiplet IDs based on level information
        record.absorption_multiplet_id = build_absorption_multiplet_id(record)
        # Reset mutiplet label; populated later only for true multiplets
        record.mutiplet_name = None


@dataclass(frozen=True)
class MultipletMetrics:
    """Per-line multiplet statistics computed from absorption_multiplet_id."""

    n_components: int
    component_index: int


def calculate_multiplet_metrics(records: list[LineRecord]) -> dict[int, MultipletMetrics]:
    """Calculate multiplet-derived quantities without mutating line fields.

    Computes group statistics (n_components, component_index) and returns them
    keyed by record id for downstream consumption. Mutiplet labels remain
    denormalized here because GUI/CSV consumers still need them.

    Args:
        records: List of LineRecord objects (mutiplet_name updated in-place)

    Returns:
        Mapping of ``id(record)`` to :class:`MultipletMetrics`.
    """
    metrics: dict[int, MultipletMetrics] = {}

    # Group records by absorption_multiplet_id
    groups: dict[str, list[LineRecord]] = defaultdict(list)
    for record in records:
        if record.absorption_multiplet_id:
            groups[record.absorption_multiplet_id].append(record)

    for indices in groups.values():
        n_components = len(indices)

        # Sort records by wavelength for component_index assignment
        group_sorted = sorted(indices, key=lambda rec: rec.wavelength)

        if n_components <= 1:
            for record in group_sorted:
                record.mutiplet_name = None
            continue

        for component_idx, record in enumerate(group_sorted, start=1):
            metrics[id(record)] = MultipletMetrics(
                n_components=n_components, component_index=component_idx
            )

        first_record = group_sorted[0]
        ion_roman = int_to_roman(first_record.charge_state + 1)
        prefix = f"{first_record.element_symbol} {ion_roman}"
        wavelengths = [str(round(record.wavelength)) for record in group_sorted]
        mutiplet_label = f"{prefix} {'/'.join(wavelengths)}"
        for record in group_sorted:
            record.mutiplet_name = mutiplet_label

    return metrics


def compute_multiplet_id(
    records: list[LineRecord], metrics_map: dict[int, MultipletMetrics]
) -> None:
    """Compute multiplet identification hash for absorption_multiplet_id as per spec.md §5.3.

    Uses SHA-256 hash of canonical multiplet ID.

    Args:
        records: List of LineRecord objects (modified in-place)
        metrics_map: Metrics keyed by ``id(record)`` for true multiplets only
    """
    for record in records:
        if not record.absorption_multiplet_id:
            record.multiplet_id = None
            continue

        metrics = metrics_map.get(id(record))
        if metrics is None:
            record.multiplet_id = None
            continue

        canonical = record.absorption_multiplet_id
        record.multiplet_id = truncate_sha256(canonical)


def process_multiplets(records: list[LineRecord]) -> dict[int, MultipletMetrics]:
    """Full multiplet processing pipeline.

    Executes:
    1. Assign multiplet IDs
    2. Calculate metrics (n_components, component_index)
    3. Compute multiplet identification hashes

    Args:
        records: List of LineRecord objects (modified in-place)
    """
    assign_multiplet_ids(records)
    metrics = calculate_multiplet_metrics(records)
    compute_multiplet_id(records, metrics)
    return metrics
