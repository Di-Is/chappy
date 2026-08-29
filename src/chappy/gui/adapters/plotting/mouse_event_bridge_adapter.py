"""Matplotlib-to-Qt mouse event bridge adapter for spectrum plotting."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget

from chappy.plotting.matplotlib_event_bridge import MatplotlibEventBridge

if TYPE_CHECKING:
    from collections.abc import Callable

    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

    from chappy.plotting.matplotlib_spectrum_plot_facade import (
        MatplotlibMouseEventBridge,
        SpectrumMouseInputPort,
    )


logger = logging.getLogger(__name__)

MouseEventType = Literal["press", "release", "move"]


@runtime_checkable
class MatplotlibLocationEvent(Protocol):
    """Protocol for Matplotlib location events (axes leave, etc.).

    ``axes_leave_event`` delivers a ``LocationEvent`` that lacks ``button``, so it
    is modelled separately from :class:`MatplotlibMouseEvent`.
    """

    inaxes: object | None
    x: float
    y: float


@runtime_checkable
class MatplotlibMouseEvent(Protocol):
    """Protocol for Matplotlib mouse events used by the bridge."""

    inaxes: object | None
    x: float
    y: float
    xdata: float | None
    button: int
    guiEvent: object | None  # noqa: N815


@runtime_checkable
class MatplotlibDoubleClickMouseEvent(Protocol):
    """Protocol for Matplotlib mouse events with double-click metadata."""

    dblclick: bool


@runtime_checkable
class MatplotlibGuiEvent(Protocol):
    """Protocol for backend mouse events exposing keyboard modifiers."""

    def modifiers(self) -> Qt.KeyboardModifier | int:
        """Return keyboard modifier bitmask."""


@runtime_checkable
class MatplotlibGuiEventHost(Protocol):
    """Protocol for Matplotlib events exposing a ``guiEvent``."""

    guiEvent: object  # noqa: N815


# Matplotlib mouse button codes
MATLOTLIB_LEFT_BUTTON = 1
MATLOTLIB_MIDDLE_BUTTON = 2
MATLOTLIB_RIGHT_BUTTON = 3


class MatplotlibMouseEventBridgeAdapter:
    """Forward Matplotlib mouse events into typed Qt mouse events for interactor routing."""

    def __init__(
        self,
        *,
        figure: Figure,
        axes: Axes,
        canvas: object,
        get_interactor: Callable[[], SpectrumMouseInputPort],
        should_forward: Callable[[], bool],
    ) -> None:
        """Initialize the plotting event adapter.

        Args:
            figure: Matplotlib figure containing callbacks.
            axes: Matplotlib axes that owns forwarding logic.
            canvas: Qt canvas used to convert coordinates.
            get_interactor: Callback returning the current interactor sink.
            should_forward: Whether to forward non-wheel events this instance.
        """
        if not isinstance(canvas, QWidget):
            msg = "MatplotlibMouseEventBridgeAdapter requires a QWidget canvas."
            raise TypeError(msg)
        self._axes = axes
        self._canvas = canvas
        self._get_interactor = get_interactor
        self._should_forward = should_forward
        self._event_bridge = MatplotlibEventBridge(figure, self)

    def connect(self) -> None:
        """Connect Matplotlib callbacks."""
        self._event_bridge.connect()

    def disconnect(self) -> None:
        """Disconnect Matplotlib callbacks."""
        self._event_bridge.disconnect()

    def handle_mouse_press(self, event: object) -> None:
        """Bridge Matplotlib button press events."""
        if not (isinstance(event, MatplotlibMouseEvent) and event.inaxes == self._axes):
            return
        if isinstance(event, MatplotlibMouseEvent) and self._is_double_click(event):
            self.handle_double_click_centering(event)
            return
        self.forward_mouse_event(event, "press")

    def handle_mouse_release(self, event: object) -> None:
        """Bridge Matplotlib button release events."""
        if not (isinstance(event, MatplotlibMouseEvent) and event.inaxes == self._axes):
            return
        self.forward_mouse_event(event, "release")

    def handle_mouse_motion(self, event: object) -> None:
        """Bridge Matplotlib motion events."""
        if not (isinstance(event, MatplotlibMouseEvent) and event.inaxes == self._axes):
            return
        self.forward_mouse_event(event, "move")

    def handle_axes_leave(self, event: object) -> None:
        """Handle axis-leave events.

        Matplotlib delivers ``axes_leave_event`` as a ``LocationEvent`` (no
        ``button``), so it is matched against the location-event protocol.
        """
        if not isinstance(event, MatplotlibLocationEvent):
            return
        self._require_interactor().handle_mouse_leave()

    def handle_double_click_centering(self, event: object) -> None:
        """Handle double-click center commands."""
        if not isinstance(event, MatplotlibMouseEvent):
            return
        wavelength = event.xdata
        if wavelength is None:
            return
        self._require_interactor().handle_double_click_center(float(wavelength))
        logger.debug("🎯 Double-click centering at wavelength=%.2f", wavelength)

    def forward_mouse_event(self, event: object, event_type: MouseEventType) -> None:
        """Translate and forward a Matplotlib mouse event to Qt interactor methods."""
        if not self._should_forward():
            return
        if not isinstance(event, MatplotlibMouseEvent):
            return

        if event_type == "move":
            logger.debug(
                "forward_mouse_event: action=%s, x=%.1f, y=%.1f", event_type, event.x, event.y
            )

        try:
            x = event.x
            y = event.y
            button = event.button

            qt_button = Qt.MouseButton.NoButton
            if button == MATLOTLIB_LEFT_BUTTON:
                qt_button = Qt.MouseButton.LeftButton
            elif button == MATLOTLIB_MIDDLE_BUTTON:
                qt_button = Qt.MouseButton.MiddleButton
            elif button == MATLOTLIB_RIGHT_BUTTON:
                qt_button = Qt.MouseButton.RightButton

            dpi_ratio = self._canvas.devicePixelRatio()
            canvas_width = self._canvas.width()
            canvas_height = self._canvas.height()

            widget_x = round(x / dpi_ratio)
            widget_y = round(canvas_height - (y / dpi_ratio))

            widget_x = max(0, min(widget_x, canvas_width - 1))
            widget_y = max(0, min(widget_y, canvas_height - 1))

            pos = QPoint(widget_x, widget_y)
            global_pos = self._canvas.mapToGlobal(pos)
            modifiers = self._read_keyboard_modifiers(event)

            if event_type == "move":
                qt_event = QMouseEvent(
                    QMouseEvent.Type.MouseMove,
                    pos,
                    global_pos,
                    Qt.MouseButton.NoButton,
                    Qt.MouseButton.NoButton,
                    modifiers,
                )
            else:
                qt_event = QMouseEvent(
                    QMouseEvent.Type.MouseButtonPress
                    if event_type == "press"
                    else QMouseEvent.Type.MouseButtonRelease,
                    pos,
                    global_pos,
                    qt_button,
                    qt_button,
                    modifiers,
                )

            interactor = self._require_interactor()
            if event_type == "press":
                interactor.handle_mouse_press_event(qt_event)
            elif event_type == "release":
                interactor.handle_mouse_release_event(qt_event)
            elif event_type == "move":
                interactor.handle_mouse_move_event(qt_event)
            logger.debug(
                "  ✅ Forwarded %s event at (%.1f, %.1f) button=%s", event_type, x, y, button
            )
        except (AttributeError, RuntimeError) as error:
            logger.debug("Failed to forward mouse event: %s", error)

    @staticmethod
    def _is_double_click(event: object) -> bool:
        """Check whether a Matplotlib event is a double-click."""
        return isinstance(event, MatplotlibDoubleClickMouseEvent) and bool(event.dblclick)

    @staticmethod
    def _read_keyboard_modifiers(event: object) -> Qt.KeyboardModifier:
        """Return modifiers from backend ``guiEvent`` or Qt keyboard state."""
        modifiers = QApplication.keyboardModifiers()
        gui_event = MatplotlibMouseEventBridgeAdapter._matplotlib_gui_event(event)
        if gui_event is None:
            return modifiers
        try:
            backend_modifiers = gui_event.modifiers()
        except (AttributeError, RuntimeError, TypeError):
            logger.debug("Unable to read modifiers from guiEvent; using QApplication modifiers")
            return modifiers

        if isinstance(backend_modifiers, Qt.KeyboardModifier):
            return backend_modifiers
        if isinstance(backend_modifiers, int):
            try:
                return Qt.KeyboardModifier(backend_modifiers)
            except ValueError:
                logger.debug(
                    "Unable to normalize guiEvent modifiers value=%s; using QApplication modifiers",
                    backend_modifiers,
                )
                return modifiers
        logger.debug(
            "Ignoring unsupported guiEvent modifiers type=%s; using QApplication modifiers",
            type(backend_modifiers).__name__,
        )
        return modifiers

    @staticmethod
    def _matplotlib_gui_event(event: object) -> MatplotlibGuiEvent | None:
        """Return backend ``guiEvent`` if it exposes ``modifiers``."""
        if not isinstance(event, MatplotlibGuiEventHost):
            return None
        gui_event = event.guiEvent
        if isinstance(gui_event, MatplotlibGuiEvent):
            return gui_event
        return None

    def _require_interactor(self) -> SpectrumMouseInputPort:
        """Return the active spectrum interactor sink."""
        return self._get_interactor()


def create_matplotlib_mouse_event_bridge_adapter(
    *,
    figure: Figure,
    axes: Axes,
    canvas: object,
    get_interactor: Callable[[], SpectrumMouseInputPort],
    should_forward: Callable[[], bool],
) -> MatplotlibMouseEventBridge:
    """Create the Qt mouse event bridge adapter for Matplotlib spectrum plots."""
    return MatplotlibMouseEventBridgeAdapter(
        figure=figure,
        axes=axes,
        canvas=canvas,
        get_interactor=get_interactor,
        should_forward=should_forward,
    )
