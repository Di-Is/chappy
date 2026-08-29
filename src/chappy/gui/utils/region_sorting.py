"""Region sorting utilities for display purposes."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from chappy.core.absorption.models import AbsorptionRegion


def sort_regions_for_display(
    regions: Sequence[tuple[str, AbsorptionRegion]],
) -> list[tuple[str, AbsorptionRegion]]:
    """Sort absorption regions by wavelength for consistent display order.

    Regions are sorted by:
    1. analysis_range[0] (left edge wavelength, ascending)
    2. analysis_range[1] (right edge wavelength, ascending) - for tie-breaking
    3. region_id (ascending) - for stable ordering

    Regions with None analysis_range are placed at the end.

    Args:
        regions: Sequence of (region_id, AbsorptionRegion) tuples to sort.

    Returns:
        A new list containing the regions in sorted order.
        The input sequence is not modified.
    """

    def sort_key(item: tuple[str, AbsorptionRegion]) -> tuple[float, float, str]:
        region_id, region = item
        if region.analysis_range is None:
            return (float("inf"), float("inf"), region_id)
        return (region.analysis_range[0], region.analysis_range[1], region_id)

    return sorted(regions, key=sort_key)
