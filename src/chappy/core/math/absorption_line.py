"""Absorber component for modeling absorption lines."""

import numpy as np
from numpy.typing import NDArray

from .voigt import voigt_profile

C_KMS = 2.99792458e5  # Speed of light in km/s
C_CMS = C_KMS * 1e5  # Speed of light in cm/s
E2_ME_C = 0.02654  # e²/(m_e * c) in convenient units for optical depth


def calculate_absorption_profile(
    wavelength: NDArray[np.float64],
    redshift: float,
    log_column_density: float,
    b_parameter: float,
    rest_wavelength: float,
    oscillator_strength: float,
    gamma: float,
) -> NDArray[np.float64]:
    """Calculate absorption profile using Voigt function.

    Args:
        wavelength: Wavelength array in Angstroms
        rest_wavelength: Rest wavelength in Angstroms
        redshift: Redshift
        log_column_density: Log10 column density (cm⁻²)
        b_parameter: Doppler parameter in km/s
        oscillator_strength: Oscillator strength
        gamma: Natural broadening in s⁻¹

    Returns:
        Transmission array (0 = complete absorption, 1 = no absorption)
    """
    # Apply redshift to get observed wavelength
    lambda_obs = rest_wavelength * (1.0 + redshift)

    # Calculate Doppler width in wavelength units (convert b from km/s to Gaussian σ)
    sigma_lambda = lambda_obs * b_parameter / (C_KMS * np.sqrt(2.0))

    # Calculate natural broadening in wavelength units
    # gamma_lambda = (lambda²/4πc) * gamma, convert λ from Å to cm then back to Å
    gamma_lambda = (lambda_obs**2 / (4.0 * np.pi * C_CMS)) * gamma * 1e-8

    # Calculate Voigt profile
    profile: NDArray[np.float64] = voigt_profile(
        wavelength, lambda_obs, gamma_lambda, sigma_lambda
    )

    # Calculate optical depth
    # τ = (πe²/m_e c) * N * f * λ * φ(λ)
    tau_coeff = (
        (E2_ME_C / C_CMS)
        * np.power(10.0, log_column_density)
        * oscillator_strength
        * rest_wavelength**2
        * 1e-8
    )
    tau: NDArray[np.float64] = tau_coeff * profile

    # Calculate transmission
    transmission: NDArray[np.float64] = np.empty_like(tau, dtype=np.float64)
    np.exp(-tau, out=transmission)
    return transmission
