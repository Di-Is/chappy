"""Bootstrap MainWindow UI shell components.

This module manages window properties, UI construction, and basic setup.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from PySide6.QtCore import QByteArray, QObject, QSettings

from chappy.gui.shell.dock_layout_coordinator import DockLayoutCoordinator
from chappy.gui.shell.menu_action_factory import MenuActionFactory
from chappy.gui.shell.window_layout_builder import WindowLayoutBuilder
from chappy.gui.theme import get_application_stylesheet

if TYPE_CHECKING:
    from collections.abc import Callable

    from PySide6.QtGui import QCloseEvent, QDragEnterEvent, QDropEvent
    from PySide6.QtWidgets import QMainWindow, QProgressBar

    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.modes.analysis.region_detail.model_addition_controller import (
        OptimizeModelAdditionUseCasePort,
    )
    from chappy.gui.modes.identify.panel.panel import IdentifySidePanel
    from chappy.gui.shell.actions.dispatcher import ActionDispatcher
    from chappy.gui.shell.dependencies import RegionDetailFactory
    from chappy.gui.shell.project_session_controller import SavePromptReason

logger = logging.getLogger(__name__)

_WINDOW_LAYOUT_SCHEMA_KEY = "windowLayoutSchema"
_WINDOW_LAYOUT_SCHEMA_VERSION = 3


@dataclass(slots=True)
class WindowBootstrapParts:
    """Typed shell UI parts built by the window bootstrapper."""

    layout_builder: WindowLayoutBuilder | None = None
    action_factory: MenuActionFactory | None = None
    dock_coordinator: DockLayoutCoordinator | None = None
    progress_bar: QProgressBar | None = None


class ProjectSessionEventPort(Protocol):
    """Protocol describing the project session APIs used by window events."""

    def check_save_current_project(self, *, reason: SavePromptReason = "generic") -> bool:
        """Return whether closing can proceed after save prompts."""
        ...

    def handle_drag_enter_event(self, event: QDragEnterEvent) -> None:
        """Process drag enter events for project resources."""
        ...

    def handle_drop_event(self, event: QDropEvent) -> None:
        """Process drop events for project resources."""
        ...


class WindowBootstrapper:
    """Bootstrap window setup and initialization.

    Responsibilities:
    - Window properties configuration
    - Menu creation
    - Status bar setup
    - Central widget setup
    - Dock widget management
    - Action factory initialization
    """

    def __init__(
        self,
        main_window: QMainWindow,
        *,
        optimize_model_addition_usecase: OptimizeModelAdditionUseCasePort,
        region_detail_factory: RegionDetailFactory,
    ) -> None:
        """Initialize setup handler.

        Args:
            main_window: The main application window
            optimize_model_addition_usecase: Use case passed to optimize mode panel.
            region_detail_factory: Factory composing the Region Detail UI facade.
        """
        self._main_window = main_window
        self._optimize_model_addition_usecase = optimize_model_addition_usecase
        self._region_detail_factory = region_detail_factory
        self._parts = WindowBootstrapParts()

        logger.debug("WindowBootstrapper initialized")

    @property
    def parts(self) -> WindowBootstrapParts:
        """Return the typed shell UI parts assembled so far."""
        return self._parts

    def setup_window(self) -> None:
        """Setup basic window properties."""
        if self._parts.layout_builder is None:
            self._parts.layout_builder = WindowLayoutBuilder(self._main_window)
        self._parts.layout_builder.setup_window_properties()

    def create_actions(self, dispatcher: ActionDispatcher) -> None:
        """Create all application actions."""
        self._parts.action_factory = MenuActionFactory(self._main_window, dispatcher=dispatcher)
        self._parts.action_factory.create_all_actions()

    def create_menus(self) -> None:
        """Create all application menus."""
        if self._parts.action_factory is None:
            msg = "Action factory not initialized"
            raise RuntimeError(msg)

        # Create menu bar and set it to the main window
        menubar = self._parts.action_factory.create_menu_bar()
        self._main_window.setMenuBar(menubar)

        logger.debug("Application menus created and set to main window")

    def create_status_bar(self) -> None:
        """Create status bar with shared controller."""
        if self._parts.layout_builder is None:
            self._parts.layout_builder = WindowLayoutBuilder(self._main_window)

        self._parts.layout_builder.create_status_bar()

        controller = self._parts.layout_builder.status_controller
        if controller:
            self._parts.progress_bar = controller.progress_bar

        logger.debug("Status bar created")

    def create_central_widget(self) -> None:
        """Create central widget for main content area."""
        # Use layout builder to create central widget with ViewStack.
        if self._parts.layout_builder is None:
            self._parts.layout_builder = WindowLayoutBuilder(self._main_window)

        logger.info("🏗️ Creating central widget via WindowLayoutBuilder...")
        self._parts.layout_builder.create_central_widget()

    def create_dock_widgets(self) -> None:
        """Create and setup all dock widgets."""
        if self._parts.layout_builder is None:
            msg = "WindowLayoutBuilder must be initialized before creating dock widgets"
            raise RuntimeError(msg)
        side_panel_container = self._parts.layout_builder.side_panel_placeholder
        if side_panel_container is None:
            msg = "Side panel placeholder must be initialized before creating dock widgets"
            raise RuntimeError(msg)

        self._parts.dock_coordinator = DockLayoutCoordinator(
            self._main_window,
            side_panel_container=side_panel_container,
            optimize_model_addition_usecase=self._optimize_model_addition_usecase,
            region_detail_factory=self._region_detail_factory,
        )

        # Create standard dock widgets
        self._parts.dock_coordinator.create_component_dock()
        self._parts.dock_coordinator.create_range_selector_dock()

        analysis_bottom_pane = self._parts.layout_builder.analysis_bottom_pane
        analysis_center_splitter = self._parts.layout_builder.analysis_center_splitter
        if analysis_bottom_pane is None or analysis_center_splitter is None:
            msg = "Central widget must be built before attaching the Analysis bottom pane"
            raise RuntimeError(msg)
        self._parts.dock_coordinator.attach_analysis_bottom_pane(
            analysis_bottom_pane, analysis_center_splitter
        )

        logger.debug("Dock widgets created and configured")

    def restore_settings(self) -> None:
        """Restore window settings from QSettings."""
        settings = QSettings()

        stored_layout_schema = settings.value(_WINDOW_LAYOUT_SCHEMA_KEY, 0, type=int)
        if stored_layout_schema != _WINDOW_LAYOUT_SCHEMA_VERSION:
            # Old windowState embeds removed dock object names (analysisBottomDock etc.).
            settings.remove("windowState")
            settings.remove("mainSplitterState")
            settings.remove("analysisCenterSplitterState")
            settings.setValue(_WINDOW_LAYOUT_SCHEMA_KEY, _WINDOW_LAYOUT_SCHEMA_VERSION)

        # Restore window geometry and state
        geometry_bytes = settings.value("geometry", defaultValue=None, type=QByteArray)
        if isinstance(geometry_bytes, QByteArray) and not self._main_window.restoreGeometry(
            geometry_bytes
        ):
            logger.warning("Stored window geometry could not be restored; clearing setting")
            settings.remove("geometry")

        state_bytes = settings.value("windowState", defaultValue=None, type=QByteArray)
        if isinstance(state_bytes, QByteArray) and not self._main_window.restoreState(state_bytes):
            logger.warning("Stored window state could not be restored; clearing setting")
            settings.remove("windowState")

        layout_builder = self._parts.layout_builder
        main_splitter = layout_builder.main_splitter if layout_builder is not None else None
        if main_splitter is not None:
            splitter_bytes = settings.value(
                "mainSplitterState", defaultValue=None, type=QByteArray
            )
            if isinstance(splitter_bytes, QByteArray) and not main_splitter.restoreState(
                splitter_bytes
            ):
                logger.warning("Stored splitter state could not be restored; clearing setting")
                settings.remove("mainSplitterState")
            main_splitter.splitterMoved.connect(self._persist_splitter_state)

        analysis_center_splitter = (
            layout_builder.analysis_center_splitter if layout_builder is not None else None
        )
        if analysis_center_splitter is not None:
            splitter_bytes = settings.value(
                "analysisCenterSplitterState", defaultValue=None, type=QByteArray
            )
            if isinstance(splitter_bytes, QByteArray):
                if analysis_center_splitter.restoreState(splitter_bytes):
                    dock_coordinator = self._parts.dock_coordinator
                    if dock_coordinator is not None:
                        dock_coordinator.mark_analysis_bottom_pane_height_restored()
                else:
                    logger.warning(
                        "Stored Analysis splitter state could not be restored; clearing setting"
                    )
                    settings.remove("analysisCenterSplitterState")
            analysis_center_splitter.splitterMoved.connect(
                self._persist_analysis_center_splitter_state
            )

        identify_panel = self._identify_panel()
        if identify_panel is not None:
            identify_panel.restore_ui_state(settings)
            identify_panel.ui_state_changed.connect(self._persist_identify_panel_ui_state)

        # Apply theme
        stylesheet = get_application_stylesheet()
        self._main_window.setStyleSheet(stylesheet)

        logger.debug("Window settings restored")

    def _persist_splitter_state(self, *_: object) -> None:
        """Persist the main splitter position when the user moves it."""
        layout_builder = self._parts.layout_builder
        main_splitter = layout_builder.main_splitter if layout_builder is not None else None
        if main_splitter is None:
            return
        QSettings().setValue("mainSplitterState", main_splitter.saveState())

    def _persist_analysis_center_splitter_state(self, *_: object) -> None:
        """Persist the Analysis bottom pane height when the user drags it."""
        layout_builder = self._parts.layout_builder
        splitter = layout_builder.analysis_center_splitter if layout_builder is not None else None
        if splitter is None:
            return
        QSettings().setValue("analysisCenterSplitterState", splitter.saveState())

    def _identify_panel(self) -> IdentifySidePanel | None:
        """Return the identify side panel once the dock coordinator built it."""
        dock_coordinator = self._parts.dock_coordinator
        if dock_coordinator is None:
            return None
        return dock_coordinator.identify_panel

    def _persist_identify_panel_ui_state(self) -> None:
        """Persist identify panel splitter and collapse state when they change."""
        identify_panel = self._identify_panel()
        if identify_panel is None:
            return
        identify_panel.save_ui_state(QSettings())

    def save_settings(self) -> None:
        """Save window settings to QSettings."""
        settings = QSettings()
        settings.setValue(_WINDOW_LAYOUT_SCHEMA_KEY, _WINDOW_LAYOUT_SCHEMA_VERSION)
        settings.setValue("geometry", self._main_window.saveGeometry())
        settings.setValue("windowState", self._main_window.saveState())

        layout_builder = self._parts.layout_builder
        main_splitter = layout_builder.main_splitter if layout_builder is not None else None
        if main_splitter is not None:
            settings.setValue("mainSplitterState", main_splitter.saveState())

        analysis_center_splitter = (
            layout_builder.analysis_center_splitter if layout_builder is not None else None
        )
        if analysis_center_splitter is not None:
            settings.setValue("analysisCenterSplitterState", analysis_center_splitter.saveState())

        identify_panel = self._identify_panel()
        if identify_panel is not None:
            identify_panel.save_ui_state(settings)

        logger.debug("Window settings saved")

    def update_window_title(self, current_project: SpectroscopyProject | None = None) -> None:
        """Update window title based on current project.

        Args:
            current_project: The current project or None
        """
        if current_project:
            project_name = current_project.name
            self._main_window.setWindowTitle(f"Chappy - {project_name}")
        else:
            self._main_window.setWindowTitle("Chappy - QSO Absorber Analysis")


class WindowLifecycleCoordinator(QObject):
    """Coordinate window lifecycle events for the GUI shell."""

    def __init__(self, main_window: QMainWindow) -> None:
        """Initialize the lifecycle coordinator.

        Args:
            main_window: The main application window.
        """
        super().__init__(main_window)
        self._main_window = main_window
        self._project_session: ProjectSessionEventPort | None = None
        self._save_settings_callback: Callable[[], None] | None = None

        logger.debug("WindowLifecycleCoordinator initialized")

    def set_project_session(self, project_session: ProjectSessionEventPort) -> None:
        """Set the project session used by window events.

        Args:
            project_session: Project session event port.
        """
        self._project_session = project_session

    def set_save_settings_callback(self, callback: Callable[[], None]) -> None:
        """Set the callback for saving window settings.

        Args:
            callback: Function to call when settings need to be saved.
        """
        self._save_settings_callback = callback

    def setup_event_handling(self) -> None:
        """Enable shell-level window event handling."""
        self._main_window.setAcceptDrops(True)
        logger.info("Drag and drop enabled: %s", self._main_window.acceptDrops())

    def handle_close_event(self, event: QCloseEvent) -> None:
        """Handle the window close event.

        Args:
            event: Qt close event.
        """
        if self._project_session is None:
            msg = "Project session is required before handling close events."
            raise RuntimeError(msg)

        if not self._project_session.check_save_current_project(reason="shutdown"):
            event.ignore()
            return

        if self._save_settings_callback is not None:
            self._save_settings_callback()

        event.accept()
        logger.info("Main window closed via closeEvent")

    def handle_drag_enter_event(self, event: QDragEnterEvent) -> None:
        """Handle drag enter events for file drops.

        Args:
            event: Drag enter event.
        """
        if self._project_session is None:
            msg = "Project session is required before handling drag enter events."
            raise RuntimeError(msg)

        self._project_session.handle_drag_enter_event(event)
        logger.debug("Drag enter event handled by project session")

    def handle_drop_event(self, event: QDropEvent) -> None:
        """Handle drop events for project files.

        Args:
            event: Drop event.
        """
        if self._project_session is None:
            msg = "Project session is required before handling drop events."
            raise RuntimeError(msg)

        self._project_session.handle_drop_event(event)
        logger.debug("Drop event handled by project session")
