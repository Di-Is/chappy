from __future__ import annotations

import sys

import pytest

from chappy.core.cosmology import (
    PLANCK_2018,
    CosmologyParameters,
    comoving_distance_mpc,
    is_spatially_flat,
    lookback_time_gyr,
)


@pytest.mark.parametrize(
    ("redshift", "expected"),
    [(0.5, 1951.386986158016), (2.0, 5312.07539244653), (4.0, 7332.510405936026)],
)
def test_comoving_distance_against_baseline(redshift: float, expected: float) -> None:
    params = PLANCK_2018
    ours = comoving_distance_mpc(redshift, params)
    assert ours == pytest.approx(expected, rel=5e-3)


@pytest.mark.parametrize(
    ("redshift", "expected"), [(0.5, 5.209965198197182), (2.0, 10.522877283992694)]
)
def test_lookback_time_against_baseline(redshift: float, expected: float) -> None:
    params = PLANCK_2018
    ours = lookback_time_gyr(redshift, params)
    assert ours == pytest.approx(expected, rel=5e-3)


def test_nonflat_parameters_handled() -> None:
    params = CosmologyParameters(h0=70.0, omega_m=0.3, omega_lambda=0.6)
    distance = comoving_distance_mpc(1.0, params)
    lookback = lookback_time_gyr(1.0, params)
    assert distance > 0
    assert lookback > 0


def test_is_spatially_flat_matches_float_noise() -> None:
    epsilon = sys.float_info.epsilon
    assert is_spatially_flat(0.0)
    assert is_spatially_flat(epsilon * 8)
    assert is_spatially_flat(-epsilon * 4)


def test_is_spatially_flat_rejects_visible_curvature() -> None:
    assert not is_spatially_flat(1e-9)
    assert not is_spatially_flat(-1e-6)


def test_is_spatially_flat_validates_tolerance() -> None:
    with pytest.raises(ValueError):
        is_spatially_flat(0.0, tolerance=-1.0)
