"""Tests for instrumental resolution convolution utilities."""

from __future__ import annotations

import numpy as np
import pytest

from chappy.core.math.instrument_resolution import apply_instrument_resolution
from chappy.core.resolution import ResolutionState
from chappy.core.spectrum_model import SpectrumModel


@pytest.fixture(scope="module")
def sample_wavelength() -> np.ndarray:
    return np.linspace(5000.0, 5005.0, 2048, dtype=np.float64)


@pytest.fixture(scope="module")
def narrow_absorption(sample_wavelength: np.ndarray) -> np.ndarray:
    center = 5002.5
    sigma = 0.02
    profile = np.exp(-0.5 * ((sample_wavelength - center) / sigma) ** 2)
    return 1.0 - 0.7 * profile


def test_apply_instrument_resolution_smears_delta(sample_wavelength: np.ndarray) -> None:
    flux = np.ones_like(sample_wavelength)
    flux[len(sample_wavelength) // 2] = 0.0

    convolved = apply_instrument_resolution(sample_wavelength, flux, resolution=20000.0)

    assert convolved.min() > 0.95
    np.testing.assert_allclose(convolved[[0, -1]], 1.0, atol=1e-6)


def test_spectrum_model_resolution_state_applies(
    sample_wavelength: np.ndarray, narrow_absorption: np.ndarray
) -> None:
    model = SpectrumModel()
    model.set_resolution_state(ResolutionState(value=30000.0, enabled=True))

    broadened = model.apply_resolution_effect(sample_wavelength, narrow_absorption)

    assert np.isclose(broadened.sum(), narrow_absorption.sum(), atol=5e-2)
    assert broadened.min() > 0.8


def test_resolution_disabled_returns_original(
    sample_wavelength: np.ndarray, narrow_absorption: np.ndarray
) -> None:
    model = SpectrumModel()
    model.set_resolution_state(ResolutionState(value=30000.0, enabled=False))

    result = model.apply_resolution_effect(sample_wavelength, narrow_absorption)
    np.testing.assert_allclose(result, narrow_absorption)
