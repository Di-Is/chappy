"""Tests for the Analysis right-side and bottom-dock page stacks."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from PySide6.QtWidgets import QWidget

from chappy.gui.modes.analysis.contracts import BottomPage, PanelState, RightPage
from chappy.gui.modes.analysis.surface_policy import policy_for_panel_state
from chappy.gui.modes.analysis.workspace import (
    AnalysisWorkspace,
    AnalysisWorkspaceAccessibility,
    AnalysisWorkspacePages,
)
from chappy.gui.visual_tokens import LayoutMetrics

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class _Announcements:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def announce(self, message: str) -> None:
        self.messages.append(message)


class _FocusPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.focus_requested = False

    def setFocus(self, *args: object) -> None:  # noqa: N802
        """Record the workspace focus request before forwarding it to Qt."""
        self.focus_requested = True
        super().setFocus(*args)


def _workspace(qtbot: QtBot) -> tuple[AnalysisWorkspace, AnalysisWorkspacePages, _Announcements]:
    pages = AnalysisWorkspacePages(
        summary=QWidget(),
        structure=_FocusPage(),
        detail=QWidget(),
        review=QWidget(),
        parameters=QWidget(),
    )
    announcements = _Announcements()
    workspace = AnalysisWorkspace(
        pages,
        accessibility=AnalysisWorkspaceAccessibility(
            right_stack_name="Analysis details", bottom_stack_name="Analysis tables"
        ),
        announcement_port=announcements,
    )
    qtbot.addWidget(workspace.right_stack)
    qtbot.addWidget(workspace.bottom_stack)
    return workspace, pages, announcements


def test_workspace_registers_each_typed_page_once(qtbot: QtBot) -> None:
    workspace, pages, _announcements = _workspace(qtbot)

    assert workspace.right_stack.count() == 3
    assert workspace.bottom_stack.count() == 2
    assert workspace.current_right_page is RightPage.SUMMARY
    assert workspace.current_bottom_page is BottomPage.REVIEW
    assert workspace.right_stack.widget(1) is pages.structure
    assert workspace.bottom_stack.widget(1) is pages.parameters
    assert workspace.right_stack.accessibleName() == "Analysis details"
    assert workspace.bottom_stack.accessibleName() == "Analysis tables"


def test_right_stack_enforces_normative_width_band(qtbot: QtBot) -> None:
    workspace, _pages, _announcements = _workspace(qtbot)

    # 220 is normative (visual_constants.md SIZE.ANALYSIS.RIGHT.MIN.WIDTH).
    assert LayoutMetrics.ANALYSIS_RIGHT_MIN_WIDTH == 220
    assert workspace.right_stack.minimumWidth() == LayoutMetrics.ANALYSIS_RIGHT_MIN_WIDTH


def test_bottom_stack_keeps_review_min_height(qtbot: QtBot) -> None:
    workspace, _pages, _announcements = _workspace(qtbot)

    # 144 keeps the 800x600 review content contract inside the bottom pane.
    assert workspace.bottom_stack.minimumHeight() == 144


def test_apply_policy_switches_right_and_bottom_pages_atomically(qtbot: QtBot) -> None:
    workspace, pages, _announcements = _workspace(qtbot)

    workspace.apply_policy(policy_for_panel_state(PanelState.REGION_DETAIL))

    assert workspace.current_right_page is RightPage.DETAIL
    assert workspace.current_bottom_page is BottomPage.PARAMETERS
    assert workspace.right_stack.currentWidget() is pages.detail
    assert workspace.bottom_stack.currentWidget() is pages.parameters


def test_explicit_focus_can_select_and_focus_a_page(qtbot: QtBot) -> None:
    workspace, pages, _announcements = _workspace(qtbot)

    workspace.focus_right_page(RightPage.STRUCTURE)

    assert workspace.current_right_page is RightPage.STRUCTURE
    assert isinstance(pages.structure, _FocusPage)
    assert pages.structure.focus_requested


def test_announcement_uses_typed_accessibility_port(qtbot: QtBot) -> None:
    workspace, _pages, announcements = _workspace(qtbot)

    workspace.announce("Region was removed")

    assert announcements.messages == ["Region was removed"]
    with pytest.raises(ValueError, match="must not be empty"):
        workspace.announce(" ")


def test_workspace_rejects_reused_page_widget(qtbot: QtBot) -> None:
    shared = QWidget()
    qtbot.addWidget(shared)

    with pytest.raises(ValueError, match="distinct widget"):
        AnalysisWorkspace(
            AnalysisWorkspacePages(
                summary=shared,
                structure=shared,
                detail=QWidget(),
                review=QWidget(),
                parameters=QWidget(),
            ),
            accessibility=AnalysisWorkspaceAccessibility("Right", "Bottom"),
            announcement_port=_Announcements(),
        )
