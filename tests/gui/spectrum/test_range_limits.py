"""Tests for wavelength range enforcement utilities."""

from __future__ import annotations

import math

from chappy.application.spectrum.range_usecase import (
    MIN_WAVELENGTH_DISPLAY_SPAN,
    enforce_min_wavelength_span,
)


def test_enforce_respects_anchor_relative_position() -> None:
    """Ensures the anchor stays at the same relative position after expansion."""
    proposed_min = 20.0909
    proposed_max = 29.1818
    anchor = 21.0
    relative = 0.1

    adjusted_min, adjusted_max = enforce_min_wavelength_span(
        proposed_min, proposed_max, anchor_wavelength=anchor, anchor_relative_position=relative
    )

    assert math.isclose(
        adjusted_max - adjusted_min, MIN_WAVELENGTH_DISPLAY_SPAN, rel_tol=0.0, abs_tol=1e-6
    )
    relative_after = (anchor - adjusted_min) / (adjusted_max - adjusted_min)
    assert math.isclose(relative_after, relative, rel_tol=0.0, abs_tol=1e-6)


def test_enforce_clamps_inside_bounds_without_shifting_anchor() -> None:
    """When bounds restrict the window, shifting preserves the anchor alignment."""
    proposed_min = 95.0
    proposed_max = 99.0
    anchor = 99.0
    relative = 0.9

    adjusted_min, adjusted_max = enforce_min_wavelength_span(
        proposed_min,
        proposed_max,
        bounds=(90.0, 105.0),
        anchor_wavelength=anchor,
        anchor_relative_position=relative,
    )

    assert adjusted_min >= 90.0
    assert adjusted_max <= 105.0
    relative_after = (anchor - adjusted_min) / (adjusted_max - adjusted_min)
    assert math.isclose(relative_after, relative, rel_tol=0.0, abs_tol=1e-6)
