"""Tests for region sorting utility."""

from __future__ import annotations

import pytest

from chappy.core.absorption.models import AbsorptionRegion
from chappy.gui.utils.region_sorting import sort_regions_for_display


class TestSortRegionsForDisplay:
    """Tests for sort_regions_for_display function."""

    def test_empty_list_returns_empty(self) -> None:
        """Empty input returns empty output."""
        result = sort_regions_for_display([])
        assert result == []

    def test_single_region_returns_same(self) -> None:
        """Single region is returned as-is."""
        region = AbsorptionRegion(region_id="r1", analysis_range=(1000.0, 1100.0))
        result = sort_regions_for_display([("r1", region)])
        assert len(result) == 1
        assert result[0][0] == "r1"

    def test_sorts_by_left_edge_wavelength(self) -> None:
        """Regions are sorted by left edge (analysis_range[0]) ascending."""
        region_a = AbsorptionRegion(region_id="a", analysis_range=(3000.0, 3100.0))
        region_b = AbsorptionRegion(region_id="b", analysis_range=(1000.0, 1100.0))
        region_c = AbsorptionRegion(region_id="c", analysis_range=(2000.0, 2100.0))

        # Input in non-sorted order
        input_regions = [("a", region_a), ("b", region_b), ("c", region_c)]
        result = sort_regions_for_display(input_regions)

        # Expected order: B (1000), C (2000), A (3000)
        assert [r[0] for r in result] == ["b", "c", "a"]

    def test_same_left_edge_sorts_by_right_edge(self) -> None:
        """When left edges are equal, sort by right edge."""
        region_a = AbsorptionRegion(region_id="a", analysis_range=(1000.0, 1200.0))
        region_b = AbsorptionRegion(region_id="b", analysis_range=(1000.0, 1100.0))

        input_regions = [("a", region_a), ("b", region_b)]
        result = sort_regions_for_display(input_regions)

        # Expected order: B (right=1100), A (right=1200)
        assert [r[0] for r in result] == ["b", "a"]

    def test_same_range_sorts_by_region_id(self) -> None:
        """When ranges are identical, sort by region_id for stability."""
        region_a = AbsorptionRegion(region_id="zzz", analysis_range=(1000.0, 1100.0))
        region_b = AbsorptionRegion(region_id="aaa", analysis_range=(1000.0, 1100.0))

        input_regions = [("zzz", region_a), ("aaa", region_b)]
        result = sort_regions_for_display(input_regions)

        # Expected order: aaa, zzz (alphabetical)
        assert [r[0] for r in result] == ["aaa", "zzz"]

    def test_none_analysis_range_placed_at_end(self) -> None:
        """Regions with None analysis_range are placed at the end."""
        region_a = AbsorptionRegion(region_id="a", analysis_range=None)
        region_b = AbsorptionRegion(region_id="b", analysis_range=(1000.0, 1100.0))
        region_c = AbsorptionRegion(region_id="c", analysis_range=None)

        input_regions = [("a", region_a), ("b", region_b), ("c", region_c)]
        result = sort_regions_for_display(input_regions)

        # Expected order: B (has range), A (None, id=a), C (None, id=c)
        assert [r[0] for r in result] == ["b", "a", "c"]

    def test_multiple_none_sorted_by_region_id(self) -> None:
        """Multiple None regions are sorted by region_id."""
        region_a = AbsorptionRegion(region_id="z_region", analysis_range=None)
        region_b = AbsorptionRegion(region_id="a_region", analysis_range=None)

        input_regions = [("z_region", region_a), ("a_region", region_b)]
        result = sort_regions_for_display(input_regions)

        # Expected order: a_region, z_region (alphabetical)
        assert [r[0] for r in result] == ["a_region", "z_region"]

    def test_does_not_mutate_input(self) -> None:
        """Input list is not mutated."""
        region_a = AbsorptionRegion(region_id="a", analysis_range=(2000.0, 2100.0))
        region_b = AbsorptionRegion(region_id="b", analysis_range=(1000.0, 1100.0))

        input_regions = [("a", region_a), ("b", region_b)]
        original_order = [("a", region_a), ("b", region_b)]

        sort_regions_for_display(input_regions)

        # Input should be unchanged
        assert [r[0] for r in input_regions] == [r[0] for r in original_order]
