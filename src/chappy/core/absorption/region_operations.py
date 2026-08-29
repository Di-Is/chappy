"""Operations on absorption region and line collections."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion


def collect_lines_for_region(
    regions: Mapping[str, AbsorptionRegion], lines: Mapping[str, AbsorptionLine], region_id: str
) -> list[AbsorptionLine]:
    """Return all existing absorption lines assigned to a region.

    Args:
        regions: Absorption regions keyed by region ID.
        lines: Absorption lines keyed by line ID.
        region_id: Region identifier.

    Returns:
        Existing absorption lines in region order.
    """
    region = regions.get(region_id)
    if region is None:
        return []
    return [line for line_id in region.line_ids if (line := lines.get(line_id)) is not None]


def is_region_needs_optimization(
    regions: Mapping[str, AbsorptionRegion], lines: Mapping[str, AbsorptionLine], region_id: str
) -> bool:
    """Return whether any line in a region needs optimization.

    Args:
        regions: Absorption regions keyed by region ID.
        lines: Absorption lines keyed by line ID.
        region_id: Region identifier.

    Returns:
        True when at least one existing region line needs optimization.
    """
    return any(
        line.needs_optimization for line in collect_lines_for_region(regions, lines, region_id)
    )


def set_region_needs_optimization(
    regions: Mapping[str, AbsorptionRegion],
    lines: Mapping[str, AbsorptionLine],
    region_id: str,
    *,
    needs_optimization: bool,
) -> int:
    """Set optimization-needed state for every existing line in a region.

    Args:
        regions: Absorption regions keyed by region ID.
        lines: Absorption lines keyed by line ID.
        region_id: Region identifier.
        needs_optimization: Target optimization-needed state.

    Returns:
        Number of line flags that changed.
    """
    updated = 0
    for line in collect_lines_for_region(regions, lines, region_id):
        if line.needs_optimization == needs_optimization:
            continue
        line.needs_optimization = needs_optimization
        updated += 1
    return updated
