"""Unit tests for velocity-space transform helpers."""

from __future__ import annotations

import numpy as np
from numpy.testing import assert_allclose
import pytest

from chappy.presentation.velocity import (
    VelocitySliceParams,
    compute_residual,
    compute_velocity_slice,
)


def test_compute_velocity_slice_recenters_by_redshift() -> None:
    """Velocity conversion should center the rest wavelength at zero velocity."""
    rest = 1215.67
    center_z = 0.25
    rest_observed = rest * (1.0 + center_z)
    delta = rest_observed * 5e-4

    wavelength = np.array([rest_observed - delta, rest_observed, rest_observed + delta])
    flux = np.array([0.9, 1.0, 1.1])
    error = np.array([0.01, 0.01, 0.01])

    params = VelocitySliceParams(
        rest_wavelength=rest, center_redshift=center_z, display_half_width_kms=500.0, unit="km/s"
    )
    velocity, flux_window, error_window = compute_velocity_slice(wavelength, flux, error, params)

    assert len(velocity) == 3
    assert_allclose(velocity, [-149.896229, 0.0, 149.896229], atol=0.1)
    assert_allclose(flux_window, flux)
    assert_allclose(error_window, error)


def test_compute_velocity_slice_applies_window_filter() -> None:
    """Velocity window should drop samples outside the specified range."""
    rest = 1550.0
    center_z = 0.1
    rest_observed = rest * (1.0 + center_z)
    large_shift = rest_observed * 1e-3

    wavelength = np.array(
        [rest_observed - large_shift, rest_observed, rest_observed + large_shift]
    )
    flux = np.array([0.8, 1.0, 0.7])

    params = VelocitySliceParams(
        rest_wavelength=rest, center_redshift=center_z, display_half_width_kms=100.0, unit="km/s"
    )
    velocity, flux_window, _ = compute_velocity_slice(wavelength, flux, None, params)

    assert len(velocity) == 1
    assert_allclose(velocity, [0.0], atol=1e-6)
    assert_allclose(flux_window, [1.0])


def test_compute_velocity_slice_supports_meters_per_second() -> None:
    """The helper must generate velocities in metres per second when requested."""
    rest = 2796.35
    center_z = 0.0
    rest_observed = rest
    delta = rest_observed * 2e-4

    wavelength = np.array([rest_observed - delta, rest_observed])
    flux = np.array([1.2, 0.95])

    params = VelocitySliceParams(
        rest_wavelength=rest, center_redshift=center_z, display_half_width_kms=100.0, unit="m/s"
    )
    velocity, flux_window, _ = compute_velocity_slice(wavelength, flux, None, params)

    assert len(velocity) == 2
    assert_allclose(velocity, [-59_958.479, 0.0], atol=10.0)
    assert_allclose(flux_window, flux)


def test_compute_residual_basic() -> None:
    """Residual should be observed minus model on the observation grid."""
    velocity_obs = np.array([-100.0, 0.0, 100.0])
    flux_obs = np.array([1.0, 0.8, 1.0])
    velocity_model = np.array([-100.0, 0.0, 100.0])
    flux_model = np.array([1.0, 0.9, 1.0])

    residual = compute_residual(velocity_obs, flux_obs, velocity_model, flux_model)

    assert_allclose(residual, [0.0, -0.1, 0.0], atol=1e-10)


def test_compute_residual_interpolates_model_to_obs_grid() -> None:
    """Model should be interpolated to observed velocity grid."""
    velocity_obs = np.array([0.0, 50.0, 100.0])
    flux_obs = np.array([1.0, 1.0, 1.0])
    velocity_model = np.array([0.0, 100.0])
    flux_model = np.array([0.8, 1.0])

    residual = compute_residual(velocity_obs, flux_obs, velocity_model, flux_model)

    assert_allclose(residual, [0.2, 0.1, 0.0], atol=1e-10)


def test_compute_residual_returns_nan_outside_model_range() -> None:
    """Points outside model velocity range should return NaN."""
    velocity_obs = np.array([-200.0, 0.0, 200.0])
    flux_obs = np.array([1.0, 1.0, 1.0])
    velocity_model = np.array([-100.0, 100.0])
    flux_model = np.array([0.9, 0.9])

    residual = compute_residual(velocity_obs, flux_obs, velocity_model, flux_model)

    assert np.isnan(residual[0])
    assert_allclose(residual[1], 0.1, atol=1e-10)
    assert np.isnan(residual[2])


def test_compute_residual_raises_on_empty_observed() -> None:
    """Empty observed array should raise ValueError."""
    velocity_obs = np.array([])
    flux_obs = np.array([])
    velocity_model = np.array([0.0, 100.0])
    flux_model = np.array([1.0, 1.0])

    with pytest.raises(ValueError, match="must not be empty"):
        compute_residual(velocity_obs, flux_obs, velocity_model, flux_model)


def test_compute_residual_raises_on_empty_model() -> None:
    """Empty model array should raise ValueError."""
    velocity_obs = np.array([0.0, 100.0])
    flux_obs = np.array([1.0, 1.0])
    velocity_model = np.array([])
    flux_model = np.array([])

    with pytest.raises(ValueError, match="must not be empty"):
        compute_residual(velocity_obs, flux_obs, velocity_model, flux_model)
