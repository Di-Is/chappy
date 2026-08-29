"""Integration tests for SpectrumInputAdapter with SpectrumView."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import numpy as np
import pytest
from PySide6.QtCore import Qt

from chappy.core.editing_mode import EditingMode
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.core.spectrum import Spectrum
from chappy.gui.shell.spectrum_mode_policy import spectrum_interaction_mode_policy

if TYPE_CHECKING:
    from PySide6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent

    from chappy.gui.spectrum.spectrum_view import SpectrumView


@pytest.fixture
def spectrum_view(qtbot) -> SpectrumView:
    """Create SpectrumView instance for testing."""
    from chappy.gui.spectrum.spectrum_plot import create_default_spectrum_plot_host_factory
    from chappy.gui.spectrum.spectrum_view import SpectrumView

    view = SpectrumView(plot_host_factory=create_default_spectrum_plot_host_factory())
    project = SpectroscopyProject(name="interactor-integration")
    wavelength = np.array([1000.0, 1001.0, 1002.0])
    flux = np.array([1.0, 0.9, 0.8])
    project.model.set_observed_spectrum(Spectrum(wavelength=wavelength, flux=flux))
    view.data_bridge.set_project(project)
    view.data_bridge.set_wavelength_range(1000.0, 1002.0)
    view.data_bridge.set_flux_range(0.8, 1.0)
    qtbot.addWidget(view)
    return view


def _record_key_events(spectrum_view: SpectrumView) -> list[QKeyEvent]:
    """Wrap process_key_event and record routed key events."""
    events: list[QKeyEvent] = []
    original: Callable[[QKeyEvent], object] = (
        spectrum_view.spectrum_input_adapter.process_key_event
    )

    def _record(event: QKeyEvent) -> object:
        events.append(event)
        return original(event)

    spectrum_view.spectrum_input_adapter.process_key_event = _record
    return events


def _record_mouse_events(spectrum_view: SpectrumView) -> list[QMouseEvent | QWheelEvent]:
    """Wrap process_mouse_event and record routed mouse events."""
    events: list[QMouseEvent | QWheelEvent] = []
    original: Callable[[QMouseEvent | QWheelEvent], object] = (
        spectrum_view.spectrum_input_adapter.process_mouse_event
    )

    def _record(event: QMouseEvent | QWheelEvent) -> object:
        events.append(event)
        return original(event)

    spectrum_view.spectrum_input_adapter.process_mouse_event = _record
    return events


def test_spectrum_input_adapter_created(spectrum_view: SpectrumView) -> None:
    """Test that SpectrumInputAdapter is created and connected."""
    # Check interactor exists
    assert hasattr(spectrum_view, "spectrum_input_adapter")
    assert spectrum_view.spectrum_input_adapter is not None

    assert spectrum_view.coordinator.interactor is spectrum_view.spectrum_input_adapter


def test_key_event_routing_to_interactor(spectrum_view: SpectrumView, qtbot) -> None:
    """Test that key events are routed to SpectrumInputAdapter."""
    events = _record_key_events(spectrum_view)

    # Send a key press event
    qtbot.keyPress(spectrum_view, Qt.Key.Key_Plus)

    # Verify interactor received the event
    assert len(events) == 1


def test_canvas_shift_release_reaches_identify_preview_signal(
    spectrum_view: SpectrumView, qtbot
) -> None:
    """Releasing Shift over the focused canvas clears preview state immediately."""
    spectrum_view.spectrum_input_adapter.set_mode_capabilities(
        spectrum_interaction_mode_policy(EditingMode.IDENTIFY).input_capabilities
    )
    released: list[bool] = []
    spectrum_view.identify_preview_shift_released.connect(lambda: released.append(True))
    plot_widget = spectrum_view.plot_host.plot_widget
    assert plot_widget is not None
    plot_widget.canvas.setFocus()

    qtbot.keyPress(plot_widget.canvas, Qt.Key.Key_Shift)
    qtbot.keyRelease(plot_widget.canvas, Qt.Key.Key_Shift)

    assert released == [True]


def test_zoom_intent_signal_emission(spectrum_view: SpectrumView, qtbot) -> None:
    """Test that zoom intent signals are emitted."""
    from chappy.gui.protocols.intent_types import ZoomFactorIntent

    # Connect a signal spy
    signal_received = []
    spectrum_view.spectrum_input_adapter.sig_zoom_requested.connect(
        lambda intent: signal_received.append(intent)
    )

    # Manually emit a zoom intent
    test_intent = ZoomFactorIntent(factor=1.5)
    spectrum_view.spectrum_input_adapter.sig_zoom_requested.emit(test_intent)

    # Verify signal was received
    assert len(signal_received) == 1
    assert signal_received[0] == test_intent
    assert signal_received[0].factor == 1.5


def test_wheel_event_routing(spectrum_view: SpectrumView, qtbot) -> None:
    """Test that wheel events are routed to SpectrumInputAdapter."""
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtCore import QPointF

    events = _record_mouse_events(spectrum_view)

    # Create a wheel event manually
    center = spectrum_view.rect().center()
    from PySide6.QtCore import QPoint

    wheel_event = QWheelEvent(
        QPointF(center),  # position
        QPointF(center),  # globalPosition
        QPoint(0, 0),  # pixelDelta (must be QPoint, not QPointF)
        QPoint(0, 120),  # angleDelta (must be QPoint, not QPointF)
        Qt.MouseButton.NoButton,  # buttons
        Qt.KeyboardModifier.NoModifier,  # modifiers
        Qt.ScrollPhase.NoScrollPhase,  # phase
        False,  # inverted
    )

    # Call wheelEvent directly
    spectrum_view.wheelEvent(wheel_event)

    # Verify interactor received the event
    assert events == [wheel_event]


def test_canvas_wheel_event_routing_to_interactor(spectrum_view: SpectrumView, qtbot) -> None:
    """Wheel events on the Matplotlib canvas must reach the interactor."""
    from PySide6.QtCore import QPoint, QPointF
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication

    plot_widget = spectrum_view.plot_host.plot_widget
    assert plot_widget is not None

    events = _record_mouse_events(spectrum_view)

    local_center = plot_widget.canvas.rect().center()
    local_pos = QPointF(local_center)
    global_pos = QPointF(plot_widget.canvas.mapToGlobal(local_center))

    wheel_event = QWheelEvent(
        local_pos,
        global_pos,
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )

    QApplication.sendEvent(plot_widget.canvas, wheel_event)

    assert events == [wheel_event]


def test_intent_to_coordinator_connection(spectrum_view: SpectrumView) -> None:
    """Test that intent signals are connected to coordinator methods."""
    # Test that signals emit properly by connecting test slots
    zoom_received = []
    pan_received = []
    absorber_received = []

    spectrum_view.spectrum_input_adapter.sig_zoom_requested.connect(
        lambda x: zoom_received.append(x)
    )
    spectrum_view.spectrum_input_adapter.sig_pan_requested.connect(
        lambda x: pan_received.append(x)
    )
    spectrum_view.spectrum_input_adapter.sig_absorber_action.connect(
        lambda x: absorber_received.append(x)
    )

    # Emit test signals
    from chappy.gui.protocols.intent_types import PanIntent, SelectAbsorberIntent, ZoomFactorIntent

    spectrum_view.spectrum_input_adapter.sig_zoom_requested.emit(ZoomFactorIntent(factor=2.0))
    spectrum_view.spectrum_input_adapter.sig_pan_requested.emit(PanIntent(fraction=0.1))
    spectrum_view.spectrum_input_adapter.sig_absorber_action.emit(SelectAbsorberIntent())

    # Verify signals were received
    assert len(zoom_received) == 1
    assert len(pan_received) == 1
    assert len(absorber_received) == 1

    assert hasattr(spectrum_view.coordinator, "handle_navigation_intent")
    assert hasattr(spectrum_view.coordinator, "coordinate_absorber_intent")


def test_plot_widget_configuration(spectrum_view: SpectrumView) -> None:
    """Test that plot widget is set on interactor for coordinate transform."""
    assert spectrum_view.plot_host.plot_widget is not None
    assert spectrum_view.spectrum_input_adapter.coord_transform is not None
