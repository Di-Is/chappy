"""Constants for parameter validation in absorber components."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ParameterValidationRanges:
    """Validation ranges for absorber parameters.

    These ranges define the physically reasonable bounds for absorber
    parameters in astronomical spectroscopy.
    """

    # Column density validation (log10 cm⁻²)
    COLUMN_DENSITY_MIN: float = 10.0  # Minimum log column density
    COLUMN_DENSITY_MAX: float = 22.0  # Maximum log column density

    # B parameter validation (km/s) - Doppler broadening parameter
    B_PARAMETER_MIN: float = 1.0  # Minimum b parameter (km/s)
    B_PARAMETER_MAX: float = 1000.0  # Maximum b parameter (km/s)

    # Redshift validation
    REDSHIFT_MIN: float = -0.1  # Minimum redshift (allows for nearby objects)
    REDSHIFT_MAX: float = 10.0  # Maximum redshift (high-z quasars)


# Global instance for easy access
PARAM_VALIDATION = ParameterValidationRanges()
