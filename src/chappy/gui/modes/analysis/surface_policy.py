"""Pure semantic UI policies for Analysis workspace panel states."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from chappy.gui.modes.analysis.contracts import BottomPage, PanelState, RightPage, SpectrumProfile
from chappy.gui.modes.common.analysis_navigation import AnalysisSurface


class AnalysisSemanticAction(StrEnum):
    """Stable Analysis operations whose availability varies by panel state."""

    OPEN_REGION = "open_region"
    OPEN_STRUCTURE_EDITOR = "open_structure_editor"
    CLOSE_STRUCTURE_EDITOR = "close_structure_editor"
    RETURN_TO_OVERVIEW = "return_to_overview"
    FIT = "fit"
    EXPORT = "export"
    TOGGLE_VELOCITY = "toggle_velocity"
    STRUCTURE_DELETE = "structure_delete"


@dataclass(frozen=True, slots=True)
class AnalysisSurfaceUiPolicy:
    """Complete semantic UI state committed for one Analysis panel state."""

    surface: AnalysisSurface
    panel_state: PanelState
    spectrum_profile: SpectrumProfile
    right_page: RightPage
    bottom_page: BottomPage
    data_control_visible: bool
    enabled_actions: frozenset[AnalysisSemanticAction]

    def allows(self, action: AnalysisSemanticAction) -> bool:
        """Return whether a semantic operation is enabled by this policy."""
        return action in self.enabled_actions


_POLICIES: dict[PanelState, AnalysisSurfaceUiPolicy] = {
    PanelState.OVERVIEW_SUMMARY: AnalysisSurfaceUiPolicy(
        surface=AnalysisSurface.OVERVIEW,
        panel_state=PanelState.OVERVIEW_SUMMARY,
        spectrum_profile=SpectrumProfile.OVERVIEW,
        right_page=RightPage.SUMMARY,
        bottom_page=BottomPage.REVIEW,
        data_control_visible=True,
        enabled_actions=frozenset(
            {AnalysisSemanticAction.OPEN_REGION, AnalysisSemanticAction.OPEN_STRUCTURE_EDITOR}
        ),
    ),
    PanelState.OVERVIEW_STRUCTURE: AnalysisSurfaceUiPolicy(
        surface=AnalysisSurface.OVERVIEW,
        panel_state=PanelState.OVERVIEW_STRUCTURE,
        spectrum_profile=SpectrumProfile.OVERVIEW,
        right_page=RightPage.STRUCTURE,
        bottom_page=BottomPage.REVIEW,
        data_control_visible=True,
        enabled_actions=frozenset(
            {
                AnalysisSemanticAction.CLOSE_STRUCTURE_EDITOR,
                AnalysisSemanticAction.RETURN_TO_OVERVIEW,
                AnalysisSemanticAction.STRUCTURE_DELETE,
            }
        ),
    ),
    PanelState.REGION_DETAIL: AnalysisSurfaceUiPolicy(
        surface=AnalysisSurface.REGION_DETAIL,
        panel_state=PanelState.REGION_DETAIL,
        spectrum_profile=SpectrumProfile.REGION_DETAIL,
        right_page=RightPage.DETAIL,
        bottom_page=BottomPage.PARAMETERS,
        data_control_visible=True,
        enabled_actions=frozenset(
            {
                AnalysisSemanticAction.RETURN_TO_OVERVIEW,
                AnalysisSemanticAction.FIT,
                AnalysisSemanticAction.EXPORT,
                AnalysisSemanticAction.TOGGLE_VELOCITY,
            }
        ),
    ),
}


def policy_for_panel_state(panel_state: PanelState) -> AnalysisSurfaceUiPolicy:
    """Return the immutable policy for an Analysis panel state."""
    return _POLICIES[panel_state]


def default_policy_for_surface(surface: AnalysisSurface) -> AnalysisSurfaceUiPolicy:
    """Return the default panel policy entered for an Analysis surface."""
    if surface is AnalysisSurface.OVERVIEW:
        return policy_for_panel_state(PanelState.OVERVIEW_SUMMARY)
    return policy_for_panel_state(PanelState.REGION_DETAIL)


__all__ = [
    "AnalysisSemanticAction",
    "AnalysisSurfaceUiPolicy",
    "default_policy_for_surface",
    "policy_for_panel_state",
]
