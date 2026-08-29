"""Focused tests for SpectrumRegionFocusController."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from chappy.gui.shell.spectrum_region_focus_controller import SpectrumRegionFocusController


def test_compute_flux_range_returns_display_padding() -> None:
    """Flux-range computation should apply display-oriented padding."""
    project = SimpleNamespace(
        model=SimpleNamespace(
            observed_spectrum=SimpleNamespace(
                wavelength=np.array([100.0, 110.0, 120.0, 130.0]),
                flux=np.array([0.2, 0.5, 0.8, 1.0]),
            )
        )
    )

    flux_range = SpectrumRegionFocusController._compute_flux_range(project, 105.0, 125.0)

    assert flux_range == (-0.1, 1.1)


def test_focus_region_pushes_selection_into_plot_host() -> None:
    """Focusing a region must select it in the plot host for model/residual."""
    selected: list[object] = []
    line = SimpleNamespace(line_id="line-1", lambda_range=(3540.0, 3550.0))
    project = SimpleNamespace(
        absorption_lines={"line-1": line},
        model=SimpleNamespace(
            observed_spectrum=SimpleNamespace(
                wavelength=np.array([3535.0, 3545.0, 3555.0]), flux=np.array([1.0, 0.4, 1.0])
            )
        ),
    )
    spectrum_view = SimpleNamespace(
        plot_host=SimpleNamespace(set_selected_absorption_region=selected.append),
        coordinator=SimpleNamespace(coordinate_range_update=lambda *a, **k: None),
        get_wavelength_range=lambda: (3530.0, 3560.0),
        get_flux_range=lambda: (-0.1, 1.1),
        set_reset_ranges=lambda *a: None,
    )
    region = SimpleNamespace(region_id="region-1", line_ids=["line-1"])
    controller = SpectrumRegionFocusController(
        project_provider=lambda: project, spectrum_view_provider=lambda: spectrum_view
    )

    controller.focus_region(region)

    assert selected == [region]


def test_compute_flux_range_returns_none_without_visible_samples() -> None:
    """Flux-range computation should return None when no visible samples remain."""
    project = SimpleNamespace(
        model=SimpleNamespace(
            observed_spectrum=SimpleNamespace(
                wavelength=np.array([100.0, 110.0]), flux=np.array([np.nan, np.nan])
            )
        )
    )

    flux_range = SpectrumRegionFocusController._compute_flux_range(project, 90.0, 120.0)

    assert flux_range is None
