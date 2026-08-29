"""Stacked spectrum view composition for the GUI shell."""
# mypy: disable-error-code="attr-defined"

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from chappy.core.editing_mode import EditingMode
from chappy.gui.shell.spectrum_mode_policy import spectrum_interaction_mode_policy
from chappy.gui.spectrum.spectrum_plot import create_default_spectrum_plot_host_factory
from chappy.gui.spectrum.spectrum_view import SpectrumView
from chappy.gui.spectrum.velocity import VelocityGridWidget

if TYPE_CHECKING:
    from chappy.core.spectroscopy_project import SpectroscopyProject


logger = logging.getLogger(__name__)


class ViewStack(QWidget):
    """Stack for multiple spectrum view types.

    This widget manages different view modes for spectrum display:
    - Spectrum View: Standard wavelength-space display
    - Velocity View: Velocity-space display
    - Additional views can be added in the future

    Each view maintains its own display settings and can be
    independently configured.

    Signals:
        activeViewChanged: Emitted when active view changes
    """

    # Qt signals
    activeViewChanged = Signal(  # noqa: N815 # Qt signal follows framework naming convention
        str, QWidget
    )  # view_name, view_widget

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize view stack.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        # State
        self.current_project: SpectroscopyProject | None = None

        # Views
        self.spectrum_view: SpectrumView | None = None
        self.velocity_view: VelocityGridWidget | None = None

        # View registry for extensibility
        self.views: dict[str, QWidget] = {}
        self._view_stack: QStackedWidget | None = None

        # Setup UI
        self._setup_views()
        self._connect_signals()

        logger.debug("ViewStack initialized")

    def _setup_views(self) -> None:
        """Setup all available views."""
        logger.info("Setting up stacked views in ViewStack...")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._view_stack = QStackedWidget(self)
        layout.addWidget(self._view_stack)

        logger.info("🌟 Creating SpectrumView...")
        self.spectrum_view = SpectrumView(
            self, plot_host_factory=create_default_spectrum_plot_host_factory()
        )
        self.spectrum_view.apply_policy(spectrum_interaction_mode_policy(EditingMode.START))
        self.views["spectrum"] = self.spectrum_view
        self._view_stack.addWidget(self.spectrum_view)
        logger.info("✓ SpectrumView added to stack")

        logger.info("🌐 Creating VelocityGridWidget...")
        self.velocity_view = VelocityGridWidget(self)
        self.views["velocity"] = self.velocity_view
        self._view_stack.addWidget(self.velocity_view)
        logger.info("✓ VelocityGridWidget added to stack")

        # Set initial view
        self._view_stack.setCurrentWidget(self.spectrum_view)
        logger.info("✓ Set initial stacked view to Spectrum")

        logger.info("ViewStack views setup completed without tabs")

    def _connect_signals(self) -> None:
        """Connect internal signals."""
        # View change signal
        if self._view_stack:
            self._view_stack.currentChanged.connect(self._on_view_changed)

    def set_project(self, project: SpectroscopyProject | None) -> None:
        """Set current project for all views.

        Args:
            project: Project to set (None to clear)
        """
        self.current_project = project

        if self.spectrum_view is not None:
            self.spectrum_view.set_project(project)

        logger.info("Set project in ViewStack: %s", project.name if project else None)

    def get_active_view(self) -> tuple[str, QWidget]:
        """Get currently active view.

        Returns:
            Tuple of (view_name, view_widget).
        """
        current_widget = self.currentWidget()
        if current_widget is None:
            msg = "Active view widget is required but the view stack is not initialized."
            raise RuntimeError(msg)

        for name, widget in self.views.items():
            if widget == current_widget:
                return name, widget

        msg = "Active view widget is not registered in ViewStack."
        raise RuntimeError(msg)

    def currentWidget(self) -> QWidget | None:  # noqa: N802 - Qt-style API name
        """Return the currently visible view widget."""
        if self._view_stack:
            return self._view_stack.currentWidget()
        return None

    @Slot(int)
    def _on_view_changed(self, _index: int) -> None:
        """Handle stacked view change events."""
        view_name, view_widget = self.get_active_view()

        # Emit signal
        self.activeViewChanged.emit(view_name, view_widget)

        logger.debug("Active view changed to: %s", view_name)

    def get_all_views(self) -> list[QWidget]:
        """Get all view widgets.

        Returns:
            List of view widgets
        """
        return list(self.views.values())

    def get_spectrum_plot(self) -> QWidget | None:
        """Get the spectrum plot widget for direct manipulation.

        Returns:
            Spectrum plot widget or None if not available
        """
        if self.spectrum_view:
            return self.spectrum_view.spectrum_plot
        msg = "Spectrum view is required before accessing the spectrum plot."
        raise RuntimeError(msg)
