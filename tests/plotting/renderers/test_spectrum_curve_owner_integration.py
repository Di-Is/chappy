"""Integration tests for spectrum curve rendering owners."""

from __future__ import annotations

from dataclasses import dataclass

from matplotlib.lines import Line2D
import numpy as np
import pytest

from chappy.plotting.core.spectrum_data_store import SpectrumPlotDataStore
from chappy.plotting.core.plot_config import PlotConfig
from chappy.plotting.renderers import (
    CurveDisplayResolutionOwner,
    MatplotlibRenderer,
    SpectrumCurveOwner,
    get_style_registry,
)
from chappy.plotting.renderers.spectrum_curves import component_curve_name
from chappy.presentation.spectrum import (
    ComponentCurveVisuals,
    SpectrumComponentCurve,
    SpectrumPlotDisplayCommand,
)


@dataclass(frozen=True)
class _CurveOwnerHarness:
    """Small integration harness for owner-level rendering tests."""

    owner: SpectrumCurveOwner
    renderer: MatplotlibRenderer
    data_store: SpectrumPlotDataStore


def _curve_line(renderer: MatplotlibRenderer, name: str) -> Line2D:
    """Return a rendered Matplotlib line by name."""
    item = renderer.plot_items[name]
    assert isinstance(item, Line2D)
    return item


@pytest.fixture
def harness() -> _CurveOwnerHarness:
    """Create a real owner wired to the real Matplotlib renderer."""
    renderer = MatplotlibRenderer()
    renderer.create_plot_widget()
    data_store = SpectrumPlotDataStore()
    owner = SpectrumCurveOwner(
        renderer=renderer,
        data_store=data_store,
        style_registry=get_style_registry(),
        config=PlotConfig(),
        display_resolution=CurveDisplayResolutionOwner(sink=renderer),
    )
    return _CurveOwnerHarness(owner=owner, renderer=renderer, data_store=data_store)


def test_render_observed_draws_observed_and_error_curves(harness: _CurveOwnerHarness) -> None:
    """Observed rendering should materialize both flux and error lines."""
    wavelength = np.linspace(1200.0, 1300.0, 100)
    flux = np.random.random(100)
    error = np.ones(100) * 0.1

    harness.data_store.set_observed_data(wavelength, flux, error)
    harness.owner.render_observed(
        display_command=SpectrumPlotDisplayCommand(
            use_normalized_observed=False, render_absorption_line_labels=True
        ),
        show_error_bars=True,
    )

    observed = _curve_line(harness.renderer, "observed")
    error_line = _curve_line(harness.renderer, "error")
    np.testing.assert_array_equal(observed.get_xdata(), wavelength)
    np.testing.assert_array_equal(observed.get_ydata(), flux)
    np.testing.assert_array_equal(error_line.get_ydata(), error)


def test_render_observed_uses_normalized_data_when_requested(harness: _CurveOwnerHarness) -> None:
    """Normalized observed rendering should follow continuum-normalized data."""
    wavelength = np.linspace(1200.0, 1300.0, 4)
    flux = np.array([2.0, 4.0, 6.0, 8.0])
    error = np.array([0.2, 0.4, 0.6, 0.8])
    continuum = np.array([2.0, 2.0, 3.0, 4.0])

    harness.data_store.set_observed_data(wavelength, flux, error)
    harness.data_store.set_continuum_data(wavelength, continuum)
    harness.owner.render_observed(
        display_command=SpectrumPlotDisplayCommand(
            use_normalized_observed=True, render_absorption_line_labels=True
        ),
        show_error_bars=True,
    )

    observed = _curve_line(harness.renderer, "observed")
    error_line = _curve_line(harness.renderer, "error")
    np.testing.assert_allclose(observed.get_ydata(), np.array([1.0, 2.0, 2.0, 2.0]))
    np.testing.assert_allclose(error_line.get_ydata(), np.array([0.1, 0.2, 0.2, 0.2]))


def test_render_model_draws_model_curve(harness: _CurveOwnerHarness) -> None:
    """Model rendering should use stored model data directly."""
    wavelength = np.linspace(1200.0, 1300.0, 100)
    model_flux = np.ones(100) * 0.95

    harness.data_store.set_model_data(wavelength, model_flux)
    harness.owner.render_model()

    model = _curve_line(harness.renderer, "model")
    np.testing.assert_array_equal(model.get_xdata(), wavelength)
    np.testing.assert_array_equal(model.get_ydata(), model_flux)


def test_residual_and_model_clear_remove_curves_and_data(harness: _CurveOwnerHarness) -> None:
    """Owner clear operations should drop renderer items and stored arrays together."""
    wavelength = np.linspace(1200.0, 1300.0, 100)
    model_flux = np.ones(100) * 0.95
    residual = np.random.random(100) * 0.1

    harness.data_store.set_model_data(wavelength, model_flux)
    harness.owner.render_model()
    harness.owner.set_residual_data(wavelength, residual)

    harness.owner.clear_model()
    harness.owner.clear_residual()

    assert "model" not in harness.renderer.plot_items
    assert "residual" not in harness.renderer.plot_items
    assert harness.data_store.get_model_data() is None
    assert harness.data_store.get_residual_data() is None


