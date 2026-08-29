"""Tests for velocity-overlay isolation from wavelength-spectrum navigation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import numpy as np
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent

from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.core.spectrum import Spectrum
from chappy.gui.spectrum.spectrum_plot import create_default_spectrum_plot_host_factory
from chappy.gui.spectrum.spectrum_view import SpectrumView
from chappy.gui.spectrum.velocity import VelocityDisplayHalfWidthSpinBox
from chappy.presentation.velocity import (
    VelocityDisplayScopeKey,
    VelocityOverlayInfo,
    VelocitySliceInfo,
)

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

type VelocityContext = Literal["identify", "optimize"]


def _build_view(qtbot: QtBot) -> SpectrumView:
    wavelength = np.linspace(1200.0, 1230.0, 101)
    project = SpectroscopyProject()
    project.model.set_observed_spectrum(
        Spectrum(
            wavelength=wavelength,
            flux=np.linspace(0.8, 1.0, wavelength.size),
            error=np.full(wavelength.size, 0.1),
        )
    )
    view = SpectrumView(
        plot_host_factory=create_default_spectrum_plot_host_factory(), project=project
    )
    qtbot.addWidget(view)
    view.set_wavelength_fields_enabled_callback(lambda _enabled: None)
    view.resize(900, 600)
    view.show()
    return view


def _activate_velocity_plot(view: SpectrumView, context: VelocityContext) -> None:
    view.set_velocity_plot_active(
        True,
        VelocityOverlayInfo(
            center_z=0.0,
            rest_wavelength=1215.67,
            display_range_scope_key=VelocityDisplayScopeKey(f"test:{context}"),
            analysis_half_widths_kms=(150.0,),
            slices=[
                VelocitySliceInfo(
                    rest_wavelength=1215.67,
                    label="Ly alpha",
                    tie_group_key="",
                    line_id="lya",
                    center_z=0.0,
                    analysis_half_width_kms=150.0,
                )
            ],
        ),
        context=context,
    )


def _wheel_event(delta: QPoint) -> QWheelEvent:
    position = QPointF(300.0, 300.0)
    return QWheelEvent(
        position,
        position,
        QPoint(),
        delta,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )


@pytest.mark.parametrize("context", ["identify", "optimize"])
def test_velocity_plot_blocks_spectrum_keyboard_navigation(
    qtbot: QtBot, context: VelocityContext
) -> None:
    """Navigation keys over either velocity surface must not reach the spectrum."""
    view = _build_view(qtbot)
    _activate_velocity_plot(view, context)
    qtbot.wait(0)
    zoom_requests: list[object] = []
    pan_requests: list[object] = []
    absorber_requests: list[object] = []
    view.spectrum_input_adapter.sig_zoom_requested.connect(zoom_requests.append)
    view.spectrum_input_adapter.sig_pan_requested.connect(pan_requests.append)
    view.spectrum_input_adapter.sig_absorber_action.connect(absorber_requests.append)
    overlay = view.velocity_view
    assert overlay is not None

    for key in (
        Qt.Key.Key_Up,
        Qt.Key.Key_Down,
        Qt.Key.Key_Left,
        Qt.Key.Key_Right,
        Qt.Key.Key_N,
        Qt.Key.Key_P,
    ):
        qtbot.keyClick(overlay, key)

    assert zoom_requests == []
    assert pan_requests == []
    assert absorber_requests == []


@pytest.mark.parametrize("context", ["identify", "optimize"])
def test_velocity_plot_blocks_spectrum_wheel_navigation(
    qtbot: QtBot, context: VelocityContext
) -> None:
    """Vertical and horizontal wheel gestures must not navigate the hidden spectrum."""
    view = _build_view(qtbot)
    _activate_velocity_plot(view, context)
    qtbot.wait(0)
    zoom_requests: list[object] = []
    pan_requests: list[object] = []
    view.spectrum_input_adapter.sig_zoom_requested.connect(zoom_requests.append)
    view.spectrum_input_adapter.sig_pan_requested.connect(pan_requests.append)
    original_range = view.get_wavelength_range()

    vertical = _wheel_event(QPoint(0, 120))
    horizontal = _wheel_event(QPoint(120, 0))
    view.wheelEvent(vertical)
    view.wheelEvent(horizontal)

    assert vertical.isAccepted() is True
    assert horizontal.isAccepted() is True
    assert zoom_requests == []
    assert pan_requests == []
    assert view.get_wavelength_range() == original_range


@pytest.mark.parametrize("context", ["identify", "optimize"])
def test_velocity_display_input_keeps_its_key_and_wheel_steps(
    qtbot: QtBot, context: VelocityContext
) -> None:
    """Overlay-local display controls must remain interactive while navigation is blocked."""
    view = _build_view(qtbot)
    _activate_velocity_plot(view, context)
    qtbot.wait(0)
    zoom_requests: list[object] = []
    view.spectrum_input_adapter.sig_zoom_requested.connect(zoom_requests.append)
    spinbox = view.findChild(VelocityDisplayHalfWidthSpinBox, "velocityDisplayHalfWidthSpinBox")
    assert spinbox is not None
    initial_value = spinbox.accepted_value.value

    spinbox.setFocus()
    qtbot.keyClick(spinbox, Qt.Key.Key_Up)
    spinbox.wheelEvent(_wheel_event(QPoint(0, 120)))

    assert spinbox.accepted_value.value == initial_value + (2 * spinbox.singleStep())
    assert zoom_requests == []


def test_spectrum_navigation_remains_enabled_without_velocity_plot(qtbot: QtBot) -> None:
    """The isolation must not change ordinary spectrum navigation."""
    view = _build_view(qtbot)
    zoom_requests: list[object] = []
    pan_requests: list[object] = []
    view.spectrum_input_adapter.sig_zoom_requested.connect(zoom_requests.append)
    view.spectrum_input_adapter.sig_pan_requested.connect(pan_requests.append)

    qtbot.keyClick(view, Qt.Key.Key_Up)
    view.wheelEvent(_wheel_event(QPoint(120, 0)))

    assert len(zoom_requests) == 1
    assert len(pan_requests) == 1
