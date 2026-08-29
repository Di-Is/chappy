"""Tests for canonical scientific velocity-range values."""

import pytest

from chappy.core.velocity_ranges import LineAnalysisHalfWidth


@pytest.mark.parametrize("value", [10.0, 200.0, 2000.0])
def test_line_analysis_half_width_accepts_supported_values(value: float) -> None:
    """Supported finite values should remain unchanged."""
    assert LineAnalysisHalfWidth(value).kms == value


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 9.9, 2000.1, -200.0])
def test_line_analysis_half_width_rejects_invalid_values(value: float) -> None:
    """Scientific values should never be silently clamped or sign-normalized."""
    with pytest.raises(ValueError):
        LineAnalysisHalfWidth(value)
