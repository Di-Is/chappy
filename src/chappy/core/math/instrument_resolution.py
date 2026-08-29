"""Instrumental resolution convolution helpers."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final

import numpy as np
from scipy.signal import fftconvolve

from chappy.core.constants import LIGHT_SPEED_KMS

if TYPE_CHECKING:
    from collections.abc import Callable

    from numpy.typing import NDArray

MIN_HALF_KERNEL_WIDTH: Final[int] = 6  # Requirement baseline; expand dynamically as needed
SIGMA_MULTIPLIER: Final[float] = 4.0  # Include ±4σ to capture most of the energy
SQRT_2LN2: Final[float] = math.sqrt(2.0 * math.log(2.0))

# Fine samples to place across the narrowest intrinsic Doppler FWHM before convolving.
OVERSAMPLE_TARGET_SUBSAMPLES: Final[int] = 3
MAX_OVERSAMPLE: Final[int] = 21

# Simple cache to avoid regenerating kernels for identical configurations
_kernel_cache: dict[tuple[float, int, float, int], NDArray[np.float64]] = {}


def _build_uniform_log_grid(
    wavelength: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Create a uniform grid in log-wavelength space matching the data extent."""
    log_min = float(np.log(wavelength[0]))
    log_max = float(np.log(wavelength[-1]))
    n_points = len(wavelength)

    uniform_log = np.linspace(log_min, log_max, n_points, dtype=np.float64)
    uniform_wave = np.exp(uniform_log).astype(np.float64, copy=False)
    return uniform_log, uniform_wave


