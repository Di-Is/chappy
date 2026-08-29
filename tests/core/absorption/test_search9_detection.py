"""Tests for SEARCH9 absorption detection implementation."""

from __future__ import annotations

import numpy as np
import pytest

from chappy.core.absorption.search9_detection import (
    Search9Error,
    Search9Parameters,
    detect_regions,
)


def _make_gaussian_spectrum(
    center: float = 5005.0, amplitude: float = 0.3, width: float = 0.12, noise_level: float = 0.01
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    wavelength = np.linspace(5000.0, 5010.0, 4000)
    continuum = np.ones_like(wavelength)
    profile = amplitude * np.exp(-0.5 * ((wavelength - center) / width) ** 2)
    flux = 1.0 - profile
    rng = np.random.default_rng(42)
    noise = rng.normal(0.0, noise_level, size=wavelength.size)
    flux = flux + noise
    error = np.full_like(flux, noise_level)
    return wavelength, flux, error, continuum


def test_detect_regions_identifies_absorption_feature() -> None:
    wavelength, flux, error, continuum = _make_gaussian_spectrum()

    params = Search9Parameters(n_sigma=3.5, boundary_sigma=1.0, kernel_half_width=6)
    regions = detect_regions(wavelength, flux, error, continuum, params)

    assert regions, "Expected at least one detected region"
    top_region = max(regions, key=lambda region: region.significance)
    assert abs(top_region.lambda_center - 5005.0) < 0.2
    assert top_region.significance > params.n_sigma


def test_detect_regions_requires_error_array() -> None:
    wavelength, flux, error, continuum = _make_gaussian_spectrum()

    params = Search9Parameters()
    with pytest.raises(Search9Error) as excinfo:
        detect_regions(wavelength, flux, None, continuum, params)

    assert excinfo.value.code == "no-error-array"


def test_detect_regions_requires_minimum_data_points() -> None:
    wavelength = np.linspace(5000.0, 5001.0, 50)
    flux = np.ones_like(wavelength)
    error = np.full_like(flux, 0.01)
    continuum = np.ones_like(flux)

    params = Search9Parameters()
    with pytest.raises(Search9Error) as excinfo:
        detect_regions(wavelength, flux, error, continuum, params)

    assert excinfo.value.code == "insufficient-data"


def test_detect_regions_handles_resolution_kernel() -> None:
    wavelength, flux, error, continuum = _make_gaussian_spectrum(noise_level=0.0, amplitude=0.9)

    params = Search9Parameters(
        n_sigma=2.0,
        boundary_sigma=1.0,
        kernel_half_width=4,
        resolution_enabled=True,
        resolution=50_000.0,
    )

    regions = detect_regions(wavelength, flux, error, continuum, params)
    assert isinstance(regions, list)


def test_detect_regions_disabled_resolution_uses_identity_kernel() -> None:
    """Disabled resolution smoothing should not require a resolution value."""
    wavelength, flux, error, continuum = _make_gaussian_spectrum()

    params = Search9Parameters(n_sigma=3.5, resolution_enabled=False, resolution=0.0)

    regions = detect_regions(wavelength, flux, error, continuum, params)

    assert isinstance(regions, list)


@pytest.mark.parametrize("resolution", [None, 0.0, -1.0, float("nan")])
def test_detect_regions_enabled_resolution_rejects_invalid_resolution(
    resolution: float | None,
) -> None:
    """Enabled resolution smoothing should not fall back to an identity kernel."""
    wavelength, flux, error, continuum = _make_gaussian_spectrum()

    params = Search9Parameters(resolution_enabled=True, resolution=resolution)

    with pytest.raises(Search9Error) as excinfo:
        detect_regions(wavelength, flux, error, continuum, params)

    assert excinfo.value.code == "invalid-input"


def test_detect_regions_invalid_spacing() -> None:
    wavelength = np.ones(200)
    flux = np.ones_like(wavelength)
    error = np.full_like(flux, 0.01)
    continuum = np.ones_like(flux)

    params = Search9Parameters()
    with pytest.raises(Search9Error) as excinfo:
        detect_regions(wavelength, flux, error, continuum, params)

    assert excinfo.value.code == "invalid-input"


def test_detect_regions_ignores_flux_at_masked_error_pixels() -> None:
    """A flux dip whose pixels have no valid error must not become a detection."""
    wavelength = np.linspace(5000.0, 5010.0, 4000)
    continuum = np.ones_like(wavelength)
    flux = np.ones_like(wavelength)
    error = np.full_like(flux, 0.01)
    flux[2000:2010] = 0.0
    error[2000:2010] = np.nan

    params = Search9Parameters(n_sigma=5.0, resolution_enabled=True, resolution=50_000.0)
    regions = detect_regions(wavelength, flux, error, continuum, params)

    assert regions == []


def test_detect_regions_skips_single_pixel_regions() -> None:
    """An isolated one-pixel dip must not produce a zero-width region."""
    wavelength = np.linspace(5000.0, 5010.0, 200)
    continuum = np.ones_like(wavelength)
    flux = np.ones_like(wavelength)
    flux[100] = 0.0
    error = np.full_like(flux, 0.01)

    params = Search9Parameters(n_sigma=3.5, boundary_sigma=1.0, kernel_half_width=0)
    regions = detect_regions(wavelength, flux, error, continuum, params)

    assert all(region.lambda_start < region.lambda_end for region in regions)
