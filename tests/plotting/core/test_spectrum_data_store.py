"""Unit tests for SpectrumPlotDataStore."""

from __future__ import annotations

import numpy as np
import pytest

from chappy.plotting.core.spectrum_data_store import SpectrumPlotDataStore


def test_clear_residual_data_sets_none() -> None:
    """clear_residual_data should clear public residual data."""
    store = SpectrumPlotDataStore()
    store.set_residual_data(np.array([1.0, 2.0]), np.array([0.1, 0.2]))
    assert store.get_residual_data() is not None

    store.clear_residual_data()

    assert store.get_residual_data() is None


def test_clear_residual_data_preserves_other_data() -> None:
    """clear_residual_data should not affect observed/model data."""
    store = SpectrumPlotDataStore()
    store.set_observed_data(np.array([1.0, 2.0]), np.array([0.9, 1.0]), np.array([0.01, 0.01]))
    store.set_residual_data(np.array([1.0, 2.0]), np.array([0.1, 0.2]))

    store.clear_residual_data()

    assert store.get_residual_data() is None
    assert store.get_observed_data() is not None


def test_unknown_wavelength_range_data_type_fails_fast() -> None:
    """Unknown data type names are internal caller errors."""
    store = SpectrumPlotDataStore()

    with pytest.raises(ValueError, match="Unknown spectrum data type"):
        store.get_wavelength_range("not-a-spectrum-layer")
