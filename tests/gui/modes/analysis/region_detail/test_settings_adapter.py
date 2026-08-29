"""Tests for optimize settings adapter."""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QSettings

from chappy.core.cosmology import PLANCK_2018
from chappy.gui.modes.analysis.region_detail.adapters.settings_adapter import (
    COSMOLOGY_H0_KEY,
    COSMOLOGY_OMEGA_LAMBDA_KEY,
    COSMOLOGY_OMEGA_M_KEY,
    OptimizeSettingsAdapter,
)


def _settings(path: Path) -> QSettings:
    """Create isolated settings storage."""
    return QSettings(str(path), QSettings.Format.IniFormat)


def test_load_cosmology_parameters_reads_persisted_values(tmp_path: Path) -> None:
    """Adapter should load persisted cosmology settings."""
    settings = _settings(tmp_path / "cosmology.ini")
    settings.setValue(COSMOLOGY_H0_KEY, 72.5)
    settings.setValue(COSMOLOGY_OMEGA_M_KEY, 0.333)
    settings.setValue(COSMOLOGY_OMEGA_LAMBDA_KEY, 0.611)

    parameters = OptimizeSettingsAdapter(settings).load_cosmology_parameters()

    assert parameters.h0 == 72.5
    assert parameters.omega_m == 0.333
    assert parameters.omega_lambda == 0.611


def test_load_cosmology_parameters_uses_planck_defaults(tmp_path: Path) -> None:
    """Adapter should fall back to Planck defaults when settings are absent."""
    parameters = OptimizeSettingsAdapter(
        _settings(tmp_path / "empty.ini")
    ).load_cosmology_parameters()

    assert math.isclose(parameters.h0, PLANCK_2018.h0, rel_tol=0.0, abs_tol=1e-9)
    assert math.isclose(parameters.omega_m, PLANCK_2018.omega_m, rel_tol=0.0, abs_tol=1e-9)
    assert math.isclose(
        parameters.omega_lambda, PLANCK_2018.omega_lambda, rel_tol=0.0, abs_tol=1e-9
    )
