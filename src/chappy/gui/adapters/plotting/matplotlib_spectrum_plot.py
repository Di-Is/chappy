"""Qt widget adapter for the Matplotlib spectrum plot."""
# mypy: disable-error-code="misc"

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from PySide6.QtCore import QT_TRANSLATE_NOOP, QEvent, QObject, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from chappy.gui.adapters.plotting.continuum_editor_adapter import (
    create_matplotlib_continuum_editor_adapter,
)
from chappy.gui.adapters.plotting.matplotlib_renderer_adapter import create_qt_matplotlib_renderer
from chappy.gui.adapters.plotting.mouse_event_bridge_adapter import (
    create_matplotlib_mouse_event_bridge_adapter,
)
from chappy.i18n import LanguageSwitcher, get_language_switcher
from chappy.plotting.matplotlib_spectrum_plot_facade import (
    MatplotlibContinuumEditorFactory,
    MatplotlibMouseEventBridgeFactory,
    MatplotlibRendererFactory,
    MatplotlibSpectrumPlotCallbacks,
    MatplotlibSpectrumPlotFacade,
)
from chappy.plotting.utils.validators import validate_spectrum_data

if TYPE_CHECKING:
    import numpy as np
    from PySide6.QtGui import QCloseEvent

    from chappy.plotting.matplotlib_spectrum_plot_facade import SpectrumMouseInputPort
    from chappy.plotting.renderers import MatplotlibRenderer

ObservedDataValidator = Callable[
    [
        "np.ndarray[tuple[int, ...], np.dtype[np.float64]] | None",
        "np.ndarray[tuple[int, ...], np.dtype[np.float64]] | None",
        "np.ndarray[tuple[int, ...], np.dtype[np.float64]] | None",
    ],
    bool,
]


@runtime_checkable
class MouseForwardingParent(Protocol):
    """Protocol for parents that control plot mouse forwarding."""

    def blocks_plot_mouse_forwarding(self) -> bool:
        """Return whether plot mouse forwarding should be suppressed."""
        ...


_MATPLOTLIB_SPECTRUM_PLOT_SOURCES = (
    str(QT_TRANSLATE_NOOP("MatplotlibSpectrumPlot", "Wavelength [Å]")),
    str(QT_TRANSLATE_NOOP("MatplotlibSpectrumPlot", "Flux")),
    str(QT_TRANSLATE_NOOP("MatplotlibSpectrumPlot", "Drag to select a masked range")),
    str(QT_TRANSLATE_NOOP("MatplotlibSpectrumPlot", "Continuum Reference")),
)


