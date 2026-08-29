"""Build main window layout components for the GUI shell."""
# mypy: disable-error-code="operator,index,attr-defined"

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, override

from PySide6.QtCore import QObject, QPointF, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QMainWindow,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QSplitterHandle,
    QVBoxLayout,
    QWidget,
)

from chappy.gui.shell.data_control_panel import DataControlPanel
from chappy.gui.shell.mode_context_bar import ModeContextBar
from chappy.gui.shell.status_bar import StatusBarController
from chappy.gui.shell.view_stack import ViewStack
from chappy.gui.theme import Colors, Fonts, Spacing
from chappy.gui.visual_tokens import LayoutMetrics, SidePanelMetrics

if TYPE_CHECKING:
    from PySide6.QtGui import QMouseEvent, QPaintEvent

logger = logging.getLogger(__name__)


class _GripSplitterHandle(QSplitterHandle):
    """Splitter handle that paints a centered grip like the Identify splitter."""

    @override
    def paintEvent(self, event: QPaintEvent) -> None:
        """Draw the styled background, then a centered dotted grip."""
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(Colors.TEXT_SECONDARY))
        center = self.rect().center()
        dots_run_horizontally = self.orientation() is Qt.Orientation.Vertical
        for offset in (-6.0, -2.0, 2.0, 6.0):
            if dots_run_horizontally:
                painter.drawEllipse(QPointF(center.x() + offset, center.y()), 1.0, 1.0)
            else:
                painter.drawEllipse(QPointF(center.x(), center.y() + offset), 1.0, 1.0)
        painter.end()

    @override
    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Report double clicks on vertical splitters for maximize toggling."""
        splitter = self.splitter()
        if self.orientation() is Qt.Orientation.Vertical and isinstance(splitter, GripSplitter):
            splitter.handle_double_clicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class GripSplitter(QSplitter):
    """Shell splitter with a visible resize grip on its handle."""

    handle_double_clicked = Signal()

    @override
    def createHandle(self) -> QSplitterHandle:
        """Create the grip-rendering handle for this splitter."""
        return _GripSplitterHandle(self.orientation(), self)


class AnalysisBottomPane(QWidget):
    """Analysis bottom host pairing a section header with the bottom stack."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("analysisBottomPane")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.title_label = QLabel(self)
        self.title_label.setObjectName("analysisBottomPaneTitle")
        self.title_label.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: {Fonts.SIZE_MEDIUM};"
            f" font-weight: 600; padding: {Spacing.XS} {Spacing.SM};"
        )
        layout.addWidget(self.title_label)
        self._layout = layout

    def set_title(self, title: str) -> None:
        """Update the section header above the hosted content."""
        self.title_label.setText(title)

    def attach_content(self, content: QWidget) -> None:
        """Host the Analysis bottom stack below the section header."""
        self._layout.addWidget(content, stretch=1)


