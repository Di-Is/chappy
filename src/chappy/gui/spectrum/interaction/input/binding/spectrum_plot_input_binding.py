"""Plot-widget binding for spectrum input adapters."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent, QWheelEvent

from chappy.gui.protocols.interaction_overlay import InteractionOverlayProtocol
from chappy.gui.spectrum.interaction.input.ports import (
    SpectrumInputAdapterEventSink,
    SpectrumInputPorts,
    SpectrumPlotWidgetPort,
)
from chappy.gui.utils.plot_coordinate_transform import PlotCoordinateTransform


class SpectrumPlotInputBinding:
    """Own plot-widget attachment and coordinate transform state."""

    def __init__(self) -> None:
        """Initialize an empty plot binding."""
        self.coord_transform: PlotCoordinateTransform | None = None
        self._plot_widget: SpectrumPlotWidgetPort | None = None
        self._event_sink: SpectrumInputAdapterEventSink | None = None

    @property
    def plot_widget(self) -> SpectrumPlotWidgetPort | None:
        """Return the currently attached plot widget."""
        return self._plot_widget

    def attach_plot_widget(
        self, plot_widget: SpectrumPlotWidgetPort, *, event_sink: SpectrumInputPorts
    ) -> None:
        """Attach a required plot widget and initialize coordinate transform."""
        if not isinstance(plot_widget, SpectrumPlotWidgetPort):
            msg = (
                "Plot widget must implement renderer, canvas, continuum point, absorber "
                "lookup, and interactor attachment ports."
            )
            raise TypeError(msg)

        if self._plot_widget is not None and id(plot_widget) != id(self._plot_widget):
            self._plot_widget.set_input_ports(mouse=None, continuum=None)
            self._plot_widget = None

        self.coord_transform = PlotCoordinateTransform(plot_widget)
        self._plot_widget = plot_widget
        self._event_sink = event_sink
        plot_widget.set_input_ports(mouse=self, continuum=event_sink)

    def detach_plot_widget(self) -> None:
        """Detach the current plot widget and clear coordinate transform."""
        if self._plot_widget is not None:
            self._plot_widget.set_input_ports(mouse=None, continuum=None)
        self._plot_widget = None
        self._event_sink = None
        self.coord_transform = None

    def process_mouse_event(self, event: object) -> None:
        """Forward mouse or wheel events to the active event sink."""
        if not isinstance(event, (QMouseEvent, QWheelEvent)):
            msg = "Plot input binding requires a Qt mouse or wheel event."
            raise TypeError(msg)
        self._require_event_sink().process_mouse_event(event)

    def handle_mouse_leave(self) -> None:
        """Forward cursor-leave events to the active event sink."""
        self._require_event_sink().handle_mouse_leave()

    def handle_double_click_center(self, wavelength: float) -> None:
        """Forward double-click centering to the active event sink."""
        self._require_event_sink().handle_double_click_center(wavelength)

    def handle_mouse_press_event(self, event: object) -> bool:
        """Forward mouse press events to the active event sink."""
        if not isinstance(event, QMouseEvent):
            msg = "Plot input binding requires a Qt mouse press event."
            raise TypeError(msg)
        return self._require_event_sink().handle_mouse_press_event(event)

    def handle_mouse_release_event(self, event: object) -> bool:
        """Forward mouse release events to the active event sink."""
        if not isinstance(event, QMouseEvent):
            msg = "Plot input binding requires a Qt mouse release event."
            raise TypeError(msg)
        return self._require_event_sink().handle_mouse_release_event(event)

    def handle_mouse_move_event(self, event: object) -> bool:
        """Forward mouse move events to the active event sink."""
        if not isinstance(event, QMouseEvent):
            msg = "Plot input binding requires a Qt mouse move event."
            raise TypeError(msg)
        return self._require_event_sink().handle_mouse_move_event(event)

    def interaction_overlay(self) -> InteractionOverlayProtocol | None:
        """Return the plot overlay implementation if available."""
        if isinstance(self._plot_widget, InteractionOverlayProtocol):
            return self._plot_widget
        return None

    def continuum_points(self) -> list[tuple[float, float]]:
        """Return the current list of continuum points from the attached plot."""
        if self._plot_widget is None:
            msg = "Plot widget is required to resolve continuum points."
            raise RuntimeError(msg)
        return self._plot_widget.continuum_points()

    def set_cursor(self, active: bool) -> None:
        """Apply crosshair or default cursor feedback."""
        if self._plot_widget is not None:
            self._plot_widget.setCursor(
                Qt.CursorShape.CrossCursor if active else Qt.CursorShape.ArrowCursor
            )

    def absorber_at_wavelength(self, wavelength: float) -> str | None:
        """Return the absorber at a wavelength, if any."""
        if self._plot_widget is None:
            return None
        return self._plot_widget.get_absorber_at_position(wavelength)

    def _require_event_sink(self) -> SpectrumInputAdapterEventSink:
        """Return the event sink attached to the current plot widget."""
        if self._event_sink is None:
            msg = "Event sink is required to forward plot input."
            raise RuntimeError(msg)
        return self._event_sink
