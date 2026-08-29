"""Tests for absorption region operation helpers."""

from __future__ import annotations

from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.absorption.region_operations import (
    collect_lines_for_region,
    is_region_needs_optimization,
    set_region_needs_optimization,
)


def _make_line(line_id: str, *, needs_optimization: bool = False) -> AbsorptionLine:
    """Create an absorption line for region operation tests."""
    return AbsorptionLine(
        line_id=line_id,
        species="H I",
        rest_wavelength=1215.67,
        center_z=1.0,
        window_kms=150.0,
        multiplet_label="",
        transition_name="Ly alpha",
        oscillator_strength=0.416,
        gamma_value=6.27e8,
        needs_optimization=needs_optimization,
    )


def test_collect_lines_for_region_skips_missing_lines() -> None:
    """Region line lookup should preserve order and skip stale line IDs."""
    regions = {"region-1": AbsorptionRegion(region_id="region-1", line_ids=["a", "missing", "b"])}
    lines = {"a": _make_line("a"), "b": _make_line("b")}

    result = collect_lines_for_region(regions, lines, "region-1")

    assert [line.line_id for line in result] == ["a", "b"]


def test_set_region_needs_optimization_counts_changed_lines() -> None:
    """Setting region optimization state should update only changed lines."""
    regions = {"region-1": AbsorptionRegion(region_id="region-1", line_ids=["a", "b"])}
    lines = {
        "a": _make_line("a", needs_optimization=False),
        "b": _make_line("b", needs_optimization=True),
    }

    updated = set_region_needs_optimization(regions, lines, "region-1", needs_optimization=True)

    assert updated == 1
    assert is_region_needs_optimization(regions, lines, "region-1") is True
    assert lines["a"].needs_optimization is True
    assert lines["b"].needs_optimization is True
