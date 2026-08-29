"""Cosmology parameter data structures and helpers (SCR-DIA-COS support)."""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

from chappy.core.constants import LIGHT_SPEED_KMS

SPEED_OF_LIGHT_KM_S = LIGHT_SPEED_KMS
MEGAPARSEC_IN_KM = 3.0856775814913673e19
SECONDS_PER_YEAR = 31_557_600.0  # Julian year
GIGAYEAR_IN_SECONDS = SECONDS_PER_YEAR * 1e9


@dataclass(slots=True)
class CosmologyParameters:
    """Container for ΛCDM cosmology parameters.

    Attributes:
        h0: Hubble constant in km/s/Mpc
        omega_m: Matter density parameter Ωm (dimensionless)
        omega_lambda: Dark energy density parameter ΩΛ (dimensionless)
    """

    h0: float
    omega_m: float
    omega_lambda: float

    @property
    def omega_k(self) -> float:
        """Derived spatial curvature Ωk = 1 − Ωm − ΩΛ."""
        return 1.0 - self.omega_m - self.omega_lambda


# Planck 2018 TT,TE,EE+lowE+lensing cosmology defaults (ESA collaboration)
PLANCK_2018 = CosmologyParameters(h0=67.4, omega_m=0.315, omega_lambda=0.685)

# Spin box constraints aligned with docs/01_requirements/screen_specification/dialogs/cosmology.md
COSMOLOGY_CONSTRAINTS: dict[str, dict[str, float]] = {
    "h0": {"min": 50.0, "max": 100.0, "step": 0.1, "decimals": 1},
    "omega_m": {"min": 0.0, "max": 1.0, "step": 0.001, "decimals": 3},
    "omega_lambda": {"min": 0.0, "max": 1.0, "step": 0.001, "decimals": 3},
}


OMEGA_K_FLAT_ABS_TOLERANCE: float = sys.float_info.epsilon * 16


def is_spatially_flat(omega_k: float, *, tolerance: float = OMEGA_K_FLAT_ABS_TOLERANCE) -> bool:
    """Return whether Ωk is effectively zero within floating-point noise.

    Args:
        omega_k: Derived spatial curvature Ωk.
        tolerance: Absolute tolerance that represents floating-point rounding noise.

    Returns:
        True if Ωk is indistinguishable from zero, otherwise False.

    Raises:
        ValueError: If ``tolerance`` is negative.
    """
    if tolerance < 0:
        msg = "tolerance must be non-negative"
        raise ValueError(msg)

    return math.isclose(omega_k, 0.0, rel_tol=0.0, abs_tol=tolerance)


def _integration_steps(z: float) -> int:
    """Return adaptive Simpson step count based on redshift scale."""
    if not math.isfinite(z) or z <= 0:
        return 0

    base = 256
    scaled = int(abs(z) * 256)
    steps = max(base, scaled)
    if steps % 2:
        steps += 1
    return min(steps, 8192)


def _simpson_integral(func: Callable[[float], float], limit: float, steps: int) -> float:
    """Evaluate integral from 0 to ``limit`` using Simpson's rule."""
    if steps <= 0 or limit <= 0:
        return 0.0

    h = limit / steps
    total = func(0.0) + func(limit)

    for i in range(1, steps):
        coefficient = 4 if i % 2 else 2
        total += coefficient * func(h * i)

    return total * h / 3.0


def _e_z(z: float, params: CosmologyParameters) -> float:
    """Return dimensionless Hubble parameter E(z)."""
    term_m = params.omega_m * (1.0 + z) ** 3
    term_k = params.omega_k * (1.0 + z) ** 2
    term_l = params.omega_lambda
    radicand = term_m + term_k + term_l
    if radicand <= 0:
        return math.nan
    return math.sqrt(radicand)


def comoving_distance_mpc(z: float, params: CosmologyParameters) -> float:
    """Compute line-of-sight comoving distance (in Mpc) for redshift ``z``."""
    if not math.isfinite(z) or z <= 0:
        return 0.0

    steps = _integration_steps(z)

    def integrand(z_val: float) -> float:
        e_z = _e_z(z_val, params)
        if not math.isfinite(e_z) or e_z == 0:
            return 0.0
        return 1.0 / e_z

    integral = _simpson_integral(integrand, z, steps)
    if not math.isfinite(integral):
        return math.nan

    return SPEED_OF_LIGHT_KM_S / params.h0 * integral


def lookback_time_gyr(z: float, params: CosmologyParameters) -> float:
    """Compute lookback time (in Gyr) for redshift ``z``."""
    if not math.isfinite(z) or z <= 0:
        return 0.0

    steps = _integration_steps(z)

    def integrand(z_val: float) -> float:
        e_z = _e_z(z_val, params)
        if not math.isfinite(e_z) or e_z == 0:
            return 0.0
        return 1.0 / ((1.0 + z_val) * e_z)

    integral = _simpson_integral(integrand, z, steps)
    if not math.isfinite(integral):
        return math.nan

    hubble_seconds = MEGAPARSEC_IN_KM / params.h0
    seconds = hubble_seconds * integral
    return seconds / GIGAYEAR_IN_SECONDS


__all__ = [
    "COSMOLOGY_CONSTRAINTS",
    "PLANCK_2018",
    "CosmologyParameters",
    "comoving_distance_mpc",
    "is_spatially_flat",
    "lookback_time_gyr",
]
