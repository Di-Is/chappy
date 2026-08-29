"""Map Qt pointer positions to spectrum data coordinates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtGui import QCursor

if TYPE_CHECKING:
    from PySide6.QtGui import QMouseEvent, QWheelEvent

    from chappy.gui.spectrum.interaction.input.ports import SpectrumPlotWidgetPort
    from chappy.gui.utils.plot_coordinate_transform import PlotCoordinateTransform


@dataclass(frozen=True, slots=True)
class DataPosition:
    """Spectrum data position."""

    wavelength: float
    flux: float

    def as_tuple(self) -> tuple[float, float]:
        """Return the position as a tuple."""
        return (self.wavelength, self.flux)


@dataclass(frozen=True, slots=True)
class PointerDataPosition:
    """Spectrum data position with keyboard modifiers."""

    position: DataPosition
    modifiers: int


class SpectrumPointerCoordinateMapper:
    """Convert Qt pointer positions to spectrum data coordinates."""

    def optional_event_data_position(
        self, transform: PlotCoordinateTransform | None, event: QMouseEvent | QWheelEvent
    ) -> DataPosition | None:
        """Return a data position for an event, or None when conversion fails."""
        if transform is None:
            return None

        pos = event.position()
        return self.optional_xy_data_position(transform, float(pos.x()), float(pos.y()))

    def require_event_data_position(
        self, transform: PlotCoordinateTransform, event: QMouseEvent | QWheelEvent
    ) -> DataPosition:
        """Return a data position for an event, preserving conversion failures."""
        pos = event.position()
        wavelength, flux = transform.qt_to_data_coordinates(pos.x(), pos.y())
        return DataPosition(wavelength=float(wavelength), flux=float(flux))

    def optional_xy_data_position(
        self, transform: PlotCoordinateTransform, x: float, y: float
    ) -> DataPosition | None:
        """Return a data position for Qt coordinates, or None on conversion failure."""
        try:
            data_pos = transform.qt_to_data_coordinates(x, y)
        except ValueError:
            return None
        if data_pos is None:
            return None
        wavelength, flux = data_pos
        return DataPosition(wavelength=float(wavelength), flux=float(flux))

    def optional_global_cursor_data_position(
        self,
        *,
        transform: PlotCoordinateTransform | None,
        plot_widget: SpectrumPlotWidgetPort | None,
    ) -> DataPosition | None:
        """Return data coordinates for the current global cursor position."""
        if transform is None or plot_widget is None:
            return None

        try:
            local_pos = plot_widget.mapFromGlobal(QCursor.pos())
            qt_x = float(local_pos.x())
            qt_y = float(local_pos.y())
        except (RuntimeError, TypeError):
            return None

        if not transform.is_valid_position(qt_x, qt_y):
            return None

        return self.optional_xy_data_position(transform, qt_x, qt_y)
