"""Tests for semantic Analysis destinations in the manual manifest."""

from __future__ import annotations

import pytest

from chappy.core.editing_mode import EditingMode
from chappy.gui.modes.common.analysis_navigation import AnalysisSurface
from chappy_user_manual_generator.models import CaptureDestination, PanelDestination
from chappy_user_manual_generator.user_manual_manifest import load_user_manual_manifest


def test_manifest_uses_semantic_analysis_destinations_and_outputs() -> None:
    manifest = load_user_manual_manifest("test")
    screen = manifest.screens[0]

    assert tuple(destination.scope for destination in screen.destinations) == (
        "start",
        "identify",
        "analysis_overview",
        "analysis_structure",
        "analysis_region_detail",
        "continuum",
    )
    assert tuple(flow.slug for flow in manifest.flows) == (
        "start-data-import",
        "identify-workflow",
        "analysis-region-detail",
        "analysis-structure",
        "continuum-adjustment",
    )
    assert all(
        flow.destination is not None and flow.destination.mode is not None
        for flow in manifest.flows
    )


@pytest.mark.parametrize(
    ("mode", "panel", "surface"),
    [
        (EditingMode.IDENTIFY, PanelDestination.ANALYSIS_OVERVIEW, AnalysisSurface.OVERVIEW),
        (EditingMode.ANALYSIS, PanelDestination.ANALYSIS_REGION_DETAIL, None),
        (EditingMode.ANALYSIS, PanelDestination.ANALYSIS_STRUCTURE, AnalysisSurface.REGION_DETAIL),
    ],
)
def test_capture_destination_rejects_contradictory_semantics(
    mode: EditingMode, panel: PanelDestination, surface: AnalysisSurface | None
) -> None:
    with pytest.raises(ValueError):
        CaptureDestination(mode, panel, surface)
