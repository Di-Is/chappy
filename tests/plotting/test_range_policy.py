"""Focused tests for observed-range policy bounds derivation."""

from __future__ import annotations

import numpy as np

from chappy.plotting.renderers.range_policy import ObservedRangePolicy, YAxisBounds


def test_observed_y_range_returns_finite_bounds() -> None:
    """Observed y-range should span finite flux values only."""
    policy = ObservedRangePolicy()
    flux = np.array([1.0, np.nan, 1.5, 0.5, np.inf])

    assert policy.observed_y_range(flux) == (0.5, 1.5)


def test_observed_y_range_without_finite_values_returns_none() -> None:
    """All-NaN flux should yield no range."""
    policy = ObservedRangePolicy()

    assert policy.observed_y_range(np.array([np.nan, np.nan])) is None


def test_auto_range_y_bounds_uses_visible_window_only() -> None:
    """Auto-range bounds should derive from flux inside the x window."""
    policy = ObservedRangePolicy()
    wavelength = np.array([1000.0, 1010.0, 1020.0])
    flux = np.array([1.0, 1.5, 0.5])

    bounds = policy.auto_range_y_bounds(wavelength, flux, x_min=1005.0, x_max=1015.0)

    assert bounds == YAxisBounds(y_min=-0.05, y_max=1.634782608695652)


def test_auto_range_y_bounds_outside_window_returns_none() -> None:
    """An x window without samples should yield no bounds."""
    policy = ObservedRangePolicy()
    wavelength = np.array([1000.0, 1010.0])
    flux = np.array([1.0, 1.5])

    assert policy.auto_range_y_bounds(wavelength, flux, x_min=2000.0, x_max=2100.0) is None
