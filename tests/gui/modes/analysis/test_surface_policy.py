"""Tests for pure Analysis surface UI policies and intents."""

from __future__ import annotations

import pytest

from chappy.gui.modes.analysis.contracts import BottomPage, PanelState, RightPage, SpectrumProfile
from chappy.gui.modes.analysis.intents import OpenAnalysisRegionIntent, OpenStructureEditorIntent
from chappy.gui.modes.analysis.surface_policy import (
    AnalysisSemanticAction,
    default_policy_for_surface,
    policy_for_panel_state,
)
from chappy.gui.modes.common.analysis_navigation import AnalysisSurface


@pytest.mark.parametrize(
    ("panel_state", "surface", "profile", "right", "bottom"),
    [
        (
            PanelState.OVERVIEW_SUMMARY,
            AnalysisSurface.OVERVIEW,
            SpectrumProfile.OVERVIEW,
            RightPage.SUMMARY,
            BottomPage.REVIEW,
        ),
        (
            PanelState.OVERVIEW_STRUCTURE,
            AnalysisSurface.OVERVIEW,
            SpectrumProfile.OVERVIEW,
            RightPage.STRUCTURE,
            BottomPage.REVIEW,
        ),
        (
            PanelState.REGION_DETAIL,
            AnalysisSurface.REGION_DETAIL,
            SpectrumProfile.REGION_DETAIL,
            RightPage.DETAIL,
            BottomPage.PARAMETERS,
        ),
    ],
)
def test_panel_policy_selects_consistent_surface_pages(
    panel_state: PanelState,
    surface: AnalysisSurface,
    profile: SpectrumProfile,
    right: RightPage,
    bottom: BottomPage,
) -> None:
    policy = policy_for_panel_state(panel_state)

    assert policy.surface is surface
    assert policy.spectrum_profile is profile
    assert policy.right_page is right
    assert policy.bottom_page is bottom
    assert policy.data_control_visible


def test_structure_editor_is_nested_overview_state() -> None:
    policy = policy_for_panel_state(PanelState.OVERVIEW_STRUCTURE)

    assert policy.surface is AnalysisSurface.OVERVIEW
    assert policy.allows(AnalysisSemanticAction.CLOSE_STRUCTURE_EDITOR)
    assert policy.allows(AnalysisSemanticAction.RETURN_TO_OVERVIEW)
    assert not policy.allows(AnalysisSemanticAction.FIT)


def test_detail_policy_exposes_detail_only_operations() -> None:
    policy = default_policy_for_surface(AnalysisSurface.REGION_DETAIL)

    assert policy.allows(AnalysisSemanticAction.FIT)
    assert policy.allows(AnalysisSemanticAction.TOGGLE_VELOCITY)
    assert policy.allows(AnalysisSemanticAction.RETURN_TO_OVERVIEW)
    assert not policy.allows(AnalysisSemanticAction.OPEN_STRUCTURE_EDITOR)


def test_intents_reject_empty_identifiers() -> None:
    with pytest.raises(ValueError, match="region_id"):
        OpenAnalysisRegionIntent(region_id=" ")
    with pytest.raises(ValueError, match="line_ids item"):
        OpenStructureEditorIntent(line_ids=("line-1", ""))
