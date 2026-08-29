"""Data validation utilities for spectrum plotting.

This module provides functions for validating spectrum data before plotting
or processing.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)

# Constants for wavelength validation
MIN_ASTRONOMICAL_WAVELENGTH = 100.0  # Minimum wavelength in Angstroms (X-ray)
MAX_ASTRONOMICAL_WAVELENGTH = 25000.0  # Maximum wavelength in Angstroms (infrared)
MAX_WAVELENGTH_SPACING = 1000.0  # Maximum reasonable wavelength spacing
MIN_DATA_POINTS = 2  # Minimum number of data points


def validate_spectrum_data(
    wavelength: NDArray[np.float64] | None,
    flux: NDArray[np.float64] | None,
    error: NDArray[np.float64] | None = None,
) -> bool:
    """Validate spectrum data arrays.

    Performs comprehensive validation including:
    - Array existence and type
    - Array length consistency
    - Wavelength range and monotonicity
    - Finite value checks

    Args:
        wavelength: Wavelength array in Angstroms
        flux: Flux array
        error: Optional error array

    Returns:
        True if data is valid, False otherwise
    """
    # Check if arrays exist
    if wavelength is None or flux is None:
        logger.warning("Wavelength or flux data is None")
        return False

    # Check array lengths
    if len(wavelength) != len(flux):
        logger.warning(
            "Wavelength and flux arrays have different lengths: %d vs %d",
            len(wavelength),
            len(flux),
        )
        return False

    if error is not None and len(error) != len(wavelength):
        logger.warning(
            "Error array length (%d) doesn't match wavelength length (%d)",
            len(error),
            len(wavelength),
        )
        return False

    # Check minimum data points
    if len(wavelength) < MIN_DATA_POINTS:
        logger.warning("Not enough data points: %d < %d", len(wavelength), MIN_DATA_POINTS)
        return False

    # Check for finite values
    if not validate_finite_values(wavelength, flux, error):
        return False

    # Check wavelength range and monotonicity
    return validate_wavelength_array(wavelength)


def validate_generic_spectrum_data(
    wavelength: NDArray[np.float64] | None,
    flux: NDArray[np.float64] | None,
    error: NDArray[np.float64] | None = None,
) -> bool:
    """Validate generic plot data without astronomical wavelength constraints.

    Args:
        wavelength: X-axis array.
        flux: Y-axis array.
        error: Optional error array.

    Returns:
        True if the arrays are length-compatible and contain finite values.
    """
    if wavelength is None or flux is None:
        return False

    if len(wavelength) != len(flux):
        return False

    if error is not None and len(error) != len(wavelength):
        return False

    return validate_finite_values(wavelength, flux, error)


def validate_finite_values(
    wavelength: NDArray[np.float64],
    flux: NDArray[np.float64],
    error: NDArray[np.float64] | None = None,
) -> bool:
    """Check that all values are finite (not NaN or inf).

    Args:
        wavelength: Wavelength array
        flux: Flux array
        error: Optional error array

    Returns:
        True if all values are finite
    """
    if not np.all(np.isfinite(wavelength)):
        logger.warning("Wavelength array contains non-finite values")
        return False

    if not np.all(np.isfinite(flux)):
        logger.warning("Flux array contains non-finite values")
        return False

    if error is not None and not np.any(np.isfinite(error)):
        logger.warning("Error array contains no finite values")
        return False

    return True


def validate_wavelength_array(wavelength: NDArray[np.float64]) -> bool:
    """Validate wavelength array properties.

    Checks:
    - Wavelength range is reasonable for astronomical data
    - Array is monotonically increasing
    - Wavelength spacing is reasonable

    Args:
        wavelength: Wavelength array in Angstroms

    Returns:
        True if wavelength array is valid
    """
    # Check wavelength range
    wave_min = np.min(wavelength)
    wave_max = np.max(wavelength)

    if wave_min < MIN_ASTRONOMICAL_WAVELENGTH:
        logger.warning(
            "Minimum wavelength %.2f is below astronomical range (%.2f)",
            wave_min,
            MIN_ASTRONOMICAL_WAVELENGTH,
        )
        return False

    if wave_max > MAX_ASTRONOMICAL_WAVELENGTH:
        logger.warning(
            "Maximum wavelength %.2f is above astronomical range (%.2f)",
            wave_max,
            MAX_ASTRONOMICAL_WAVELENGTH,
        )
        return False

    # Check monotonicity
    if not is_monotonic_increasing(wavelength):
        logger.warning("Wavelength array is not monotonically increasing")
        return False

    # Check wavelength spacing
    if len(wavelength) > 1:
        spacings = np.diff(wavelength)
        max_spacing = np.max(spacings)

        if max_spacing > MAX_WAVELENGTH_SPACING:
            logger.warning(
                "Maximum wavelength spacing %.2f exceeds threshold %.2f",
                max_spacing,
                MAX_WAVELENGTH_SPACING,
            )
            # This is a warning but not a failure

    return True


def is_monotonic_increasing(array: NDArray[np.float64]) -> bool:
    """Check if array is monotonically increasing.

    Args:
        array: Array to check

    Returns:
        True if array is monotonically increasing
    """
    return bool(np.all(np.diff(array) > 0))
