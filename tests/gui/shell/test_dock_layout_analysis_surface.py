"""Tests for Analysis-specific dock layout behavior in the shell."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import QMainWindow, QWidget

from chappy.core.editing_mode import EditingMode
from chappy.gui.modes.analysis.contracts import BottomPage
from chappy.gui.modes.analysis.workspace import (
    AnalysisWorkspace,
    AnalysisWorkspaceAccessibility,
    AnalysisWorkspacePages,
)
from chappy.gui.shell.dock_layout_coordinator import DockLayoutCoordinator, DockLayoutUiParts
from chappy.gui.shell.window_layout_builder import AnalysisBottomPane, GripSplitter
from chappy.gui.theme import get_application_stylesheet
from chappy.gui.visual_tokens import LayoutMetrics

if TYPE_CHECKING:
    import pytest
    from pytestqt.qtbot import QtBot


class _Announcements:
    def announce(self, message: str) -> None:
        """Discard announcements in tests."""


def _workspace(qtbot: QtBot) -> AnalysisWorkspace:
    workspace = AnalysisWorkspace(
        AnalysisWorkspacePages(
            summary=QWidget(),
            structure=QWidget(),
            detail=QWidget(),
            review=QWidget(),
            parameters=QWidget(),
        ),
        accessibility=AnalysisWorkspaceAccessibility("Right", "Bottom"),
        announcement_port=_Announcements(),
    )
    qtbot.addWidget(workspace.right_stack)
    qtbot.addWidget(workspace.bottom_stack)
    return workspace


def _coordinator_skeleton(side_panel_container: QWidget) -> DockLayoutCoordinator:
    """Build a coordinator without its heavy composition dependencies."""
    coordinator = cast(
        "DockLayoutCoordinator", DockLayoutCoordinator.__new__(DockLayoutCoordinator)
    )
    QObject.__init__(coordinator)
    coordinator.side_panel_container = side_panel_container
    coordinator._analysis_bottom_pane = None
    coordinator._analysis_center_splitter = None
    coordinator._analysis_bottom_restore_height = None
    coordinator._analysis_bottom_pane_sized = False
    coordinator.analysis_workspace = None
    coordinator._region_detail_ui = None
    coordinator.docks = {}
    coordinator._ui_parts = DockLayoutUiParts()
    return coordinator


def _attached_pane(qtbot: QtBot) -> tuple[DockLayoutCoordinator, AnalysisBottomPane, GripSplitter]:
    main_window = QMainWindow()
    qtbot.addWidget(main_window)
    coordinator = _coordinator_skeleton(QWidget(main_window))
    coordinator.main_window = main_window
    coordinator.analysis_workspace = _workspace(qtbot)

    splitter = GripSplitter(Qt.Orientation.Vertical)
    qtbot.addWidget(splitter)
    view = QWidget()
    view.setMinimumHeight(LayoutMetrics.SPECTRUM_MIN_HEIGHT)
    splitter.addWidget(view)
    pane = AnalysisBottomPane()
    splitter.addWidget(pane)
    splitter.setChildrenCollapsible(False)

    coordinator.attach_analysis_bottom_pane(pane, splitter)
    return coordinator, pane, splitter


def test_analysis_bottom_pane_title_follows_bottom_surface(qtbot: QtBot) -> None:
    """F7b/R2: the pane header is titled after the visible surface, not the mode."""
    coordinator, pane, _splitter = _attached_pane(qtbot)
    workspace = coordinator.analysis_workspace
    assert workspace is not None

    assert pane.title_label.text() == "Region list"

    workspace.show_bottom_page(BottomPage.PARAMETERS)
    assert pane.title_label.text() == "Parameters"

    workspace.show_bottom_page(BottomPage.REVIEW)
    assert pane.title_label.text() == "Region list"


def test_parameters_title_appends_focused_region_label(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R2: the Parameters header names the focused Detail region when known."""
    coordinator, pane, _splitter = _attached_pane(qtbot)
    workspace = coordinator.analysis_workspace
    assert workspace is not None
    monkeypatch.setattr(
        DockLayoutCoordinator, "_analysis_detail_region_label", lambda _self: "CIV (1)"
    )

    workspace.show_bottom_page(BottomPage.PARAMETERS)

    assert pane.title_label.text() == "Parameters — CIV (1)"


def test_bottom_pane_visible_only_for_analysis_mode(qtbot: QtBot) -> None:
    """R2: entering Analysis shows the bottom pane; other modes hide it."""
    coordinator, pane, _splitter = _attached_pane(qtbot)

    coordinator._update_analysis_bottom_pane(EditingMode.ANALYSIS)
    assert not pane.isHidden()

    coordinator._update_analysis_bottom_pane(EditingMode.IDENTIFY)
    assert pane.isHidden()

    coordinator._update_analysis_bottom_pane(None)
    assert pane.isHidden()


def test_handle_double_click_toggles_bottom_pane_maximization(qtbot: QtBot) -> None:
    """R2: double-clicking the handle flips maximized and user heights."""
    coordinator, pane, splitter = _attached_pane(qtbot)
    coordinator._analysis_bottom_pane_sized = True
    pane.show()
    splitter.resize(400, 700)
    with qtbot.waitExposed(splitter):
        splitter.show()
    splitter.setSizes([440, 260])
    user_height = splitter.sizes()[1]

    splitter.handle_double_clicked.emit()
    sizes = splitter.sizes()
    assert sizes[0] == LayoutMetrics.SPECTRUM_MIN_HEIGHT
    assert sizes[1] == sum(sizes) - LayoutMetrics.SPECTRUM_MIN_HEIGHT

    splitter.handle_double_clicked.emit()
    assert splitter.sizes()[1] == user_height


def test_application_stylesheet_styles_grip_splitter_handles() -> None:
    """F4/R2: main and Analysis center splitter handles have visible styling."""
    stylesheet = get_application_stylesheet()

    assert "QSplitter#mainSplitter::handle" in stylesheet
    assert "QSplitter#mainSplitter::handle:hover" in stylesheet
    assert "QSplitter#analysisCenterSplitter::handle" in stylesheet
    assert "QSplitter#analysisCenterSplitter::handle:hover" in stylesheet
