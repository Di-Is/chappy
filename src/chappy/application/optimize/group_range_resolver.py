"""Resolve the wavelength range of an Analysis absorption region.

The resolver derives an analysis wavelength range from an absorption region
without depending on Qt or GUI state. It is given only the absorption line
lookup it needs rather than the full project document.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from chappy.core.constants import LIGHT_SPEED_KMS

if TYPE_CHECKING:
    from collections.abc import Mapping

    from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion


class OptimizeGroupRangeResolver:
    """Compute the wavelength range for an absorption region."""

    def __init__(self, absorption_lines: Mapping[str, AbsorptionLine]) -> None:
        """Initialize the resolver.

        Args:
            absorption_lines: Mapping of line id to absorption line used when a
                group range must be derived from member lines.
        """
        self._absorption_lines = absorption_lines

    def resolve(self, group: AbsorptionRegion | None) -> tuple[float, float] | None:
        """Resolve the wavelength range for the provided group object.

        Args:
            group: Absorption region.

        Returns:
            Wavelength range tuple, or ``None`` when it cannot be resolved.
        """
        if group is None:
            return None

        return self._derive_absorption_region_range(group)

    def _derive_absorption_region_range(
        self, group: AbsorptionRegion
    ) -> tuple[float, float] | None:
        """Derive a wavelength range from a region using member line bounds."""
        analysis_range = group.analysis_range
        if analysis_range is not None:
            return self._validate_range_pair(
                analysis_range, context=f"absorption region '{group.region_id}' analysis_range"
            )
        line_ids = tuple(group.line_ids)

        if not line_ids:
            return None

        min_wave: float | None = None
        max_wave: float | None = None

        for line_id in line_ids:
            line = self._absorption_lines.get(line_id)
            if line is None:
                msg = f"Absorption line not found for optimize group range: {line_id}"
                raise KeyError(msg)
            bounds = self._line_wavelength_bounds(line)
            lower, upper = bounds
            if min_wave is None or lower < min_wave:
                min_wave = lower
            if max_wave is None or upper > max_wave:
                max_wave = upper

        if min_wave is None or max_wave is None:
            return None

        return float(min_wave), float(max_wave)

    @staticmethod
    def _line_wavelength_bounds(line: AbsorptionLine) -> tuple[float, float]:
        """Determine wavelength bounds for an absorption line."""
        lambda_range = line.lambda_range
        if lambda_range is not None:
            return OptimizeGroupRangeResolver._validate_range_pair(
                lambda_range, context=f"absorption line '{line.line_id}' lambda_range"
            )

        observed_value = line.observed_wavelength()
        window_kms = line.window_kms

        if (
            not math.isfinite(observed_value)
            or not math.isfinite(window_kms)
            or observed_value <= 0.0
            or window_kms <= 0.0
        ):
            msg = f"Absorption line '{line.line_id}' has no valid wavelength bounds."
            raise ValueError(msg)

        delta = observed_value * window_kms / LIGHT_SPEED_KMS
        lower = observed_value - delta
        upper = observed_value + delta

        if lower >= upper:
            msg = f"Absorption line '{line.line_id}' resolved invalid wavelength bounds."
            raise ValueError(msg)

        return float(lower), float(upper)

    @staticmethod
    def _validate_range_pair(value: tuple[float, float], *, context: str) -> tuple[float, float]:
        """Validate a required range pair from an internal snapshot."""
        if not isinstance(value, tuple) or len(value) != 2:
            msg = f"{context} must be a two-value tuple."
            raise ValueError(msg)
        lower, upper = value
        if isinstance(lower, bool) or isinstance(upper, bool):
            msg = f"{context} must contain numeric bounds."
            raise TypeError(msg)
        lower_float = float(lower)
        upper_float = float(upper)
        if not math.isfinite(lower_float) or not math.isfinite(upper_float):
            msg = f"{context} bounds must be finite."
            raise ValueError(msg)
        if lower_float >= upper_float:
            msg = f"{context} lower bound must be less than upper bound."
            raise ValueError(msg)
        return lower_float, upper_float
