"""Stacked right-side and bottom-dock page owner for Analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QStackedWidget, QWidget

from chappy.gui.modes.analysis.contracts import BottomPage, RightPage
from chappy.gui.visual_tokens import LayoutMetrics

if TYPE_CHECKING:
    from chappy.gui.modes.analysis.contracts import AnalysisAnnouncementPort
    from chappy.gui.modes.analysis.surface_policy import AnalysisSurfaceUiPolicy


@dataclass(frozen=True, slots=True)
class AnalysisWorkspacePages:
    """Concrete widgets registered in the two Analysis stacks."""

    summary: QWidget
    structure: QWidget
    detail: QWidget
    review: QWidget
    parameters: QWidget


@dataclass(frozen=True, slots=True)
class AnalysisWorkspaceAccessibility:
    """Translated accessible labels supplied by the composition boundary."""

    right_stack_name: str
    bottom_stack_name: str

    def __post_init__(self) -> None:
        """Reject labels that provide no accessible text."""
        if not self.right_stack_name.strip() or not self.bottom_stack_name.strip():
            msg = "Analysis workspace accessible names must not be empty."
            raise ValueError(msg)


class AnalysisWorkspace:
    """Own and switch the Analysis stacks without owning shell layout policy."""

    def __init__(
        self,
        pages: AnalysisWorkspacePages,
        *,
        accessibility: AnalysisWorkspaceAccessibility,
        announcement_port: AnalysisAnnouncementPort,
        parent: QWidget | None = None,
    ) -> None:
        page_widgets = (
            pages.summary,
            pages.structure,
            pages.detail,
            pages.review,
            pages.parameters,
        )
        if len({id(widget) for widget in page_widgets}) != len(page_widgets):
            msg = "Each Analysis workspace page requires a distinct widget."
            raise ValueError(msg)
        self.right_stack = QStackedWidget(parent)
        self.right_stack.setObjectName("analysisRightStack")
        self.right_stack.setAccessibleName(accessibility.right_stack_name)
        self.right_stack.setMinimumWidth(LayoutMetrics.ANALYSIS_RIGHT_MIN_WIDTH)
        self.bottom_stack = QStackedWidget(parent)
        self.bottom_stack.setObjectName("analysisBottomStack")
        self.bottom_stack.setAccessibleName(accessibility.bottom_stack_name)
        self.bottom_stack.setMinimumHeight(144)
        self._announcement_port = announcement_port
        self._right_pages = {
            RightPage.SUMMARY: pages.summary,
            RightPage.STRUCTURE: pages.structure,
            RightPage.DETAIL: pages.detail,
        }
        self._bottom_pages = {
            BottomPage.REVIEW: pages.review,
            BottomPage.PARAMETERS: pages.parameters,
        }
        for widget in self._right_pages.values():
            self.right_stack.addWidget(widget)
        for widget in self._bottom_pages.values():
            self.bottom_stack.addWidget(widget)
        self.show_right_page(RightPage.SUMMARY)
        self.show_bottom_page(BottomPage.REVIEW)

    @property
    def current_right_page(self) -> RightPage:
        """Return the typed identity of the current right-side page."""
        current = self.right_stack.currentWidget()
        for page, widget in self._right_pages.items():
            if widget is current:
                return page
        msg = "Current Analysis right-side widget is not a registered page."
        raise RuntimeError(msg)

    @property
    def current_bottom_page(self) -> BottomPage:
        """Return the typed identity of the current bottom-dock page."""
        current = self.bottom_stack.currentWidget()
        for page, widget in self._bottom_pages.items():
            if widget is current:
                return page
        msg = "Current Analysis bottom widget is not a registered page."
        raise RuntimeError(msg)

    def show_right_page(self, page: RightPage) -> None:
        """Display a registered right-side page."""
        self.right_stack.setCurrentWidget(self._right_pages[page])

    def show_bottom_page(self, page: BottomPage) -> None:
        """Display a registered bottom-dock page."""
        self.bottom_stack.setCurrentWidget(self._bottom_pages[page])

    def apply_policy(self, policy: AnalysisSurfaceUiPolicy) -> None:
        """Apply both page selections from one immutable policy."""
        self.show_right_page(policy.right_page)
        self.show_bottom_page(policy.bottom_page)

    def focus_right_page(self, page: RightPage | None = None) -> None:
        """Move keyboard focus to a selected or current right-side page."""
        if page is not None:
            self.show_right_page(page)
        self._right_pages[self.current_right_page].setFocus()

    def focus_bottom_page(self, page: BottomPage | None = None) -> None:
        """Move keyboard focus to a selected or current bottom-dock page."""
        if page is not None:
            self.show_bottom_page(page)
        self._bottom_pages[self.current_bottom_page].setFocus()

    def announce(self, message: str) -> None:
        """Publish a non-empty message through the accessible status boundary."""
        if not message.strip():
            msg = "Analysis accessibility announcement must not be empty."
            raise ValueError(msg)
        self._announcement_port.announce(message)


__all__ = ["AnalysisWorkspace", "AnalysisWorkspaceAccessibility", "AnalysisWorkspacePages"]
