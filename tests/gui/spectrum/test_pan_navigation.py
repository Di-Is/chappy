"""Tests for pan-specific navigation helpers."""

from __future__ import annotations

import pytest

from chappy.application.spectrum.range_usecase import calculate_pan_range


def test_pan_without_bounds_preserves_fractional_shift() -> None:
    """It should shift the range by the requested fraction when no bounds exist."""
    result = calculate_pan_range((1000.0, 2000.0), 0.1)
    assert result == pytest.approx((1100.0, 2100.0))


def test_pan_clamps_to_left_bound_and_preserves_span() -> None:
    """It should stop at the lower bound without shrinking the span."""
    result = calculate_pan_range((1000.0, 2000.0), -0.2, bounds=(900.0, 2500.0))
    assert result == pytest.approx((900.0, 1900.0))


def test_pan_clamps_to_right_bound_and_preserves_span() -> None:
    """It should stop at the upper bound without shrinking the span."""
    result = calculate_pan_range((1000.0, 2000.0), 0.75, bounds=(900.0, 2500.0))
    assert result == pytest.approx((1500.0, 2500.0))


def test_pan_returns_bounds_when_span_exceeds_data() -> None:
    """It should fallback to the data bounds when the view span exceeds data coverage."""
    result = calculate_pan_range((900.0, 2500.0), 0.5, bounds=(1000.0, 2000.0))
    assert result == pytest.approx((1000.0, 2000.0))
