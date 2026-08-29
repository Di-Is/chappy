"""Policies for deriving spectrum plot axis ranges from observed-spectrum data.

These policies operate on full-resolution source arrays. Rendered artists hold
display-resolution slices (see ``CurveDisplayResolutionOwner``) and must not be
used as a data source for range calculations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class YAxisBounds:
    """Resolved y-axis bounds for a visible observed-spectrum slice."""

    y_min: float
    y_max: float


class ObservedRangePolicy:
    """Derive y-range bounds from full-resolution observed-spectrum arrays."""

    def observed_y_range(self, flux: NDArray[np.float64]) -> tuple[float, float] | None:
        """Return finite y bounds of the observed flux array."""
        valid_mask = np.isfinite(flux)
        if not np.any(valid_mask):
            return None

        valid_flux = flux[valid_mask]
        return float(np.min(valid_flux)), float(np.max(valid_flux))

    def auto_range_y_bounds(
        self,
        wavelength: NDArray[np.float64],
        flux: NDArray[np.float64],
        *,
        x_min: float,
        x_max: float,
    ) -> YAxisBounds | None:
        """Return y-axis bounds for observed data in the current x window."""
        window_mask = (wavelength >= x_min) & (wavelength <= x_max) & np.isfinite(flux)
        if not np.any(window_mask):
            return None

        visible_flux = flux[window_mask]
        y_min = float(np.min(visible_flux))
        y_max = float(np.max(visible_flux))

        label_y_position = 0.92
        new_y_min = min(y_min - 0.05, -0.05)
        required_plot_range = (y_max - new_y_min) / label_y_position
        new_y_max = max(new_y_min + required_plot_range, 1.05)
        return YAxisBounds(y_min=new_y_min, y_max=new_y_max)
