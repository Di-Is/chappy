"""Tests for the value-with-error uncertainty rounding pure function."""

from __future__ import annotations

import math

import pytest

from chappy.gui.modes.analysis.region_detail.tree.uncertainty_format import format_value_with_error


@pytest.mark.parametrize(
    ("value", "error", "fallback_spec", "expected"),
    [
        (2.3456789012, 1.2e-6, "{:.5f}", "2.3456789 ± 0.0000012"),
        (2.3456789012, 1.23e-4, "{:.5f}", "2.34568 ± 0.00012"),
        (13.512, 0.45, "{:.1f}", "13.51 ± 0.45"),
        (45.21, 1.3, "{:.1f}", "45.2 ± 1.3"),
        (45.21, 13.4, "{:.1f}", "45 ± 13"),
        (4567.0, 130.0, "{:.1f}", "4567 ± 130"),
        (2.3456789012, None, "{:.5f}", "2.34568"),
        (2.3456789012, float("nan"), "{:.5f}", "2.34568"),
        (2.3456789012, 0.0, "{:.5f}", "2.34568"),
        (0.9996, 0.0996, "{:.3f}", "1.00 ± 0.10"),
    ],
)
def test_format_value_with_error(
    value: float, error: float | None, fallback_spec: str, expected: str
) -> None:
    """format_value_with_error should match the expected rounding for each case."""
    assert format_value_with_error(value, error, fallback_spec) == expected


def test_format_value_with_error_treats_negative_error_as_fallback() -> None:
    """A negative error is invalid and should fall back to plain value formatting."""
    assert format_value_with_error(2.3456789012, -1.0, "{:.5f}") == "2.34568"


def test_format_value_with_error_treats_infinite_error_as_fallback() -> None:
    """A non-finite (infinite) error should fall back to plain value formatting."""
    assert format_value_with_error(2.3456789012, math.inf, "{:.5f}") == "2.34568"
