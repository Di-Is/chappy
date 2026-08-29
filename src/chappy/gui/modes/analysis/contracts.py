"""Typed contracts and semantic state for the Analysis workspace."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from chappy.gui.modes.analysis.surface_policy import AnalysisSurfaceUiPolicy


class RightPage(StrEnum):
    """Pages hosted by the Analysis right-side stack."""

    SUMMARY = "summary"
    STRUCTURE = "structure"
    DETAIL = "detail"


class BottomPage(StrEnum):
    """Pages hosted by the single Analysis bottom dock stack."""

    REVIEW = "review"
    PARAMETERS = "parameters"


class PanelState(StrEnum):
    """User-visible Analysis panel state, including the nested structure editor."""

    OVERVIEW_SUMMARY = "overview_summary"
    OVERVIEW_STRUCTURE = "overview_structure"
    REGION_DETAIL = "region_detail"


class SpectrumProfile(StrEnum):
    """Analysis-owned semantic profile applied to the shared spectrum by the shell."""

    OVERVIEW = "overview"
    REGION_DETAIL = "region_detail"


class AnalysisAnnouncementPort(Protocol):
    """Accessible status announcement capability required by the workspace."""

    def announce(self, message: str) -> None:
        """Announce a non-empty user-visible status message."""


class AnalysisSurfacePresentationPort(Protocol):
    """Destination-surface rendering invoked on every Analysis surface entry."""

    def refresh_overview(self) -> None:
        """Rebuild the Overview review table from current project state."""

    def refresh_region_detail(self, region_id: str) -> None:
        """Rebuild the Region Detail panel for one region from current project state."""


class AnalysisWorkspacePort(Protocol):
    """Page, focus, and announcement operations used by Analysis coordinators."""

    @property
    def current_right_page(self) -> RightPage:
        """Return the currently displayed right-side page."""

    @property
    def current_bottom_page(self) -> BottomPage:
        """Return the currently displayed bottom-dock page."""

    def show_right_page(self, page: RightPage) -> None:
        """Display a registered right-side page."""

    def show_bottom_page(self, page: BottomPage) -> None:
        """Display a registered bottom-dock page."""

    def apply_policy(self, policy: AnalysisSurfaceUiPolicy) -> None:
        """Apply both page selections from one immutable policy."""

    def focus_right_page(self, page: RightPage | None = None) -> None:
        """Move keyboard focus to a right-side page."""

    def focus_bottom_page(self, page: BottomPage | None = None) -> None:
        """Move keyboard focus to a bottom-dock page."""

    def announce(self, message: str) -> None:
        """Publish an accessible status announcement."""


__all__ = [
    "AnalysisAnnouncementPort",
    "AnalysisSurfacePresentationPort",
    "AnalysisWorkspacePort",
    "BottomPage",
    "PanelState",
    "RightPage",
    "SpectrumProfile",
]
