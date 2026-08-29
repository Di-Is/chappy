"""Matplotlib mouse event bridge for spectrum plots."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from matplotlib.backend_bases import Event, LocationEvent, MouseEvent

if TYPE_CHECKING:
    from matplotlib.figure import Figure


class MatplotlibMouseEventHandler(Protocol):
    """Mouse event handler surface implemented by the plot widget."""

    def handle_mouse_press(self, event: MouseEvent) -> None:
        """Handle a Matplotlib mouse press event."""

    def handle_mouse_release(self, event: MouseEvent) -> None:
        """Handle a Matplotlib mouse release event."""

    def handle_mouse_motion(self, event: MouseEvent) -> None:
        """Handle a Matplotlib mouse motion event."""

    def handle_axes_leave(self, event: LocationEvent) -> None:
        """Handle an axes leave event.

        Matplotlib delivers ``axes_leave_event`` as a ``LocationEvent`` rather
        than a ``MouseEvent``, so the leave surface is typed accordingly.
        """


class MatplotlibEventBridge:
    """Connect Matplotlib mouse events to a narrow handler surface."""

    def __init__(self, figure: Figure, handler: MatplotlibMouseEventHandler) -> None:
        """Initialize the bridge.

        Args:
            figure: Matplotlib figure to connect.
            handler: Event handler surface.
        """
        self._figure = figure
        self._handler = handler
        self._connection_ids: list[int] = []

    def connect(self) -> None:
        """Connect Matplotlib mouse events."""
        self.disconnect()
        canvas = self._figure.canvas
        self._connection_ids = [
            canvas.mpl_connect("button_press_event", self._on_mouse_press),
            canvas.mpl_connect("button_release_event", self._on_mouse_release),
            canvas.mpl_connect("motion_notify_event", self._on_mouse_motion),
            canvas.mpl_connect("axes_leave_event", self._on_axes_leave),
        ]

    def disconnect(self) -> None:
        """Disconnect Matplotlib callbacks."""
        canvas = self._figure.canvas
        for connection_id in self._connection_ids:
            canvas.mpl_disconnect(connection_id)
        self._connection_ids.clear()

    def _on_mouse_press(self, event: Event) -> None:
        """Forward a mouse press event.

        Args:
            event: Matplotlib event.
        """
        self._handler.handle_mouse_press(self._mouse_event(event))

    def _on_mouse_release(self, event: Event) -> None:
        """Forward a mouse release event.

        Args:
            event: Matplotlib event.
        """
        self._handler.handle_mouse_release(self._mouse_event(event))

    def _on_mouse_motion(self, event: Event) -> None:
        """Forward a mouse motion event.

        Args:
            event: Matplotlib event.
        """
        self._handler.handle_mouse_motion(self._mouse_event(event))

    def _on_axes_leave(self, event: Event) -> None:
        """Forward an axes leave event.

        Args:
            event: Matplotlib event.
        """
        self._handler.handle_axes_leave(self._location_event(event))

    @staticmethod
    def _mouse_event(event: Event) -> MouseEvent:
        """Return a Matplotlib mouse event or fail on callback mismatch."""
        if isinstance(event, MouseEvent):
            return event
        msg = f"Expected Matplotlib MouseEvent, got {type(event).__name__}."
        raise TypeError(msg)

    @staticmethod
    def _location_event(event: Event) -> LocationEvent:
        """Return a Matplotlib location event or fail on callback mismatch.

        ``axes_leave_event`` is delivered as a ``LocationEvent``; a ``MouseEvent``
        is also accepted because it is a subtype.
        """
        if isinstance(event, LocationEvent):
            return event
        msg = f"Expected Matplotlib LocationEvent, got {type(event).__name__}."
        raise TypeError(msg)
