"""Centralized data management for spectrum plotting.

This module provides a centralized data store that handles storage, validation,
and access to all spectrum-related data (observed, model, residual, continuum).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)


class SpectrumPlotDataStore:
    """Manages all spectrum data for plotting.

    This class centralizes data storage and provides a consistent interface
    for accessing and updating spectrum data. It handles:
    - Observed spectrum data
    - Model spectrum data
    - Residual data
    - Continuum data
    """

    def __init__(self) -> None:
        """Initialize the data store with empty data."""
        self._observed_data: dict[str, NDArray[np.float64] | None] | None = None
        self._model_data: dict[str, NDArray[np.float64] | None] | None = None
        self._residual_data: dict[str, NDArray[np.float64] | None] | None = None
        self._continuum_data: dict[str, NDArray[np.float64] | None] | None = None
        self._normalized_observed: dict[str, NDArray[np.float64] | None] | None = None

        # Metadata
        self._data_ranges: dict[str, tuple[float, float]] = {}
        self._last_update_times: dict[str, float] = {}

    def set_observed_data(
        self,
        wavelength: NDArray[np.float64],
        flux: NDArray[np.float64],
        error: NDArray[np.float64] | None = None,
    ) -> dict[str, NDArray[np.float64] | None]:
        """Set observed spectrum data.

        Args:
            wavelength: Wavelength array
            flux: Flux array
            error: Optional error array

        Returns:
            Dictionary with stored data arrays
        """
        # Create defensive copies
        safe_wavelength = np.array(wavelength, copy=True, dtype=np.float64)
        safe_flux = np.array(flux, copy=True, dtype=np.float64)
        safe_error = np.array(error, copy=True, dtype=np.float64) if error is not None else None

        self._observed_data = {
            "wavelength": safe_wavelength,
            "flux": safe_flux,
            "error": safe_error,
        }

        # Update data ranges
        self._update_data_range("observed", safe_wavelength, safe_flux)
        self._update_normalized_observed()

        if len(safe_wavelength) > 0:
            logger.debug(
                "Set observed data: %d points, wavelength %.1f-%.1f Å",
                len(safe_wavelength),
                np.min(safe_wavelength),
                np.max(safe_wavelength),
            )
        else:
            logger.debug("Set observed data: empty arrays")

        return self._observed_data

    def get_observed_data(self) -> dict[str, NDArray[np.float64] | None] | None:
        """Get observed spectrum data.

        Returns:
            Dictionary with wavelength, flux, and error arrays, or None
        """
        return self._observed_data

    def set_model_data(
        self, wavelength: NDArray[np.float64], flux: NDArray[np.float64]
    ) -> dict[str, NDArray[np.float64] | None]:
        """Set model spectrum data.

        Args:
            wavelength: Wavelength array
            flux: Model flux array

        Returns:
            Dictionary with stored data arrays
        """
        safe_wavelength = np.array(wavelength, copy=True, dtype=np.float64)
        safe_flux = np.array(flux, copy=True, dtype=np.float64)

        self._model_data = {"wavelength": safe_wavelength, "flux": safe_flux}

        self._update_data_range("model", safe_wavelength, safe_flux)

        logger.debug("Set model data: %d points", len(safe_wavelength))

        return self._model_data

    def get_model_data(self) -> dict[str, NDArray[np.float64] | None] | None:
        """Get model spectrum data.

        Returns:
            Dictionary with wavelength and flux arrays, or None
        """
        return self._model_data

    def set_residual_data(
        self, wavelength: NDArray[np.float64], residuals: NDArray[np.float64]
    ) -> dict[str, NDArray[np.float64] | None]:
        """Set residual data.

        Args:
            wavelength: Wavelength array
            residuals: Residual array

        Returns:
            Dictionary with stored data arrays
        """
        safe_wavelength = np.array(wavelength, copy=True, dtype=np.float64)
        safe_residuals = np.array(residuals, copy=True, dtype=np.float64)

        self._residual_data = {"wavelength": safe_wavelength, "residuals": safe_residuals}

        self._update_data_range("residual", safe_wavelength, safe_residuals)

        logger.debug("Set residual data: %d points", len(safe_wavelength))

        return self._residual_data

    def get_residual_data(self) -> dict[str, NDArray[np.float64] | None] | None:
        """Get residual spectrum data.

        Returns:
            Dictionary with wavelength and residual arrays, or None
        """
        return self._residual_data

    def set_continuum_data(
        self, wavelength: NDArray[np.float64], continuum: NDArray[np.float64]
    ) -> dict[str, NDArray[np.float64] | None]:
        """Set continuum data.

        Args:
            wavelength: Wavelength array
            continuum: Continuum array

        Returns:
            Dictionary with stored data arrays
        """
        safe_wavelength = np.array(wavelength, copy=True, dtype=np.float64)
        safe_continuum = np.array(continuum, copy=True, dtype=np.float64)

        self._continuum_data = {"wavelength": safe_wavelength, "continuum": safe_continuum}

        self._update_data_range("continuum", safe_wavelength, safe_continuum)
        self._update_normalized_observed()

        return self._continuum_data

    def clear_all_data(self) -> None:
        """Clear all stored data."""
        self._observed_data = None
        self._model_data = None
        self._residual_data = None
        self._continuum_data = None
        self._normalized_observed = None
        self._data_ranges.clear()
        self._last_update_times.clear()

    def clear_residual_data(self) -> None:
        """Clear residual data only."""
        self._residual_data = None

    def clear_model_data(self) -> None:
        """Clear model data only."""
        self._model_data = None

    def get_wavelength_range(self, data_type: str = "observed") -> tuple[float, float] | None:
        """Get wavelength range for specified data type.

        Args:
            data_type: Type of data ("observed", "model", "residual", "continuum")

        Returns:
            Tuple of (min_wavelength, max_wavelength) or None
        """
        data = self._get_data_by_type(data_type)
        if data is None:
            return None

        wavelength = data.get("wavelength")
        if wavelength is None or len(wavelength) == 0:
            return None

        return float(np.min(wavelength)), float(np.max(wavelength))

    def _get_data_by_type(self, data_type: str) -> dict[str, NDArray[np.float64] | None] | None:
        """Get data dictionary by type.

        Args:
            data_type: Type of data to retrieve

        Returns:
            Data dictionary or None
        """
        if data_type == "observed":
            return self._observed_data
        if data_type == "model":
            return self._model_data
        if data_type == "residual":
            return self._residual_data
        if data_type == "continuum":
            return self._continuum_data
        msg = f"Unknown spectrum data type: {data_type}"
        raise ValueError(msg)

    def get_normalized_observed_data(self) -> dict[str, NDArray[np.float64] | None] | None:
        """Return observed data normalized by the active continuum."""
        return self._normalized_observed

    def _update_normalized_observed(self) -> None:
        """Recompute normalized observed spectrum using current continuum."""
        self._normalized_observed = None

        if not self._observed_data or not self._continuum_data:
            return

        wavelength = self._observed_data.get("wavelength")
        flux = self._observed_data.get("flux")
        error = self._observed_data.get("error")
        continuum = self._continuum_data.get("continuum")

        if (
            wavelength is None
            or flux is None
            or continuum is None
            or len(flux) == 0
            or len(flux) != len(continuum)
        ):
            if flux is not None and continuum is not None and len(flux) != len(continuum):
                logger.warning(
                    "Observed flux (%d) and continuum (%d) lengths mismatch; skipping normalization",
                    len(flux),
                    len(continuum),
                )
            return

        safe_continuum = np.array(continuum, copy=False, dtype=np.float64)
        valid_mask = np.isfinite(safe_continuum) & (safe_continuum != 0.0)
        safe_divisor = np.where(valid_mask, safe_continuum, np.nan)

        norm_flux = np.array(flux, copy=True, dtype=np.float64) / safe_divisor
        norm_error = None
        if error is not None:
            norm_error = np.array(error, copy=True, dtype=np.float64) / safe_divisor

        self._normalized_observed = {
            "wavelength": np.array(wavelength, copy=False, dtype=np.float64),
            "flux": norm_flux,
            "error": norm_error,
        }

    def _update_data_range(
        self, data_type: str, wavelength: NDArray[np.float64], values: NDArray[np.float64]
    ) -> None:
        """Update stored data range for a data type.

        Args:
            data_type: Type of data
            wavelength: Wavelength array (unused but kept for consistency)
            values: Value array to compute range from
        """
        _ = wavelength  # Unused but kept for API consistency
        if len(values) > 0:
            self._data_ranges[data_type] = (float(np.min(values)), float(np.max(values)))