def _get_gaussian_kernel(
    resolution: float, n_points: int, delta_log: float
) -> tuple[NDArray[np.float64], int]:
    """Return normalized Gaussian kernel for given resolution and grid spacing."""
    # FWHM in log-lambda units is 1 / R
    fwhm_log = 1.0 / resolution
    sigma_pixels = fwhm_log / (2.0 * SQRT_2LN2 * delta_log)
    if sigma_pixels <= 0.0:
        msg = "Resolution must produce positive sigma"
        raise ValueError(msg)

    half_width = min(
        max(MIN_HALF_KERNEL_WIDTH, math.ceil(SIGMA_MULTIPLIER * sigma_pixels)),
        max(1, (n_points - 1) // 2),
    )

    key = (float(resolution), int(n_points), float(delta_log), int(half_width))
    cached = _kernel_cache.get(key)
    if cached is not None:
        return cached, half_width

    offsets = np.arange(-half_width, half_width + 1, dtype=np.float64)
    kernel = np.exp(-0.5 * np.square(offsets / sigma_pixels))
    kernel_sum = float(np.sum(kernel))
    if kernel_sum <= 0:
        msg = "Gaussian kernel sum must be positive"
        raise ValueError(msg)
    kernel = kernel / kernel_sum
    _kernel_cache[key] = kernel
    return kernel, half_width


def apply_instrument_resolution(
    wavelength: NDArray[np.float64], flux: NDArray[np.float64], *, resolution: float
) -> NDArray[np.float64]:
    """Convolve flux with instrumental resolution effects.

    Args:
        wavelength: Monotonic wavelength grid in Angstroms.
        flux: Model flux array defined on the same grid.
        resolution: Resolving power R = λ/Δλ. Must be positive.

    Returns:
        Convolved flux array of same shape.
    """
    if resolution <= 0:
        msg = "Resolution must be positive"
        raise ValueError(msg)
    if wavelength.ndim != 1 or flux.ndim != 1:
        msg = "wavelength and flux must be 1-D arrays"
        raise ValueError(msg)
    if len(wavelength) != len(flux):
        msg = "wavelength and flux must have the same length"
        raise ValueError(msg)
    if len(wavelength) < 3:
        return flux.copy()

    if not np.all(np.diff(wavelength) > 0):
        msg = "wavelength array must be strictly increasing"
        raise ValueError(msg)

    log_grid, uniform_wave = _build_uniform_log_grid(wavelength)
    flux_uniform = np.interp(uniform_wave, wavelength, flux, left=flux[0], right=flux[-1])

    if len(log_grid) < 2:
        return flux.copy()
    delta_log = float(log_grid[1] - log_grid[0])
    if delta_log <= 0:
        msg = "Computed log-wavelength spacing must be positive"
        raise ValueError(msg)

    kernel, half_width = _get_gaussian_kernel(resolution, len(flux_uniform), delta_log)

    pad_width = half_width
    padded_flux = np.pad(flux_uniform, pad_width, mode="edge")
    convolved_padded = fftconvolve(padded_flux, kernel, mode="same")
    convolved = convolved_padded[pad_width:-pad_width] if pad_width > 0 else convolved_padded

    # Interpolate back to original wavelength grid
    result = np.interp(wavelength, uniform_wave, convolved)
    return np.asarray(result, dtype=np.float64)


def resolve_oversample_factor(wavelength: NDArray[np.float64], min_b_kms: float | None) -> int:
    """Fine-grid factor needed to resolve the narrowest line before convolution.

    A point-sampled Voigt on the pixel grid loses the line core once its intrinsic
    Doppler width approaches the pixel size, biasing fitted N and b. Returns 1 (no
    oversampling, no cost) whenever every line is broad relative to the pixels.
    """
    if min_b_kms is None or min_b_kms <= 0 or len(wavelength) < 2:
        return 1
    pixel_fraction = float(np.median(np.diff(wavelength)) / np.median(wavelength))
    doppler_fraction = 2.0 * SQRT_2LN2 * min_b_kms / LIGHT_SPEED_KMS  # FWHM_Doppler / λ
    if doppler_fraction <= 0:
        return 1
    factor = math.ceil(OVERSAMPLE_TARGET_SUBSAMPLES * pixel_fraction / doppler_fraction)
    return int(min(max(1, factor), MAX_OVERSAMPLE))


def kernel_half_width_pixels(wavelength: NDArray[np.float64], resolution: float) -> int:
    """Pixel margin the Gaussian LSF reaches, for padding a fit window before convolution."""
    if len(wavelength) < 2 or resolution <= 0:
        return 0
    delta_log = float(np.median(np.diff(np.log(wavelength))))
    if delta_log <= 0:
        return 0
    sigma_pixels = (1.0 / resolution) / (2.0 * SQRT_2LN2 * delta_log)
    return int(max(MIN_HALF_KERNEL_WIDTH, math.ceil(SIGMA_MULTIPLIER * sigma_pixels)))


def _oversampled_grid(wavelength: NDArray[np.float64], oversample: int) -> NDArray[np.float64]:
    """Contiguous fine grid with `oversample` sub-samples spanning each pixel bin."""
    edges = np.empty(len(wavelength) + 1, dtype=np.float64)
    edges[1:-1] = 0.5 * (wavelength[:-1] + wavelength[1:])
    edges[0] = wavelength[0] - 0.5 * (wavelength[1] - wavelength[0])
    edges[-1] = wavelength[-1] + 0.5 * (wavelength[-1] - wavelength[-2])
    widths = np.diff(edges)
    fractions = (np.arange(oversample, dtype=np.float64) + 0.5) / oversample
    return (edges[:-1, None] + widths[:, None] * fractions[None, :]).ravel()


def apply_instrument_resolution_model(
    wavelength: NDArray[np.float64],
    model_flux: Callable[[NDArray[np.float64]], NDArray[np.float64]],
    *,
    resolution: float,
    oversample: int,
) -> NDArray[np.float64]:
    """Convolve a model with the LSF, oversampling narrow lines and rebinning to pixels.

    Args:
        wavelength: Monotonic pixel grid in Angstroms.
        model_flux: Callable returning raw (pre-convolution) model flux on any grid.
        resolution: Resolving power R = λ/Δλ.
        oversample: Fine sub-samples per pixel (1 = evaluate directly on the pixel grid).

    Returns:
        Convolved flux sampled on `wavelength`.
    """
    if oversample <= 1:
        return apply_instrument_resolution(
            wavelength, model_flux(wavelength), resolution=resolution
        )
    fine = _oversampled_grid(wavelength, oversample)
    convolved = apply_instrument_resolution(fine, model_flux(fine), resolution=resolution)
    rebinned = convolved.reshape(len(wavelength), oversample).mean(axis=1)
    return np.asarray(rebinned, dtype=np.float64)


__all__ = [
    "apply_instrument_resolution",
    "apply_instrument_resolution_model",
    "kernel_half_width_pixels",
    "resolve_oversample_factor",
]
