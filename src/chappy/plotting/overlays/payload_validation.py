"""Validation helpers for plotting overlay payloads."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, SupportsFloat

from chappy.presentation.spectrum import AbsorptionMarkerInput

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from chappy.plotting.overlays import AbsorptionLineRegion


def validate_absorption_marker_input(marker: AbsorptionMarkerInput) -> AbsorptionMarkerInput:
    """Return a sanitized absorption marker payload."""
    return AbsorptionMarkerInput(
        name=require_marker_name(marker.name),
        rest_wavelength=require_marker_float(marker.rest_wavelength, "rest_wavelength"),
        redshift=require_marker_float(marker.redshift, "redshift"),
        column_density=require_marker_float(marker.column_density, "column_density"),
        b_parameter=require_marker_float(marker.b_parameter, "b_parameter"),
        oscillator_strength=require_marker_float(
            marker.oscillator_strength, "oscillator_strength"
        ),
        gamma=require_marker_float(marker.gamma, "gamma"),
        component_id=marker.component_id,
        tie_label=marker.tie_label,
        color=marker.color,
    )


def require_marker_name(value: str) -> str:
    """Return a non-empty marker name."""
    if not isinstance(value, str) or not value:
        msg = "Absorption marker name is required."
        raise ValueError(msg)
    return value


def require_marker_float(value: object, field: str) -> float:
    """Return a finite marker float value."""
    return _require_finite_float(
        value,
        numeric_message=f"Absorption marker field '{field}' must be numeric.",
        finite_message=f"Absorption marker field '{field}' must be finite.",
    )


def validate_absorption_line_regions(regions: Sequence[AbsorptionLineRegion]) -> None:
    """Validate absorption-line region payloads."""
    for index, region in enumerate(regions, start=1):
        _validate_absorption_line_region_bounds(region, index=index)


def _validate_absorption_line_region_bounds(region: Mapping[str, object], *, index: int) -> None:
    """Validate required numeric bounds for one absorption line region."""
    if "lambda_start" not in region or "lambda_end" not in region:
        msg = f"Absorption line region #{index} requires both 'lambda_start' and 'lambda_end'."
        raise ValueError(msg)

    lambda_start = require_region_float(region["lambda_start"], "lambda_start", index=index)
    lambda_end = require_region_float(region["lambda_end"], "lambda_end", index=index)

    if lambda_start >= lambda_end:
        msg = f"Absorption line region #{index} requires lambda_start < lambda_end."
        raise ValueError(msg)


def require_region_float(value: object, field: str, *, index: int) -> float:
    """Convert and validate a finite region boundary value."""
    return _require_finite_float(
        value,
        numeric_message=f"Absorption line region #{index} field '{field}' must be a finite number.",
        finite_message=f"Absorption line region #{index} field '{field}' must be finite.",
    )


def _require_finite_float(value: object, *, numeric_message: str, finite_message: str) -> float:
    """Return a finite float from a marker or region payload field."""
    if isinstance(value, bool):
        raise TypeError(numeric_message)
    if not isinstance(value, str | SupportsFloat):
        raise TypeError(numeric_message)
    try:
        converted = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(numeric_message) from exc
    if not math.isfinite(converted):
        raise ValueError(finite_message)
    return converted
