"""Tests for Matplotlib event bridge narrowing."""

from __future__ import annotations

import pytest
from matplotlib.backend_bases import Event, LocationEvent, MouseEvent
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from chappy.plotting.matplotlib_event_bridge import MatplotlibEventBridge


class _Handler:
    """Collect bridged mouse events."""

    def __init__(self) -> None:
        """Initialize an empty event collection."""
        self.pressed: MouseEvent | None = None
        self.left: LocationEvent | None = None

    def handle_mouse_press(self, event: MouseEvent) -> None:
        """Store a bridged press event."""
        self.pressed = event

    def handle_mouse_release(self, event: MouseEvent) -> None:
        """Accept a bridged release event."""

    def handle_mouse_motion(self, event: MouseEvent) -> None:
        """Accept a bridged motion event."""

    def handle_axes_leave(self, event: LocationEvent) -> None:
        """Store a bridged axes-leave event."""
        self.left = event


def _bridge() -> tuple[MatplotlibEventBridge, _Handler, FigureCanvasAgg]:
    """Create a bridge with a handler and Agg canvas."""
    figure = Figure()
    canvas = FigureCanvasAgg(figure)
    handler = _Handler()
    return MatplotlibEventBridge(figure, handler), handler, canvas


def test_event_bridge_forwards_mouse_events() -> None:
    """Mouse callbacks should receive the original Matplotlib mouse event."""
    bridge, handler, canvas = _bridge()
    event = MouseEvent("button_press_event", canvas, x=1, y=2)

    bridge._on_mouse_press(event)

    assert handler.pressed is event


def test_event_bridge_rejects_non_mouse_events() -> None:
    """Non-mouse callbacks should fail before reaching the mouse handler."""
    bridge, _handler, canvas = _bridge()
    event = Event("draw_event", canvas)

    with pytest.raises(TypeError, match="Expected Matplotlib MouseEvent"):
        bridge._on_mouse_press(event)


def test_event_bridge_forwards_axes_leave_location_event() -> None:
    """Axes-leave delivers a LocationEvent, which must reach the handler."""
    bridge, handler, canvas = _bridge()
    event = LocationEvent("axes_leave_event", canvas, x=1, y=2)

    bridge._on_axes_leave(event)

    assert handler.left is event


def test_event_bridge_accepts_mouse_event_on_axes_leave() -> None:
    """A MouseEvent is a LocationEvent subtype and is accepted on leave."""
    bridge, handler, canvas = _bridge()
    event = MouseEvent("motion_notify_event", canvas, x=1, y=2)

    bridge._on_axes_leave(event)

    assert handler.left is event


def test_event_bridge_rejects_non_location_events_on_axes_leave() -> None:
    """A bare Event should fail before reaching the leave handler."""
    bridge, _handler, canvas = _bridge()
    event = Event("draw_event", canvas)

    with pytest.raises(TypeError, match="Expected Matplotlib LocationEvent"):
        bridge._on_axes_leave(event)
