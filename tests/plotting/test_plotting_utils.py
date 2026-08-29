"""Tests for plotting utility helpers."""

from __future__ import annotations

import numpy as np

from chappy.plotting.utils.absorber_hit_testing import resolve_absorber_hit_tolerance
from chappy.plotting.utils.validators import validate_generic_spectrum_data


def test_validate_generic_spectrum_data_accepts_finite_non_astronomical_axes() -> None:
    """Generic validation should accept finite non-astronomical x-axis data."""
    x_data = np.array([-200.0, -100.0, 0.0, 100.0])
    y_data = np.array([0.9, 1.0, 0.95, 1.02])

    assert validate_generic_spectrum_data(x_data, y_data, error=None)


def test_validate_generic_spectrum_data_rejects_length_mismatch() -> None:
    """Generic validation should reject mismatched array lengths."""
    x_data = np.array([1.0, 2.0, 3.0])
    y_data = np.array([0.9, 1.0])

    assert not validate_generic_spectrum_data(x_data, y_data, error=None)


def test_resolve_absorber_hit_tolerance_prefers_explicit_value() -> None:
    """An explicit absorber hit tolerance should be preserved."""
    assert resolve_absorber_hit_tolerance(x_min=1000.0, x_max=2000.0, tolerance=7.5) == 7.5


def test_resolve_absorber_hit_tolerance_uses_visible_range_when_implicit() -> None:
    """Implicit absorber hit tolerance should scale with visible x-range."""
    assert resolve_absorber_hit_tolerance(x_min=1000.0, x_max=1200.0, tolerance=None) == 2.0
