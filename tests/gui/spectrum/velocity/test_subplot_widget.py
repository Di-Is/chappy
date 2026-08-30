"""Tests for the velocity subplot widget module."""

from __future__ import annotations

import numpy as np
from pytestqt.qtbot import QtBot

from chappy.gui.spectrum.velocity import VelocitySubplotWidget
from chappy.presentation.velocity import (
    VelocityComponentInfo,
    VelocityCurveSources,
    VelocityDisplayHalfWidth,
    VelocitySliceInfo,
    VelocitySpectrumData,
    build_velocity_slice_render_input,
)

_LIVE_SUBPLOTS: list[VelocitySubplotWidget] = []


def test_render_state_reports_title_components_and_placeholder(qtbot: QtBot) -> None:
    """Render state should expose observable widget state without private access."""
    subplot = VelocitySubplotWidget()
    _LIVE_SUBPLOTS.append(subplot)

    subplot.set_heading("Mg II 2796", primary=True)
    subplot.set_components(
        [
            VelocityComponentInfo(
                component_id="comp_1", velocity=0.0, rest_wavelength=2796.35, label="Component 1"
            )
        ]
    )
    subplot.show_placeholder("No samples in current window")

    state = subplot.render_state()

    assert state.title == "Mg II 2796 (baseline)"
    assert state.placeholder_visible is True
    assert state.placeholder_text == "No samples in current window"
    assert state.component_ids == ("comp_1",)
    qtbot.wait(0)


def test_render_state_reports_residual_presence(qtbot: QtBot) -> None:
    """Render state should indicate whether residual data is currently present."""
    subplot = VelocitySubplotWidget()
    _LIVE_SUBPLOTS.append(subplot)

    velocity = np.array([-20.0, 0.0, 20.0], dtype=np.float64)
    flux = np.array([1.0, 0.9, 1.0], dtype=np.float64)
    error = np.array([0.1, 0.1, 0.1], dtype=np.float64)
    residual = np.array([0.0, -0.05, 0.0], dtype=np.float64)

    subplot.set_data(velocity, flux, error, display_half_width_kms=50.0)
    subplot.set_residual(velocity, residual)

    state = subplot.render_state()

    assert state.placeholder_visible is False
    assert state.residual_visible is True
    qtbot.wait(0)


def test_applied_render_input_emphasises_the_selected_component_marker(qtbot: QtBot) -> None:
    """A slice marked as selected upstream draws its marker emphasised."""
    subplot = VelocitySubplotWidget()
    _LIVE_SUBPLOTS.append(subplot)

    slice_info = VelocitySliceInfo(
        rest_wavelength=1215.67,
        label="Lyα",
        tie_group_key="",
        center_z=0.0,
        analysis_half_width_kms=150.0,
        components=[
            VelocityComponentInfo(
                component_id="abs-1",
                velocity=-10.0,
                rest_wavelength=1215.67,
                label="HI a",
                color="#1B9E77",
            ),
            VelocityComponentInfo(
                component_id="abs-2",
                velocity=10.0,
                rest_wavelength=1215.67,
                label="HI b",
                selected=True,
                color="#D95F02",
            ),
        ],
    )
    observed = VelocitySpectrumData(
        wavelength=np.linspace(1215.0, 1216.3, 40, dtype=np.float64),
        flux=np.ones(40, dtype=np.float64),
        error=None,
    )

    subplot.apply_render_input(
        build_velocity_slice_render_input(
            slice_info,
            sources=VelocityCurveSources(observed=observed, model=None),
            display_half_width=VelocityDisplayHalfWidth(500.0),
            unit="km/s",
            optimize_mode=True,
        ),
        {},
    )

    assert subplot.render_state().emphasized_marker_labels == ("HI b",)
    qtbot.wait(0)
