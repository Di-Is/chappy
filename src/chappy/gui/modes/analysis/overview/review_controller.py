"""Controller for constructing and rendering Analysis Overview review rows."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from PySide6.QtCore import QObject

from chappy.gui.modes.analysis.overview.review_rows import AnalysisOverviewRowsBuilder

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.presentation.analysis import AnalysisReviewRow, AnalysisReviewSummary


class AnalysisOverviewReviewView(Protocol):
    """Rendering boundary implemented by the Overview panel."""

    def render_review(
        self, rows: Sequence[AnalysisReviewRow], summary: AnalysisReviewSummary
    ) -> None:
        """Render typed presentation output without deriving scientific state."""


class AnalysisOverviewReviewController(QObject):
    """Build typed rows from project facts and send them to the panel view."""

    def __init__(
        self,
        *,
        view: AnalysisOverviewReviewView,
        project_provider: Callable[[], SpectroscopyProject | None],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._view = view
        self._project_provider = project_provider
        self._builder = AnalysisOverviewRowsBuilder()

    def refresh(self) -> None:
        """Build and render a current read-only review snapshot."""
        rows, summary = self._builder.build(self._project_provider())
        self._view.render_review(rows, summary)


__all__ = ["AnalysisOverviewReviewController", "AnalysisOverviewReviewView"]
