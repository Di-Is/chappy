"""UI construction and layout management for spectrum view.

This module handles the creation and arrangement of UI components
for the spectrum view.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QBoxLayout, QStackedLayout, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from chappy.gui.spectrum.spectrum_view import SpectrumView


@runtime_checkable
class _PlotComponent(Protocol):
    """Protocol describing the plot component dependency."""

    def create_widget(self) -> QWidget:
        """Create and return the plot widget."""


logger = logging.getLogger(__name__)


class SpectrumViewBuilder:
    """Builds UI components for spectrum view.

    Responsibilities:
    - UI layout construction
    - Widget creation and placement
    - Initial configuration
    - Style application
    """

    def __init__(self, view: SpectrumView) -> None:
        """Initialize the builder.

        Args:
            view: The spectrum view to build UI for
        """
        self.view = view
        self._built = False

        logger.debug("SpectrumViewBuilder initialized")

    def build(self) -> None:
        """Build the complete UI."""
        if self._built:
            msg = "Spectrum view UI has already been built."
            raise RuntimeError(msg)

        # Create main layout
        self._create_main_layout()

        layout = self.view.layout()
        if layout is None:
            msg = "Spectrum view layout is required after main layout creation."
            raise RuntimeError(msg)

        # Create plot area
        plot_widget = self._create_plot_area()
        if isinstance(layout, QBoxLayout):
            layout.addWidget(plot_widget, 1)  # Stretch factor 1
        else:
            layout.addWidget(plot_widget)

        # Apply initial settings
        self._apply_initial_settings()

        self._built = True
        logger.info("Spectrum view UI built successfully")

    def _create_main_layout(self) -> None:
        """Create the main layout structure."""
        layout = QVBoxLayout(self.view)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        logger.debug("Main layout created")

    def _create_plot_area(self) -> QWidget:
        """Create the plot display area.

        Returns:
            The plot container widget.
        """
        component = self.view.plot_host
        if not isinstance(component, _PlotComponent):
            msg = "Plot component is required to build SpectrumView."
            raise TypeError(msg)

        plot_widget = component.create_widget()
        if not isinstance(plot_widget, QWidget):
            msg = "Plot component must create a QWidget."
            raise TypeError(msg)

        plot_widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        container = QWidget(self.view)
        container.setObjectName("spectrumPlotContainer")
        stack = QStackedLayout(container)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setSpacing(0)
        stack.addWidget(plot_widget)

        # Expose stack to the view for overlay management
        self.view.register_plot_container(container, stack, plot_widget)

        return container

    def _apply_initial_settings(self) -> None:
        """Apply initial settings to UI components."""
        logger.debug("Initial settings applied")
