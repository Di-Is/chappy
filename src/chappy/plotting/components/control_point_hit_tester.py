"""Hit testing utilities for continuum control points."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

DisplayPointResolver = Callable[[float, float], tuple[float, float] | None]


class ControlPointHitTester:
    """Find continuum control points near pointer positions."""

    def point_index_near(
        self,
        *,
        points: Sequence[tuple[float, float]],
        target_display: tuple[float, float],
        data_to_display: DisplayPointResolver,
        tolerance_pixels: float,
    ) -> int | None:
        """Return the nearest point index within display-space tolerance."""
        best_index = None
        best_distance = float("inf")

        for idx, point in enumerate(points):
            display_point = data_to_display(*point)
            if display_point is None:
                continue
            dx = display_point[0] - target_display[0]
            dy = display_point[1] - target_display[1]
            distance = math.hypot(dx, dy)
            if distance <= tolerance_pixels and distance < best_distance:
                best_distance = distance
                best_index = idx

        return best_index

    @staticmethod
    def is_too_close_to_existing(
        *,
        points: Sequence[tuple[float, float]],
        wavelength: float,
        min_separation: float,
        exclude_index: int | None = None,
    ) -> bool:
        """Return True when a candidate wavelength is too close to existing points."""
        for idx, (existing_wave, _flux) in enumerate(points):
            if exclude_index is not None and idx == exclude_index:
                continue
            if abs(existing_wave - wavelength) < min_separation:
                return True
        return False
