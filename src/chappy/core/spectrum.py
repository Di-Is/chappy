"""Spectrum data structure for astronomical spectroscopy."""

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray


@dataclass
class Spectrum:
    """Single astronomical spectrum representation.

    This class represents a single spectrum with wavelength, flux, and
    optional error arrays. It maintains compatibility with FITS format
    and supports various wavelength coordinate systems.

    Attributes:
        wavelength: Wavelength array in Angstroms
        flux: Flux array in erg/s/cm²/Å
        error: Optional 1-sigma error array; entries that are not finite and
            positive (sentinel nulls, negatives, zeros, Inf) are normalised
            to NaN on construction
        header: FITS header information as dictionary
        crval1: Reference wavelength value
        cdelt1: Wavelength increment
        crpix1: Reference pixel
        dc_flag: Logarithmic wavelength flag
        lin_vel: Linear velocity flag
    """

    wavelength: NDArray[np.float64]
    flux: NDArray[np.float64]
    error: NDArray[np.float64] | None = None
    header: dict[str, Any] = field(default_factory=dict)
    crval1: float = 0.0
    cdelt1: float = 1.0
    crpix1: int = 1
    dc_flag: bool = False
    lin_vel: bool = False

    def __post_init__(self) -> None:
        """Validate array dimensions after initialization."""
        if len(self.wavelength) != len(self.flux):
            msg = (
                f"Wavelength and flux arrays must have same length. "
                f"Got {len(self.wavelength)} and {len(self.flux)}"
            )
            raise ValueError(msg)

        if self.error is not None:
            self.assign_error(self.error)

    def assign_error(self, error: NDArray[np.float64]) -> None:
        """Assign a 1-sigma error array, normalising invalid entries to NaN.

        Entries that are not finite and positive (sentinel nulls such as
        -9999 or -1e32, negatives, zeros, Inf) carry no uncertainty
        information and are stored as NaN.

        Args:
            error: Error array matching the flux length.

        Raises:
            ValueError: If the array length does not match the flux array.
        """
        if len(error) != len(self.flux):
            msg = (
                f"Error array must have same length as flux. Got {len(error)} and {len(self.flux)}"
            )
            raise ValueError(msg)
        self.error = np.where(np.isfinite(error) & (error > 0), error, np.nan).astype(np.float64)

    def copy(self) -> "Spectrum":
        """Create a deep copy of the spectrum."""
        return Spectrum(
            wavelength=self.wavelength.copy(),
            flux=self.flux.copy(),
            error=self.error.copy() if self.error is not None else None,
            header=self.header.copy(),
            crval1=self.crval1,
            cdelt1=self.cdelt1,
            crpix1=self.crpix1,
            dc_flag=self.dc_flag,
            lin_vel=self.lin_vel,
        )

    @property
    def wavelength_range(self) -> tuple[float, float]:
        """Get wavelength range as (min, max) tuple."""
        return float(np.min(self.wavelength)), float(np.max(self.wavelength))

    @property
    def n_pixels(self) -> int:
        """Number of pixels/data points in spectrum."""
        return len(self.wavelength)

    @property
    def has_error(self) -> bool:
        """Check if error array is present."""
        return self.error is not None

    def calculate_snr(self, wavelength_range: tuple[float, float] | None = None) -> float:
        """Calculate signal-to-noise ratio.

        Args:
            wavelength_range: Optional wavelength range for calculation

        Returns:
            Median SNR value
        """
        if self.error is None:
            msg = "Cannot calculate SNR without error array"
            raise ValueError(msg)

        if wavelength_range is None:
            mask = ~np.isnan(self.flux) & ~np.isnan(self.error) & (self.error > 0)
        else:
            mask = (
                (self.wavelength >= wavelength_range[0])
                & (self.wavelength <= wavelength_range[1])
                & ~np.isnan(self.flux)
                & ~np.isnan(self.error)
                & (self.error > 0)
            )

        if not np.any(mask):
            msg = "Cannot calculate SNR: no valid data points in range"
            raise ValueError(msg)

        snr = self.flux[mask] / self.error[mask]
        return float(np.median(snr))