class WindowLayoutBuilder(QObject):
    """Build window layout, settings, and UI components.

    This class handles the creation and management of all UI layout
    components including the status bar, central widgets,
    and window settings persistence.
    """

    def __init__(self, main_window: QMainWindow) -> None:
        """Initialize the window layout builder.

        Args:
            main_window: Parent main window instance.
        """
        super().__init__()
        self.main_window = main_window

        # UI components that will be created
        self.central_widget: QWidget | None = None
        self.main_splitter: QSplitter | None = None
        self.analysis_center_splitter: GripSplitter | None = None
        self.analysis_bottom_pane: AnalysisBottomPane | None = None
        self.view_container: QWidget | None = None
        self.view_stack: ViewStack | None = None
        self.mode_context_bar: ModeContextBar | None = None
        self.data_control_panel: DataControlPanel | None = None
        self.data_control_container: QScrollArea | None = None
        self.status_controller: StatusBarController | None = None
        self.side_panel_placeholder: QWidget | None = None

    def setup_window_properties(self) -> None:
        """Setup basic window properties."""
        self.main_window.setWindowTitle(
            "Chappy - Code for Handling Absorption Profiles with PYthon"
        )
        self.main_window.setWindowIcon(QIcon())  # TODO(dev): Add application icon

        # Set default size and position
        default_width = LayoutMetrics.SIDEPANEL_WIDTH + 900
        self.main_window.resize(default_width, 800)
        self.main_window.move(100, 100)

        # Set minimum size to ensure consistent layout across modes
        # Based on SCR-COM.01.03 specifications
        self.main_window.setMinimumSize(800, 600)

        # Enable dock widget features
        self.main_window.setDockOptions(
            QMainWindow.DockOption.AllowTabbedDocks
            | QMainWindow.DockOption.AllowNestedDocks
            | QMainWindow.DockOption.AnimatedDocks
        )

    def create_status_bar(self) -> None:
        """Create status bar with three-zone layout controller."""
        status_bar = self.main_window.statusBar()
        self.status_controller = StatusBarController(status_bar)

    def create_central_widget(self) -> None:
        """Create central widget with main plot area."""
        self.central_widget = QWidget()
        # Enable drag/drop on central widget so events can be forwarded to main window
        self.central_widget.setAcceptDrops(True)
        self.main_window.setCentralWidget(self.central_widget)

        # Main layout
        layout = QVBoxLayout(self.central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Mode context bar
        self.mode_context_bar = ModeContextBar()
        layout.addWidget(self.mode_context_bar)

        # Create main splitter
        self.main_splitter = GripSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setObjectName("mainSplitter")
        self.main_splitter.setProperty("doc.include", False)
        self.main_splitter.setHandleWidth(SidePanelMetrics.SPLITTER_HANDLE_WIDTH)
        # Enable drag/drop on splitter so events can be forwarded to main window
        self.main_splitter.setAcceptDrops(True)
        self.main_splitter.setChildrenCollapsible(False)
        layout.addWidget(self.main_splitter, stretch=1)

        # Build left view container so spectrum and controls share width
        self.view_container = QWidget()
        self.view_container.setObjectName("viewContainer")
        self.view_container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        view_layout = QVBoxLayout(self.view_container)
        view_layout.setContentsMargins(0, 0, 0, 0)
        view_layout.setSpacing(0)

        # Create view stack with multiple views.
        self.view_stack = ViewStack()
        if self.view_stack.spectrum_view is not None:
            self.view_stack.spectrum_view.set_start_mode_drop_target(self.main_window)

        # Enable drag/drop on view stack so events can be forwarded to main window.
        self.view_stack.setAcceptDrops(True)
        self.view_stack.setMinimumHeight(LayoutMetrics.SPECTRUM_MIN_HEIGHT)
        self.view_stack.setMinimumWidth(LayoutMetrics.SPECTRUM_MIN_WIDTH)

        logger.info("Building view container with ViewStack and DataControlPanel...")

        # Vertical splitter hosting the spectrum above the Analysis bottom pane.
        self.analysis_center_splitter = GripSplitter(Qt.Orientation.Vertical)
        self.analysis_center_splitter.setObjectName("analysisCenterSplitter")
        self.analysis_center_splitter.setProperty("doc.include", False)
        self.analysis_center_splitter.setHandleWidth(SidePanelMetrics.SPLITTER_HANDLE_WIDTH)
        self.analysis_center_splitter.setAcceptDrops(True)
        self.analysis_center_splitter.setChildrenCollapsible(False)
        self.analysis_center_splitter.addWidget(self.view_stack)

        self.analysis_bottom_pane = AnalysisBottomPane()
        self.analysis_bottom_pane.hide()
        self.analysis_center_splitter.addWidget(self.analysis_bottom_pane)
        self.analysis_center_splitter.setStretchFactor(0, 1)
        self.analysis_center_splitter.setStretchFactor(1, 0)
        view_layout.addWidget(self.analysis_center_splitter, stretch=1)

        # Data control panel at bottom, aligned with spectrum width.
        # Wrapped in a horizontal scroll area so the panel's own large
        # minimum width does not propagate to the splitter/view container.
        self.data_control_panel = DataControlPanel()
        data_control_scroll = QScrollArea(self.view_container)
        data_control_scroll.setObjectName("dataControlScroll")
        data_control_scroll.setWidget(self.data_control_panel)
        data_control_scroll.setWidgetResizable(True)
        data_control_scroll.setFrameShape(QFrame.Shape.NoFrame)
        data_control_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        data_control_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        data_control_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.data_control_container = data_control_scroll
        view_layout.addWidget(data_control_scroll)

        self.main_splitter.addWidget(self.view_container)
        logger.info("✓ View container added to splitter")

        # Placeholder side panel container. DockLayoutCoordinator mounts the content.
        self.side_panel_placeholder = QWidget()
        self.side_panel_placeholder.setObjectName("sidePanelPlaceholder")
        self.side_panel_placeholder.setProperty("doc.include", False)
        self.side_panel_placeholder.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        # No descendant QWidget rule here: widget-level sheets outrank the
        # application sheet, so it would wipe QPushButton[variant=...] fills.
        self.side_panel_placeholder.setStyleSheet(
            "#sidePanelPlaceholder {"
            f" background-color: {Colors.BACKGROUND_PANEL};"
            f" border-left: 1px solid {Colors.BORDER_DEFAULT};"
            "}"
        )
        self.main_splitter.addWidget(self.side_panel_placeholder)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 0)

        # Set initial splitter sizes
        default_left = max(800, self.main_window.width() - LayoutMetrics.SIDEPANEL_WIDTH)
        self.main_splitter.setSizes([default_left, LayoutMetrics.SIDEPANEL_WIDTH])