class MatplotlibSpectrumPlot(MatplotlibSpectrumPlotFacade, QWidget):
    """Concrete Qt widget owning the Matplotlib spectrum plot canvas."""

    range_changed = Signal(float, float, float, float)  # x_min, x_max, y_min, y_max
    selection_changed = Signal(float, float)  # x_min, x_max

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        mouse_event_bridge_factory: MatplotlibMouseEventBridgeFactory | None = None,
        observed_data_validator: ObservedDataValidator | None = None,
        constrained_layout: bool = False,
        tick_labelsize: float | None = None,
        show_axis_labels: bool = True,
    ) -> None:
        """Initialize the Qt plot widget adapter.

        Args:
            parent: Parent widget.
            mouse_event_bridge_factory: Optional GUI-owned mouse event bridge factory.
            observed_data_validator: Optional validator for observed plot data.
            constrained_layout: Size plot margins from rendered tick labels instead of
                fixed figure-relative fractions.
            tick_labelsize: Optional tick label font size in points.
            show_axis_labels: Whether the plot renders its own axis labels.
        """
        QWidget.__init__(self, parent)
        self._constrained_layout = constrained_layout
        self._tick_labelsize = tick_labelsize
        MatplotlibSpectrumPlotFacade.__init__(
            self,
            mouse_event_bridge_factory=mouse_event_bridge_factory
            or create_matplotlib_mouse_event_bridge_adapter,
            continuum_editor_factory=self._create_continuum_editor_factory(),
            renderer_factory=self._create_renderer_factory(),
            callbacks=MatplotlibSpectrumPlotCallbacks(
                attach_canvas=self._install_canvas,
                translate_text=self._translate_text,
                notify_range_changed=self._emit_range_signal,
                notify_selection_changed=self._emit_selection_signal,
                should_forward_mouse_events_to_interactor=self._should_forward_mouse_events,
                set_tooltip=self._set_canvas_tooltip,
            ),
            observed_data_validator=observed_data_validator or validate_spectrum_data,
            show_axis_labels=show_axis_labels,
        )
        self._language_switcher: LanguageSwitcher = get_language_switcher(self)
        self._language_switcher.language_changed.connect(self._on_language_changed)
        self.refresh_translated_text()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Forward Matplotlib canvas wheel events to the shared interactor."""
        interactor: SpectrumMouseInputPort | None = self._mouse_interactor
        if (
            watched is self._qt_canvas()
            and event.type() == QEvent.Type.Wheel
            and interactor is not None
        ):
            interactor.process_mouse_event(event)
            event.accept()
            return True
        return QWidget.eventFilter(self, watched, event)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Release Matplotlib resources when the Qt widget closes."""
        with suppress(RuntimeError):
            self.dispose()
        with suppress(RuntimeError, TypeError):
            self._language_switcher.language_changed.disconnect(self._on_language_changed)
        QWidget.closeEvent(self, event)

    def _install_canvas(self) -> None:
        """Install the Matplotlib canvas in this widget's layout."""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        canvas = self._qt_canvas()
        layout.addWidget(canvas)
        canvas.setContentsMargins(0, 0, 0, 0)

        canvas.setMouseTracking(True)
        self.setMouseTracking(True)
        canvas.installEventFilter(self)

    def _qt_canvas(self) -> QWidget:
        """Return the renderer canvas as a Qt widget."""
        if not isinstance(self.canvas, QWidget):
            msg = "Qt MatplotlibSpectrumPlot requires a QWidget canvas."
            raise TypeError(msg)
        return self.canvas

    def _translate_text(self, text: str) -> str:
        """Translate source text using the Qt translation context."""
        return self.tr(text)

    def _on_language_changed(self, _code: str) -> None:
        """Refresh translated plot text after a language change."""
        self.refresh_translated_text()

    def _create_continuum_editor_factory(self) -> MatplotlibContinuumEditorFactory:
        """Return the GUI-owned continuum editor factory."""
        return create_matplotlib_continuum_editor_adapter

    def _create_renderer_factory(self) -> MatplotlibRendererFactory:
        """Return the GUI-owned Matplotlib renderer factory."""

        def factory() -> MatplotlibRenderer:
            return create_qt_matplotlib_renderer(
                constrained_layout=self._constrained_layout, tick_labelsize=self._tick_labelsize
            )

        return factory

    def _emit_range_signal(self, x_min: float, x_max: float, y_min: float, y_max: float) -> None:
        """Emit the Qt range-changed signal."""
        self.range_changed.emit(x_min, x_max, y_min, y_max)

    def _emit_selection_signal(self, x_min: float, x_max: float) -> None:
        """Emit the Qt selection-changed signal."""
        self.selection_changed.emit(x_min, x_max)

    def _should_forward_mouse_events(self) -> bool:
        """Return whether mouse events should be forwarded to the shared interactor."""
        parent = self.parent()
        return not (
            parent is not None
            and isinstance(parent, MouseForwardingParent)
            and parent.blocks_plot_mouse_forwarding()
        )

    def _set_canvas_tooltip(self, text: str) -> None:
        """Set the Qt tooltip on the embedded canvas."""
        self._qt_canvas().setToolTip(text)
