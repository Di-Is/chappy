"""SEARCH9-based absorption line detection utilities.

This module implements the equivalent-width based detection scheme
outlined in Schneider et al. (1993, ApJS, 87, 45) as referenced by the
IDENT requirements (IDN.02.02). It provides a light-weight Python
translation suitable for interactively identifying statistically
significant absorption troughs in a continuum-normalised spectrum.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

MIN_DATA_POINTS = 100
DEFAULT_BOUNDARY_SIGMA = 1.0
DEFAULT_KERNEL_HALF_WIDTH = 6
MIN_SPACING_SAMPLES = 2


FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]
IntArray = NDArray[np.int_]
ArrayLikeFloat = FloatArray | Sequence[float]


class Search9Error(RuntimeError):
    """Custom exception signalling detection failures."""

    def __init__(self, code: str, message: str) -> None:
        """Attach an error code used for user-facing messaging."""
        super().__init__(message)
        self.code = code


@dataclass(slots=True)
class Search9Parameters:
    """Container for SEARCH9 configurable parameters."""

    n_sigma: float = 50.0
    boundary_sigma: float = DEFAULT_BOUNDARY_SIGMA
    kernel_half_width: int = DEFAULT_KERNEL_HALF_WIDTH
    resolution: float | None = None
    resolution_enabled: bool = False


@dataclass(slots=True)
class Search9Region:
    """Result container for a detected absorption region."""

    lambda_start: float
    lambda_end: float
    lambda_center: float
    significance: float


def _validate_inputs(
    wavelength: FloatArray, flux: FloatArray, error: FloatArray | None, continuum: FloatArray
) -> None:
    if wavelength.size < MIN_DATA_POINTS or flux.size < MIN_DATA_POINTS:
        code = "insufficient-data"
        message = "At least 100 data points are required"
        raise Search9Error(code, message)
    if error is None:
        code = "no-error-array"
        message = "Error array is required for detection"
        raise Search9Error(code, message)
    if continuum.size == 0:
        code = "no-continuum"
        message = "Continuum array is empty"
        raise Search9Error(code, message)
    if wavelength.size != flux.size or wavelength.size != continuum.size:
        code = "invalid-input"
        message = "Spectrum and continuum lengths must match"
        raise Search9Error(code, message)
    if error.size != flux.size:
        code = "invalid-input"
        message = "Error array must match flux length"
        raise Search9Error(code, message)


def _estimate_delta_lambda(wavelength: FloatArray) -> float:
    if wavelength.size < MIN_SPACING_SAMPLES:
        return 0.0
    diffs: FloatArray = np.diff(wavelength)
    finite_diffs: FloatArray = diffs[np.isfinite(diffs)]
    if finite_diffs.size == 0:
        return 0.0
    return float(np.median(np.abs(finite_diffs)))


def _build_kernel(
    delta_lambda: float, params: Search9Parameters, reference_wavelength: float
) -> FloatArray:
    if not params.resolution_enabled:
        return np.array([1.0], dtype=np.float64)

    if params.resolution is None or not np.isfinite(params.resolution) or params.resolution <= 0:
        code = "invalid-input"
        message = "Resolution must be positive when resolution smoothing is enabled"
        raise Search9Error(code, message)
    if not np.isfinite(reference_wavelength) or reference_wavelength <= 0:
        code = "invalid-input"
        message = "Reference wavelength must be positive when resolution smoothing is enabled"
        raise Search9Error(code, message)
    if not np.isfinite(delta_lambda) or delta_lambda <= 0:
        code = "invalid-input"
        message = "Wavelength spacing must be positive when resolution smoothing is enabled"
        raise Search9Error(code, message)

    fwhm = reference_wavelength / params.resolution
    if not np.isfinite(fwhm) or fwhm <= 0:
        code = "invalid-input"
        message = "Resolution produced an invalid smoothing width"
        raise Search9Error(code, message)

    sigma_lambda = fwhm / (2.0 * np.sqrt(2.0 * np.log(2.0)))
    if not np.isfinite(sigma_lambda) or sigma_lambda <= 0:
        code = "invalid-input"
        message = "Resolution produced an invalid smoothing sigma"
        raise Search9Error(code, message)

    sigma_pixels = sigma_lambda / delta_lambda
    half_width = max(params.kernel_half_width, int(np.ceil(4.0 * sigma_pixels)))
    half_width = min(max(half_width, 1), 128)

    offsets = np.arange(-half_width, half_width + 1, dtype=np.float64)
    kernel: FloatArray = np.exp(-0.5 * (offsets * delta_lambda / sigma_lambda) ** 2)
    kernel /= np.sum(kernel)
    return kernel.astype(np.float64)


def _normalise_spectrum(
    flux: FloatArray, error: FloatArray, continuum: FloatArray
) -> tuple[FloatArray, FloatArray, BoolArray]:
    continuum_safe: FloatArray = np.where(
        np.isfinite(continuum) & (continuum > 0), continuum, np.nan
    )

    norm_flux = flux / continuum_safe
    norm_error = error / continuum_safe

    # EW and its variance must sum over the same pixels; a pixel lacking a
    # valid error would otherwise inflate |EW| without widening sigma_W.
    valid_mask = np.isfinite(norm_flux) & np.isfinite(norm_error) & (norm_error > 0)

    min_error = 1e-10
    norm_error = np.where(valid_mask, np.maximum(norm_error, min_error), 0.0)

    norm_flux = np.where(valid_mask, norm_flux, 0.0)

    return (norm_flux.astype(np.float64), norm_error.astype(np.float64), valid_mask.astype(bool))


def _masked_convolution(
    values: FloatArray, mask: BoolArray, kernel: FloatArray
) -> tuple[FloatArray, FloatArray]:
    kernel_float = kernel.astype(np.float64)
    masked_values: FloatArray = np.where(mask, values, 0.0)
    conv = np.convolve(masked_values, kernel_float, mode="same").astype(np.float64)
    norm = np.convolve(mask.astype(np.float64), kernel_float, mode="same").astype(np.float64)
    return conv, norm


def _initial_regions(indices: IntArray) -> list[tuple[int, int]]:
    if indices.size == 0:
        return []

    regions: list[tuple[int, int]] = []
    start = int(indices[0])
    prev = int(indices[0])

    for idx_raw in indices[1:]:
        idx = int(idx_raw)
        if idx == prev + 1:
            prev = idx
            continue
        regions.append((start, prev))
        start = idx
        prev = idx
    regions.append((start, prev))
    return regions


def _expand_regions(
    regions: list[tuple[int, int]],
    significance: FloatArray,
    finite_mask: BoolArray,
    params: Search9Parameters,
) -> list[tuple[int, int]]:
    if not regions:
        return []

    expanded: list[tuple[int, int]] = []
    last_index = len(significance) - 1

    for start_idx_raw, end_idx_raw in regions:
        expanded_start = int(start_idx_raw)
        expanded_end = int(end_idx_raw)
        if params.boundary_sigma > 0:
            i = expanded_start
            while i > 0 and finite_mask[i - 1] and significance[i - 1] <= -params.boundary_sigma:
                i -= 1
            expanded_start = i

            i = expanded_end
            while (
                i < last_index
                and finite_mask[i + 1]
                and significance[i + 1] <= -params.boundary_sigma
            ):
                i += 1
            expanded_end = i
        expanded.append((expanded_start, expanded_end))

    expanded.sort(key=lambda pair: pair[0])

    merged: list[tuple[int, int]] = []
    current_start, current_end = expanded[0]
    for start_idx, end_idx in expanded[1:]:
        if start_idx <= current_end:
            current_end = max(current_end, end_idx)
            continue
        merged.append((current_start, current_end))
        current_start, current_end = start_idx, end_idx
    merged.append((current_start, current_end))
    return merged


def _find_regions(significance: FloatArray, params: Search9Parameters) -> list[tuple[int, int]]:
    finite_mask = np.isfinite(significance)
    detection_mask = finite_mask & (significance <= -params.n_sigma)
    indices = np.flatnonzero(detection_mask)

    preliminary = _initial_regions(indices)
    return _expand_regions(preliminary, significance, finite_mask, params)


def detect_regions(
    wavelength: ArrayLikeFloat,
    flux: ArrayLikeFloat,
    error: ArrayLikeFloat | None,
    continuum: ArrayLikeFloat,
    params: Search9Parameters,
) -> list[Search9Region]:
    """Detect statistically significant absorption regions.

    Raises:
        Search9Error: If detection cannot be performed due to invalid inputs.
    """
    wavelength_arr: FloatArray = np.asarray(wavelength, dtype=np.float64)
    flux_arr: FloatArray = np.asarray(flux, dtype=np.float64)
    continuum_arr: FloatArray = np.asarray(continuum, dtype=np.float64)
    error_arr: FloatArray | None = (
        np.asarray(error, dtype=np.float64) if error is not None else None
    )

    _validate_inputs(wavelength_arr, flux_arr, error_arr, continuum_arr)

    if error_arr is None:
        msg = "no-error-array"
        raise Search9Error(msg, "Error array is required for detection")

    delta_lambda = _estimate_delta_lambda(wavelength_arr)
    if delta_lambda <= 0:
        code = "invalid-input"
        message = "Non-positive wavelength spacing"
        raise Search9Error(code, message)

    kernel = _build_kernel(delta_lambda, params, float(np.mean(wavelength_arr)))

    norm_flux, norm_error, valid_mask = _normalise_spectrum(flux_arr, error_arr, continuum_arr)

    # Equivalent width computation (negative for absorption features)
    delta_flux = norm_flux - 1.0
    ew_raw, ew_norm = _masked_convolution(delta_flux, valid_mask, kernel)
    with np.errstate(invalid="ignore", divide="ignore"):
        ew = np.divide(ew_raw, ew_norm, out=np.full_like(ew_raw, np.nan), where=ew_norm > 0)
    ew *= delta_lambda

    kernel_sq = kernel**2
    norm_error_sq = norm_error**2
    variance_raw, _ = _masked_convolution(norm_error_sq, valid_mask, kernel_sq)
    # EW was renormalised by ew_norm, so its variance scales by ew_norm**2.
    with np.errstate(invalid="ignore", divide="ignore"):
        variance = np.divide(
            (delta_lambda**2) * variance_raw,
            ew_norm**2,
            out=np.full_like(variance_raw, np.nan),
            where=ew_norm > 0,
        )
    sigma_w = np.sqrt(variance)

    with np.errstate(invalid="ignore", divide="ignore"):
        significance = np.divide(ew, sigma_w, out=np.full_like(ew, np.nan), where=sigma_w > 0)

    regions_indices = _find_regions(significance, params)
    if not regions_indices:
        return []

    results: list[Search9Region] = []
    for start_idx, end_idx in regions_indices:
        region_slice = slice(start_idx, end_idx + 1)
        region_waves = wavelength_arr[region_slice]
        region_flux = norm_flux[region_slice]
        region_sig = significance[region_slice]

        # Single-pixel regions have lambda_start == lambda_end, which violates
        # the region contract (lambda_start < lambda_end) consumed by overlays.
        if region_waves.size < 2:
            continue

        weights = np.clip(1.0 - region_flux, 0.0, None)
        weight_sum = float(np.sum(weights))
        if weight_sum <= 0:
            weights = np.ones_like(region_waves)
            weight_sum = float(weights.size)

        lambda_center = float(np.sum(region_waves * weights) / weight_sum)
        lambda_start = float(region_waves[0])
        lambda_end = float(region_waves[-1])
        region_significance = float(np.nanmin(region_sig))
        if not np.isfinite(region_significance):
            continue

        results.append(
            Search9Region(
                lambda_start=lambda_start,
                lambda_end=lambda_end,
                lambda_center=lambda_center,
                significance=abs(region_significance),
            )
        )

    return results


__all__ = [
    "DEFAULT_BOUNDARY_SIGMA",
    "DEFAULT_KERNEL_HALF_WIDTH",
    "MIN_DATA_POINTS",
    "Search9Error",
    "Search9Parameters",
    "Search9Region",
    "detect_regions",
]
