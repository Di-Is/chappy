"""Pure velocity-space transformation helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from chappy.core.constants import LIGHT_SPEED_KMS

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from chappy.presentation.velocity.view_model import VelocitySliceParams


def compute_velocity_slice(
    wavelength: NDArray[np.float64],
    flux: NDArray[np.float64],
    error: NDArray[np.float64] | None,
    params: VelocitySliceParams,
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64] | None]:
    """Convert a spectrum into velocity space and clamp to the configured window."""
    if params.rest_wavelength <= 0:
        msg = "rest_wavelength must be positive for velocity conversion"
        raise ValueError(msg)

    rest_observed = params.rest_wavelength * (1.0 + params.center_redshift)
    velocity = (wavelength / rest_observed - 1.0) * LIGHT_SPEED_KMS

    window_limit = abs(params.display_half_width_kms)
    if params.unit == "m/s":
        velocity = velocity * 1000.0
        window_limit *= 1000.0
    elif params.unit != "km/s":
        msg = f"Unsupported velocity unit: {params.unit}"
        raise ValueError(msg)

    finite_mask = np.isfinite(velocity) & np.isfinite(flux)
    if error is not None:
        finite_mask &= np.isfinite(error)

    mask = finite_mask & (velocity >= -window_limit) & (velocity <= window_limit)
    if not np.any(mask):
        empty: NDArray[np.float64] = np.zeros(0, dtype=np.float64)
        if error is not None:
            return empty, empty, np.zeros(0, dtype=np.float64)
        return empty, empty, None

    clipped_velocity = velocity[mask]
    clipped_flux = flux[mask]
    clipped_error = error[mask] if error is not None else None
    return clipped_velocity, clipped_flux, clipped_error


def compute_residual(
    velocity_obs: NDArray[np.float64],
    flux_obs: NDArray[np.float64],
    velocity_model: NDArray[np.float64],
    flux_model: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Compute residual by interpolating model to observed velocity grid."""
    if velocity_obs.size == 0:
        msg = "velocity_obs must not be empty"
        raise ValueError(msg)
    if velocity_model.size == 0:
        msg = "velocity_model must not be empty"
        raise ValueError(msg)

    residual: NDArray[np.float64] = np.full_like(flux_obs, np.nan, dtype=np.float64)
    in_range = (velocity_obs >= velocity_model.min()) & (velocity_obs <= velocity_model.max())
    if not np.any(in_range):
        return residual

    flux_model_interp = np.interp(velocity_obs[in_range], velocity_model, flux_model)
    residual[in_range] = flux_obs[in_range] - flux_model_interp
    return residual
