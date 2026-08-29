"""Voigt profile calculations."""

import numpy as np
from numpy.typing import NDArray
from scipy.special import wofz


def voigt_profile(
    wavelength: NDArray[np.float64], rest_wavelength: float, gamma: float, sigma: float
) -> NDArray[np.float64]:
    """Calculate Voigt absorption profile.

    The Voigt profile is normalized such that the integral over all
    wavelengths equals amplitude.

    Args:
        wavelength: Wavelength array in Angstroms
        rest_wavelength: Line center wavelength in Angstroms
        gamma: Lorentzian HWHM in Angstroms (natural broadening)
        sigma: Gaussian standard deviation in Angstroms (Doppler broadening)

    Returns:
        Voigt profile values
    """
    if sigma <= 0:
        msg = "Sigma must be positive"
        raise ValueError(msg)

    # Normalized frequency offset
    x = (wavelength - rest_wavelength) / (sigma * np.sqrt(2.0))

    # Voigt a parameter
    a = gamma / (sigma * np.sqrt(2.0)) if sigma > 0 else 0.0

    # Calculate profile
    z = x + 1j * a
    profile = np.asarray(wofz(z).real, dtype=np.float64)

    # Normalize and scale
    normalization = 1.0 / (sigma * np.sqrt(2.0 * np.pi))

    return np.asarray(normalization * profile, dtype=np.float64)
