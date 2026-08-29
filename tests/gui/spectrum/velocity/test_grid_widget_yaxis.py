"""Tests for velocity plot Y-axis range control."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest
from numpy.testing import assert_allclose

from chappy.core.constants import LIGHT_SPEED_KMS
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.core.spectrum import Spectrum
from chappy.gui.adapters.plotting import MatplotlibSpectrumPlot
from chappy.gui.shell.spectrum_mode_policy import spectrum_interaction_mode_policy
from chappy.gui.spectrum.spectrum_plot import create_default_spectrum_plot_host_factory
from chappy.gui.spectrum.spectrum_view import SpectrumView
from chappy.gui.spectrum.velocity import VelocityGridWidget, VelocitySubplotWidget
from chappy.plotting.utils.validators import validate_generic_spectrum_data
from chappy.presentation.velocity import VelocitySliceInfo, build_velocity_view_data

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


REST_WAVELENGTH = 1000.0


@pytest.fixture
def spectrum_plot(qtbot: QtBot) -> MatplotlibSpectrumPlot:
    """Create a MatplotlibSpectrumPlot instance for testing."""
    plot = MatplotlibSpectrumPlot(observed_data_validator=validate_generic_spectrum_data)
    qtbot.addWidget(plot)
    return plot


@pytest.fixture
def velocity_subplot(qtbot: QtBot) -> VelocitySubplotWidget:
    """Create a VelocitySubplotWidget instance for testing."""
    subplot = VelocitySubplotWidget()
    qtbot.addWidget(subplot)
    return subplot


@pytest.fixture
def velocity_grid(qtbot: QtBot) -> VelocityGridWidget:
    """Create a VelocityGridWidget instance for testing."""
    view = VelocityGridWidget()
    qtbot.addWidget(view)
    return view


def test_matplotlib_spectrum_plot_reports_observed_y_range(
    spectrum_plot: MatplotlibSpectrumPlot,
) -> None:
    """Observed range should ignore model and residual data."""
    spectrum_plot.set_observed_spectrum(
        np.array([1.0, 2.0, 3.0, 4.0, 5.0]), np.array([0.5, 0.8, 0.3, 0.9, 0.6]), error=None
    )

    assert spectrum_plot.get_observed_y_range() == (0.3, 0.9)


def test_matplotlib_spectrum_plot_returns_none_without_observed(
    spectrum_plot: MatplotlibSpectrumPlot,
) -> None:
    """No observed data should produce no range."""
    assert spectrum_plot.get_observed_y_range() is None


def test_velocity_subplot_reports_observed_y_range(
    velocity_subplot: VelocitySubplotWidget,
) -> None:
    """VelocitySubplotWidget should expose rendered observed flux limits."""
    _set_subplot_data(velocity_subplot, np.array([0.2, 0.8, 0.4]))

    result = velocity_subplot.get_observed_y_range()

    assert result is not None
    assert_allclose(result, (0.2, 0.8), atol=1e-10)


def test_velocity_subplot_set_flux_range_updates_axis_limits(
    velocity_subplot: VelocitySubplotWidget,
) -> None:
    """VelocitySubplotWidget should expose applied axis limits."""
    velocity_subplot.set_flux_range(-0.1, 1.2)
    assert_allclose(velocity_subplot.get_flux_range(), (-0.1, 1.2), atol=1e-10)


def test_velocity_grid_set_flux_range_applies_to_all_subplots(
    velocity_grid: VelocityGridWidget,
) -> None:
    """Grid-level flux range should propagate to every subplot."""
    velocity_grid.set_flux_range(-0.1, 1.2)

    for subplot in _subplots(velocity_grid):
        assert_allclose(subplot.get_flux_range(), (-0.1, 1.2), atol=1e-10)
    assert velocity_grid.is_manual_y_range_active() is True


def test_velocity_grid_auto_range_y_all_unifies_subplots(
    velocity_grid: VelocityGridWidget,
) -> None:
    """Auto range should choose one common Y range from all observed subplots."""
    _set_view_subplot_data(velocity_grid, [(0.2, 0.8), (0.1, 0.9), (0.3, 0.7), None, None, None])

    velocity_grid.auto_range_y_all()

    expected = _expected_auto_range(0.1, 0.9)
    for subplot in _subplots(velocity_grid):
        assert_allclose(subplot.get_flux_range(), expected, atol=1e-10)
    assert velocity_grid.is_manual_y_range_active() is False


def test_velocity_grid_auto_range_y_all_preserves_existing_limits_without_data(
    velocity_grid: VelocityGridWidget,
) -> None:
    """Without observed data, auto range should leave existing manual limits unchanged."""
    velocity_grid.set_flux_range(-0.2, 1.2)

    velocity_grid.auto_range_y_all()

    for subplot in _subplots(velocity_grid):
        assert_allclose(subplot.get_flux_range(), (-0.2, 1.2), atol=1e-10)
    assert velocity_grid.is_manual_y_range_active() is True


def test_velocity_grid_get_global_observed_y_range_returns_margin_applied_range(
    velocity_grid: VelocityGridWidget,
) -> None:
    """Global observed range should include the configured margins."""
    _set_view_subplot_data(velocity_grid, [(0.2, 0.8), (0.1, 0.9), (0.3, 0.7), None, None, None])

    result = velocity_grid.get_global_observed_y_range()

    assert result is not None
    assert_allclose(result, _expected_auto_range(0.1, 0.9), atol=1e-10)


def test_velocity_grid_update_display_preserves_manual_range_when_flag_set(
    velocity_grid: VelocityGridWidget,
) -> None:
    """Rendering new data should not auto-range while manual limits are active."""
    project = _create_project_with_spectrum(np.array([0.2, 0.8, 0.4]))
    slices = [_single_slice()]
    _apply_slices(velocity_grid, slices)
    velocity_grid.set_flux_range(-0.2, 1.3)

    _set_project_view_data(velocity_grid, project, slices)

    assert_allclose(_subplots(velocity_grid)[0].get_flux_range(), (-0.2, 1.3))
    assert velocity_grid.is_manual_y_range_active() is True


def test_velocity_grid_update_display_auto_ranges_when_manual_flag_reset(
    velocity_grid: VelocityGridWidget,
) -> None:
    """Resetting the manual flag should re-enable automatic Y bounds."""
    project = _create_project_with_spectrum(np.array([0.2, 0.8, 0.4]))
    slices = [_single_slice()]
    _apply_slices(velocity_grid, slices)
    velocity_grid.reset_manual_y_range()

    _set_project_view_data(velocity_grid, project, slices)

    assert_allclose(_subplots(velocity_grid)[0].get_flux_range(), _expected_auto_range(0.2, 0.8))
    assert velocity_grid.is_manual_y_range_active() is False


def test_spectrum_view_syncs_velocity_flux_only_while_sync_connected(qtbot: QtBot) -> None:
    """Flux changes should reach the velocity grid only during an active overlay session."""
    spectrum_view = SpectrumView(plot_host_factory=create_default_spectrum_plot_host_factory())
    velocity_grid = VelocityGridWidget()
    qtbot.addWidget(spectrum_view)
    qtbot.addWidget(velocity_grid)
    spectrum_view.set_project(_create_project_with_spectrum(np.array([0.2, 0.8, 0.4])))
    spectrum_view._velocity_view = velocity_grid

    spectrum_view._connect_velocity_flux_sync()
    spectrum_view.data_bridge.set_flux_range(-0.1, 1.2)

    for subplot in _subplots(velocity_grid):
        assert_allclose(subplot.get_flux_range(), (-0.1, 1.2), atol=1e-10)

    spectrum_view._disconnect_velocity_flux_sync()
    spectrum_view.data_bridge.set_flux_range(-0.5, 0.5)

    for subplot in _subplots(velocity_grid):
        assert_allclose(subplot.get_flux_range(), (-0.1, 1.2), atol=1e-10)


def test_spectrum_view_get_velocity_plot_y_range_when_visible(qtbot: QtBot) -> None:
    """SpectrumView should surface the active velocity plot range when visible."""
    spectrum_view = SpectrumView(plot_host_factory=create_default_spectrum_plot_host_factory())
    velocity_grid = VelocityGridWidget()
    qtbot.addWidget(spectrum_view)
    qtbot.addWidget(velocity_grid)
    spectrum_view._velocity_view = velocity_grid
    spectrum_view._velocity_visible = True
    _set_view_subplot_data(velocity_grid, [(0.1, 0.9)])

    result = spectrum_view.get_velocity_plot_y_range()

    assert result is not None
    assert_allclose(result, _expected_auto_range(0.1, 0.9), atol=1e-10)


def _expected_auto_range(y_min: float, y_max: float) -> tuple[float, float]:
    """Return the expected auto-range from observed flux limits."""
    return min(y_min - 0.05, -0.05), max(y_max + 0.05, 1.05)


def _velocity_grid(size: int) -> np.ndarray:
    """Return a deterministic velocity grid for subplot data."""
    return np.linspace(-100.0, 100.0, size)


def _wavelength_from_velocity(velocity: np.ndarray) -> np.ndarray:
    """Convert test velocities to observed wavelengths at zero redshift."""
    return REST_WAVELENGTH * (1.0 + velocity / LIGHT_SPEED_KMS)


def _set_subplot_data(subplot: VelocitySubplotWidget, flux: np.ndarray) -> None:
    """Render observed velocity data in a subplot."""
    velocity = _velocity_grid(flux.size)
    error = np.full(flux.shape, 0.1, dtype=np.float64)
    subplot.set_data(velocity, flux, error, display_half_width_kms=150.0)


def _set_view_subplot_data(
    velocity_grid: VelocityGridWidget, flux_ranges: list[tuple[float, float] | None]
) -> None:
    """Populate grid subplots with deterministic observed data."""
    for subplot, flux_range in zip(_subplots(velocity_grid), flux_ranges, strict=False):
        if flux_range is None:
            continue
        y_min, y_max = flux_range
        _set_subplot_data(subplot, np.array([y_min, (y_min + y_max) / 2.0, y_max]))


def _create_project_with_spectrum(flux: np.ndarray) -> SpectroscopyProject:
    """Create a project containing one observed spectrum near the test rest wavelength."""
    velocity = _velocity_grid(flux.size)
    wavelength = _wavelength_from_velocity(velocity)
    error = np.full(flux.shape, 0.1, dtype=np.float64)
    project = SpectroscopyProject()
    project.model.set_observed_spectrum(Spectrum(wavelength=wavelength, flux=flux, error=error))
    return project


def _single_slice() -> VelocitySliceInfo:
    """Create one velocity slice matching the project spectrum."""
    return VelocitySliceInfo(
        rest_wavelength=REST_WAVELENGTH,
        label="Ly alpha",
        tie_group_key="",
        center_z=0.0,
        selected=True,
        analysis_half_width_kms=150.0,
    )


def _set_project_view_data(
    velocity_grid: VelocityGridWidget,
    project: SpectroscopyProject,
    slices: list[VelocitySliceInfo],
) -> None:
    """Set assembled velocity view data for tests."""
    velocity_grid.apply_view_data(
        build_velocity_view_data(
            project,
            slices,
            display_half_width_kms=velocity_grid.display_half_width.value,
            include_optimize_overlays=False,
        )
    )


def _apply_slices(velocity_grid: VelocityGridWidget, slices: list[VelocitySliceInfo]) -> None:
    """Apply slice-only view data without project spectra."""
    velocity_grid.apply_view_data(
        build_velocity_view_data(
            None,
            slices,
            display_half_width_kms=velocity_grid.display_half_width.value,
            include_optimize_overlays=False,
        )
    )


def _subplots(view: VelocityGridWidget) -> tuple[VelocitySubplotWidget, ...]:
    """Return the subplot children in grid order."""
    return tuple(view.findChildren(VelocitySubplotWidget))
