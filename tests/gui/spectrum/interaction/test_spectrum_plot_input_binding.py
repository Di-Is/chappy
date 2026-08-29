"""Tests for spectrum plot input binding."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent, QWheelEvent

from chappy.gui.spectrum.interaction.input.binding.spectrum_plot_input_binding import (
    SpectrumPlotInputBinding,
)
from chappy.gui.spectrum.interaction.input.ports import (
    ContinuumInteractionEventSink,
    SpectrumInputAdapterEventSink,
)
from chappy.presentation.interaction.interaction_contracts import InteractionEvent


@dataclass
class _CanvasFake:
    """Canvas surface required by PlotCoordinateTransform."""

    def width(self) -> int:
        """Return a deterministic width."""
        return 800

    def height(self) -> int:
        """Return a deterministic height."""
        return 600

    def devicePixelRatio(self) -> float:  # noqa: N802
        """Return a deterministic device pixel ratio."""
        return 1.0


@dataclass
class _DataTransformFake:
    """Data transform surface required by PlotCoordinateTransform."""

    def transform(self, _position: tuple[float, float]) -> tuple[float, float]:
        """Return deterministic data coordinates."""
        return (5000.0, 1.0)


@dataclass
class _TransDataFake:
    """Invertible transform surface required by PlotCoordinateTransform."""

    def inverted(self) -> _DataTransformFake:
        """Return the inverse transform."""
        return _DataTransformFake()


@dataclass
class _AxesFake:
    """Axes surface required by PlotCoordinateTransform."""

    transData: _TransDataFake = field(default_factory=_TransDataFake)


@dataclass
class _RendererFake:
    """Renderer surface required by PlotCoordinateTransform."""

    axes: _AxesFake | None = field(default_factory=_AxesFake)


@dataclass
class _PlotWidgetFake:
    """Plot widget fake for binding tests."""

    canvas: _CanvasFake = field(default_factory=_CanvasFake)
    renderer: _RendererFake = field(default_factory=_RendererFake)
    mouse_input: SpectrumInputAdapterEventSink | None = None
    continuum_input: ContinuumInteractionEventSink | None = None
    cursors: list[Qt.CursorShape] = field(default_factory=list)
    continuum_values: list[tuple[float, float]] = field(default_factory=list)
    detected_wavelengths: list[float] = field(default_factory=list)
    absorber_id: str | None = None

    def set_input_ports(
        self,
        *,
        mouse: SpectrumInputAdapterEventSink | None,
        continuum: ContinuumInteractionEventSink | None,
    ) -> None:
        """Record the attached input ports."""
        self.mouse_input = mouse
        self.continuum_input = continuum

    def continuum_points(self) -> list[tuple[float, float]]:
        """Return configured continuum points."""
        return list(self.continuum_values)

    def get_absorber_at_position(self, wavelength: float) -> str | None:
        """Return configured absorber id."""
        self.detected_wavelengths.append(wavelength)
        return self.absorber_id

    def setCursor(self, cursor: Qt.CursorShape) -> None:  # noqa: N802
        """Record cursor changes."""
        self.cursors.append(cursor)

    def mapFromGlobal(self, _position: QPoint) -> QPointF:  # noqa: N802
        """Map global position to local position."""
        return QPointF(10.0, 20.0)


@dataclass
class _EventSinkFake:
    """Event sink fake for binding forwarding tests."""

    mouse_event_count: int = 0
    mouse_leave_count: int = 0
    centered_wavelengths: list[float] = field(default_factory=list)
    press_event_count: int = 0
    release_event_count: int = 0
    move_event_count: int = 0
    continuum_events: list[InteractionEvent] = field(default_factory=list)

    def process_mouse_event(self, _event: QMouseEvent | QWheelEvent) -> None:
        """Record a forwarded mouse or wheel event."""
        self.mouse_event_count += 1

    def handle_mouse_leave(self) -> None:
        """Record a forwarded mouse leave event."""
        self.mouse_leave_count += 1

    def handle_double_click_center(self, wavelength: float) -> None:
        """Record a forwarded double-click center request."""
        self.centered_wavelengths.append(wavelength)

    def handle_mouse_press_event(self, _event: QMouseEvent) -> bool:
        """Record a forwarded mouse press event."""
        self.press_event_count += 1
        return True

    def handle_mouse_release_event(self, _event: QMouseEvent) -> bool:
        """Record a forwarded mouse release event."""
        self.release_event_count += 1
        return True

    def handle_mouse_move_event(self, _event: QMouseEvent) -> bool:
        """Record a forwarded mouse move event."""
        self.move_event_count += 1
        return True

    def can_process_continuum_event(self) -> bool:
        """Allow continuum events."""
        return True

    def process_continuum_interaction_event(self, event: InteractionEvent) -> bool:
        """Record a continuum interaction event."""
        self.continuum_events.append(event)
        return True


def test_attach_initializes_transform_and_detaches_old_widget() -> None:
    """Attach should initialize transform and detach a replaced widget."""
    binding = SpectrumPlotInputBinding()
    old_plot = _PlotWidgetFake()
    new_plot = _PlotWidgetFake()
    event_sink = _EventSinkFake()

    binding.attach_plot_widget(old_plot, event_sink=event_sink)
    binding.attach_plot_widget(new_plot, event_sink=event_sink)

    assert binding.plot_widget is new_plot
    assert binding.coord_transform is not None
    assert new_plot.mouse_input is binding
    assert new_plot.continuum_input is event_sink
    assert old_plot.mouse_input is None
    assert old_plot.continuum_input is None


def test_detach_clears_widget_and_transform() -> None:
    """Detach should clear plot widget and coordinate transform."""
    binding = SpectrumPlotInputBinding()
    plot = _PlotWidgetFake()
    binding.attach_plot_widget(plot, event_sink=_EventSinkFake())

    binding.detach_plot_widget()

    assert binding.plot_widget is None
    assert binding.coord_transform is None
    assert plot.mouse_input is None
    assert plot.continuum_input is None


def test_continuum_points_requires_attached_plot() -> None:
    """Continuum points require an attached plot widget."""
    binding = SpectrumPlotInputBinding()

    with pytest.raises(RuntimeError, match="Plot widget is required"):
        binding.continuum_points()


def test_cursor_absorber_and_continuum_delegate_to_plot() -> None:
    """Plot-bound operations should delegate to the attached plot widget."""
    binding = SpectrumPlotInputBinding()
    plot = _PlotWidgetFake(continuum_values=[(4000.0, 1.0)], absorber_id="abs-1")
    binding.attach_plot_widget(plot, event_sink=_EventSinkFake())

    binding.set_cursor(True)
    binding.set_cursor(False)

    assert binding.continuum_points() == [(4000.0, 1.0)]
    assert binding.absorber_at_wavelength(4100.0) == "abs-1"
    assert plot.detected_wavelengths == [4100.0]
    assert plot.cursors == [Qt.CursorShape.CrossCursor, Qt.CursorShape.ArrowCursor]


def test_forwards_plot_input_to_event_sink() -> None:
    """Binding should forward plot event sink calls to the configured sink."""
    binding = SpectrumPlotInputBinding()
    plot = _PlotWidgetFake()
    event_sink = _EventSinkFake()

    binding.attach_plot_widget(plot, event_sink=event_sink)

    assert plot.mouse_input is binding
    assert plot.continuum_input is event_sink

    plot.mouse_input.handle_mouse_leave()
    plot.mouse_input.handle_double_click_center(5100.0)

    assert event_sink.mouse_leave_count == 1
    assert event_sink.centered_wavelengths == [5100.0]


def test_forwarding_without_event_sink_raises() -> None:
    """Forwarding should fail clearly when no event sink is attached."""
    binding = SpectrumPlotInputBinding()

    with pytest.raises(RuntimeError, match="Event sink is required"):
        binding.handle_mouse_leave()
