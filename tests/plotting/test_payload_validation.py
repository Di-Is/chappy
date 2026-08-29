"""Unit tests for plotting overlay payload validation helpers."""

from __future__ import annotations

import pytest

from chappy.plotting.overlays.payload_validation import (
    require_marker_float,
    validate_absorption_line_regions,
    validate_absorption_marker_input,
)
from chappy.presentation.spectrum import AbsorptionMarkerInput


def test_validate_absorption_marker_input_preserves_valid_values() -> None:
    """Valid marker payloads should survive validation unchanged."""
    marker = AbsorptionMarkerInput(
        name="Lya",
        rest_wavelength=1215.67,
        redshift=2.0,
        column_density=14.0,
        b_parameter=20.0,
        oscillator_strength=0.4164,
        gamma=6.265e8,
    )

    validated = validate_absorption_marker_input(marker)

    assert validated == marker


@pytest.mark.parametrize("value", [True, False, float("nan"), float("inf"), object()])
def test_require_marker_float_rejects_non_finite_and_non_numeric_values(value: object) -> None:
    """Marker float validation should reject bools, infinities, NaN, and arbitrary objects."""
    with pytest.raises((TypeError, ValueError)):
        require_marker_float(value, "redshift")


def test_validate_absorption_line_regions_rejects_missing_and_invalid_bounds() -> None:
    """Region validation should reject malformed numeric boundaries."""
    with pytest.raises(ValueError, match="requires both"):
        validate_absorption_line_regions([{"label": "LyA"}])

    with pytest.raises(ValueError, match="must be finite"):
        validate_absorption_line_regions([{"lambda_start": 1000.0, "lambda_end": float("nan")}])

    with pytest.raises(ValueError, match="lambda_start < lambda_end"):
        validate_absorption_line_regions([{"lambda_start": 1100.0, "lambda_end": 1000.0}])
