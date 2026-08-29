"""Absorber marker hit-testing helpers."""

from __future__ import annotations


def resolve_absorber_hit_tolerance(
    *, x_min: float, x_max: float, tolerance: float | None
) -> float:
    """Return the hit-test tolerance for absorber marker selection.

    Args:
        x_min: Current visible minimum x value.
        x_max: Current visible maximum x value.
        tolerance: Explicit caller-provided tolerance, if any.

    Returns:
        Effective tolerance in x-axis units.
    """
    if tolerance is not None:
        return tolerance

    x_range = x_max - x_min
    return min(50.0, x_range * 0.01)