def _component_curve(
    component_id: str, color: str, *, emphasized: bool = False
) -> SpectrumComponentCurve:
    """Create a component transmission curve on a short wavelength grid."""
    wavelength = np.linspace(1200.0, 1300.0, 10)
    return SpectrumComponentCurve(
        component_id=component_id,
        color=color,
        wavelength=wavelength,
        flux=np.linspace(1.0, 0.5, 10),
        emphasized=emphasized,
    )


def test_render_component_profiles_draws_one_dashed_curve_per_component(
    harness: _CurveOwnerHarness,
) -> None:
    """Each component gets its own identity-coloured curve under the model curve."""
    harness.owner.render_component_profiles(
        (_component_curve("abs-1", "#1B9E77"), _component_curve("abs-2", "#D95F02"))
    )

    first = _curve_line(harness.renderer, component_curve_name("abs-1"))
    second = _curve_line(harness.renderer, component_curve_name("abs-2"))
    assert first.get_color() == "#1B9E77"
    assert second.get_color() == "#D95F02"
    assert first.get_linestyle() == ComponentCurveVisuals.LINE_STYLE
    assert first.get_zorder() == ComponentCurveVisuals.Z_ORDER
    assert first.get_alpha() == ComponentCurveVisuals.ALPHA


def test_render_component_profiles_drops_components_no_longer_present(
    harness: _CurveOwnerHarness,
) -> None:
    """Re-rendering a smaller component set removes the stale curves."""
    harness.owner.render_component_profiles(
        (_component_curve("abs-1", "#1B9E77"), _component_curve("abs-2", "#D95F02"))
    )

    harness.owner.render_component_profiles((_component_curve("abs-2", "#D95F02"),))

    assert component_curve_name("abs-1") not in harness.renderer.plot_items
    assert component_curve_name("abs-2") in harness.renderer.plot_items


def test_clear_model_also_removes_component_curves(harness: _CurveOwnerHarness) -> None:
    """Component curves belong to the model, so clearing the model clears them."""
    harness.owner.render_component_profiles((_component_curve("abs-1", "#1B9E77"),))

    harness.owner.clear_model()

    assert component_curve_name("abs-1") not in harness.renderer.plot_items


def test_clear_component_profiles_removes_every_component_curve(
    harness: _CurveOwnerHarness,
) -> None:
    """Turning the display off leaves no component curve behind."""
    harness.owner.render_component_profiles(
        (_component_curve("abs-1", "#1B9E77"), _component_curve("abs-2", "#D95F02"))
    )

    harness.owner.clear_component_profiles()

    assert component_curve_name("abs-1") not in harness.renderer.plot_items
    assert component_curve_name("abs-2") not in harness.renderer.plot_items


def test_set_emphasized_component_id_restyles_without_recomputing(
    harness: _CurveOwnerHarness,
) -> None:
    """Selecting a component thickens its curve and keeps every colour and sample."""
    harness.owner.render_component_profiles(
        (_component_curve("abs-1", "#1B9E77"), _component_curve("abs-2", "#D95F02"))
    )
    selected = _curve_line(harness.renderer, component_curve_name("abs-1"))
    other = _curve_line(harness.renderer, component_curve_name("abs-2"))
    samples = selected.get_ydata()

    harness.owner.set_emphasized_component_id("abs-1")

    assert selected.get_linewidth() == ComponentCurveVisuals.EMPHASIZED_LINE_WIDTH
    assert selected.get_alpha() == ComponentCurveVisuals.EMPHASIZED_ALPHA
    assert selected.get_zorder() == ComponentCurveVisuals.EMPHASIZED_Z_ORDER
    assert selected.get_color() == "#1B9E77"
    np.testing.assert_array_equal(selected.get_ydata(), samples)
    assert other.get_linewidth() == ComponentCurveVisuals.LINE_WIDTH
    assert other.get_zorder() == ComponentCurveVisuals.Z_ORDER


def test_set_emphasized_component_id_clears_previous_emphasis(harness: _CurveOwnerHarness) -> None:
    """Deselecting returns every component curve to its resting style."""
    harness.owner.render_component_profiles(
        (_component_curve("abs-1", "#1B9E77", emphasized=True),)
    )

    harness.owner.set_emphasized_component_id(None)

    line = _curve_line(harness.renderer, component_curve_name("abs-1"))
    assert line.get_linewidth() == ComponentCurveVisuals.LINE_WIDTH
    assert line.get_alpha() == ComponentCurveVisuals.ALPHA
