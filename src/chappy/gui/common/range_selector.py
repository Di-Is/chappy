"""Range selector widget for creating fitting range groups."""

from __future__ import annotations

import logging
import math
from typing import Protocol, runtime_checkable

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QWidget,
)

logger = logging.getLogger(__name__)


@runtime_checkable
class SpectrumItem(Protocol):
    """Protocol for spectrum graphics items."""

    _is_spectrum_item: bool


class RangeRectItem(QGraphicsRectItem):
    """Graphics item representing a wavelength range selection."""

    def __init__(self, x: float, y: float, width: float, height: float) -> None:
        """Initialize range rectangle item.

        Args:
            x: X position
            y: Y position
            width: Rectangle width
            height: Rectangle height
        """
        super().__init__(x, y, width, height)

        # Set appearance
        self.setPen(QPen(QColor(255, 0, 0, 180), 2, Qt.PenStyle.DashLine))
        self.setBrush(QBrush(QColor(255, 0, 0, 50)))

        # Enable interactions
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges, True)


class RangeSelectorWidget(QGraphicsView):
    """Widget for interactively selecting wavelength ranges.

    This widget allows users to drag-select wavelength ranges on a spectrum plot
    for creating fitting range groups.

    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize range selector widget.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        # Initialize scene
        self._scene = QGraphicsScene()
        self.setScene(self._scene)

        # Selection state
        self._selecting = False
        self._start_pos = 0.0
        self._current_selection: RangeRectItem | None = None

        # Spectrum data for visualization
        self._wavelength_data: list[float] = []
        self._flux_data: list[float] = []
        self._wavelength_min: float | None = None
        self._wavelength_max: float | None = None

        # Setup widget
        self._setup_widget()
        self.setEnabled(False)

        logger.info("✓ RangeSelectorWidget initialized with height: %d", self.height())

    def _setup_widget(self) -> None:
        """Setup widget appearance and behavior."""
        # Configure view
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Set fixed height for range selection area
        self.setFixedHeight(150)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def set_spectrum_data(self, wavelength: list[float], flux: list[float]) -> None:
        """Set spectrum data for visualization.

        Args:
            wavelength: Wavelength array
            flux: Flux array

        Raises:
            ValueError: If non-empty spectrum data is malformed.
        """
        _validate_spectrum_data(wavelength, flux)
        self._wavelength_data = wavelength
        self._flux_data = flux

        if wavelength and flux:
            self._wavelength_min = min(wavelength)
            self._wavelength_max = max(wavelength)
            self.setEnabled(True)
        else:
            self._wavelength_min = None
            self._wavelength_max = None
            self.setEnabled(False)

        self._update_spectrum_display()

    def _update_spectrum_display(self) -> None:
        """Update the spectrum display in the scene."""
        # Clear existing spectrum items
        for item in self._scene.items():
            if isinstance(item, SpectrumItem):
                self._scene.removeItem(item)

        if not self._wavelength_data or not self._flux_data:
            return
        if self._wavelength_min is None or self._wavelength_max is None:
            return

        # Draw simplified spectrum representation
        min_flux = min(self._flux_data) if self._flux_data else 0.0
        max_flux = max(self._flux_data) if self._flux_data else 1.0
        flux_range = max_flux - min_flux if max_flux > min_flux else 1.0

        # Scene coordinates: x = wavelength, y = normalized flux
        scene_height = 100.0

        # Sample points for display (don't draw every point for performance)
        step = max(1, len(self._wavelength_data) // 1000)

        for i in range(0, len(self._wavelength_data) - step, step):
            x1 = self._wavelength_data[i]
            y1 = scene_height * (1.0 - (self._flux_data[i] - min_flux) / flux_range)

            x2 = self._wavelength_data[i + step]
            y2 = scene_height * (1.0 - (self._flux_data[i + step] - min_flux) / flux_range)

            self._scene.addLine(x1, y1, x2, y2, QPen(QColor(0, 0, 255, 100)))

        # Update scene rect
        self._scene.setSceneRect(
            self._wavelength_min, 0, self._wavelength_max - self._wavelength_min, scene_height
        )

    def _clamp_to_wavelength_range(self, value: float) -> float | None:
        """Clamp a value to the loaded wavelength range.

        Args:
            value: Wavelength coordinate to clamp.

        Returns:
            Clamped wavelength, or None when no spectrum data is loaded.
        """
        if self._wavelength_min is None or self._wavelength_max is None:
            return None
        return max(self._wavelength_min, min(self._wavelength_max, value))

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Handle mouse press for range selection.

        Args:
            event: Mouse event
        """
        if event.button() == Qt.MouseButton.LeftButton:
            # Start selection
            scene_pos = self.mapToScene(event.pos())
            start_pos = self._clamp_to_wavelength_range(scene_pos.x())
            if start_pos is None:
                super().mousePressEvent(event)
                return
            self._start_pos = start_pos
            self._selecting = True

            logger.debug("Started range selection at %.1f Å", self._start_pos)

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Handle mouse move during selection.

        Args:
            event: Mouse event
        """
        if self._selecting:
            scene_pos = self.mapToScene(event.pos())
            current_pos = self._clamp_to_wavelength_range(scene_pos.x())
            if current_pos is None:
                super().mouseMoveEvent(event)
                return

            # Update selection rectangle
            min_x = min(self._start_pos, current_pos)
            max_x = max(self._start_pos, current_pos)
            width = max_x - min_x

            if self._current_selection:
                self._scene.removeItem(self._current_selection)

            if width > 0:
                self._current_selection = RangeRectItem(min_x, 0, width, 100.0)
                self._scene.addItem(self._current_selection)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Handle mouse release to complete selection.

        Args:
            event: Mouse event
        """
        if self._selecting and event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            end_pos = self._clamp_to_wavelength_range(scene_pos.x())
            if end_pos is None:
                self._selecting = False
                super().mouseReleaseEvent(event)
                return

            # Calculate final range
            min_wavelength = min(self._start_pos, end_pos)
            max_wavelength = max(self._start_pos, end_pos)

            # Only emit if range is meaningful (> 1 Angstrom)
            if max_wavelength - min_wavelength > 1.0:
                logger.info("Range selected: %.1f - %.1f Å", min_wavelength, max_wavelength)

            # Clean up
            if self._current_selection:
                self._scene.removeItem(self._current_selection)
                self._current_selection = None

            self._selecting = False

        super().mouseReleaseEvent(event)


def _validate_spectrum_data(wavelength: list[float], flux: list[float]) -> None:
    """Validate spectrum data before it drives selector state.

    Args:
        wavelength: Wavelength values.
        flux: Flux values.

    Raises:
        ValueError: If non-empty data is malformed.
    """
    if not wavelength and not flux:
        return
    if len(wavelength) != len(flux):
        msg = "Range selector spectrum data must have matching wavelength and flux lengths."
        raise ValueError(msg)
    if not wavelength:
        msg = "Range selector spectrum data must be empty or contain paired samples."
        raise ValueError(msg)
    if not all(math.isfinite(value) for value in wavelength):
        msg = "Range selector wavelength data must be finite."
        raise ValueError(msg)
    if not all(math.isfinite(value) for value in flux):
        msg = "Range selector flux data must be finite."
        raise ValueError(msg)
    if min(wavelength) >= max(wavelength):
        msg = "Range selector wavelength data must span a non-zero range."
        raise ValueError(msg)
