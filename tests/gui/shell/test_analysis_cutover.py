"""Focused shell contracts for the atomic Analysis cutover."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from chappy.core.absorption.models import UNASSIGNED_REGION_ID, AbsorptionLine, AbsorptionRegion
from chappy.core.editing_mode import EditingMode
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.modes.common.analysis_navigation import AnalysisSurface, OpenAnalysisRegionIntent
from chappy.gui.common.shared_operations import AnalysisOperationSurface
from chappy.gui.shell.main_window import MainWindow


def _project() -> SpectroscopyProject:
    project = SpectroscopyProject(name="analysis-cutover")
    project.absorption_lines["line-1"] = AbsorptionLine(
        line_id="line-1",
        species="H I",
        rest_wavelength=1215.67,
        center_z=1.0,
        window_kms=120.0,
        multiplet_label="Ly alpha",
        transition_name="Ly alpha",
        oscillator_strength=0.1,
        gamma_value=1.0e8,
        region_id="region-1",
    )
    project.absorption_regions["region-1"] = AbsorptionRegion(
        region_id="region-1", line_ids=["line-1"]
    )
    return project


def test_identify_open_intent_uses_validate_focus_destination_mode_order() -> None:
    calls: list[tuple[str, object]] = []

    class _Navigation:
        def focus_region(self, region_id: str) -> bool:
            calls.append(("focus", region_id))
            return True

        def set_surface(self, surface: AnalysisSurface) -> None:
            calls.append(("surface", surface))

    class _ModeShell:
        def switch_mode(self, mode: EditingMode) -> None:
            calls.append(("mode", mode))

    class _Project:
        def is_region_analysis_capable(self, region_id: str) -> bool:
            calls.append(("validate", region_id))
            return region_id == "region-1"

    window = SimpleNamespace(
        current_project=_Project(),
        _analysis_navigation=_Navigation(),
        mode_shell_coordinator=_ModeShell(),
    )

    MainWindow.handle_identify_open_analysis_region(
        cast("MainWindow", window), OpenAnalysisRegionIntent("region-1")
    )

    assert calls == [
        ("validate", "region-1"),
        ("focus", "region-1"),
        ("surface", AnalysisSurface.REGION_DETAIL),
        ("mode", EditingMode.ANALYSIS),
    ]


def test_identify_open_intent_rejects_invalid_region_before_navigation() -> None:
    window = SimpleNamespace(
        current_project=_project(),
        _analysis_navigation=SimpleNamespace(
            focus_region=lambda _region_id: (_ for _ in ()).throw(AssertionError)
        ),
        mode_shell_coordinator=SimpleNamespace(
            switch_mode=lambda _mode: (_ for _ in ()).throw(AssertionError)
        ),
    )

    MainWindow.handle_identify_open_analysis_region(
        cast("MainWindow", window), OpenAnalysisRegionIntent("missing")
    )


def test_back_to_overview_focuses_current_region_row() -> None:
    calls: list[tuple[str, object]] = []
    panel = SimpleNamespace(
        set_structure_editor_visible=lambda visible: calls.append(("structure", visible)),
        focus_review_region=lambda region_id: calls.append(("focus", region_id)) or True,
    )
    window = SimpleNamespace(
        _analysis_navigation=SimpleNamespace(state=SimpleNamespace(focused_region_id="region-1")),
        _require_analysis_surface_coordinator=lambda: SimpleNamespace(
            back_to_overview=lambda: True
        ),
        _require_dock_coordinator=lambda: SimpleNamespace(organize_panel=panel),
    )

    assert MainWindow.back_to_analysis_overview(cast("MainWindow", window)) is True
    assert calls == [("structure", False), ("focus", "region-1")]


def _tutorial_surface_window(
    focused_region_id: str | None, project: SpectroscopyProject | None
) -> SimpleNamespace:
    window = SimpleNamespace(
        opened=[],
        current_project=project,
        _analysis_navigation=SimpleNamespace(
            state=SimpleNamespace(focused_region_id=focused_region_id)
        ),
    )
    coordinator = SimpleNamespace(
        panel_state=None, open_region=lambda intent: window.opened.append(intent.region_id) or True
    )
    window._require_analysis_surface_coordinator = lambda: coordinator
    window._tutorial_region_exists = MainWindow._tutorial_region_exists.__get__(window)
    window._first_tutorial_region_id = MainWindow._first_tutorial_region_id.__get__(window)
    return window


def test_tutorial_region_detail_falls_back_when_focused_region_is_stale() -> None:
    project = _project()
    window = _tutorial_surface_window("merged-away", project)

    applied = MainWindow._switch_tutorial_analysis_surface(
        cast("MainWindow", window), AnalysisOperationSurface.REGION_DETAIL
    )

    assert applied is True
    assert window.opened == ["region-1"]


def test_tutorial_region_detail_fallback_skips_unassigned_region() -> None:
    project = SpectroscopyProject(name="unassigned-only")
    project.absorption_regions[UNASSIGNED_REGION_ID] = AbsorptionRegion(
        region_id=UNASSIGNED_REGION_ID, line_ids=[]
    )
    window = _tutorial_surface_window(None, project)

    applied = MainWindow._switch_tutorial_analysis_surface(
        cast("MainWindow", window), AnalysisOperationSurface.REGION_DETAIL
    )

    assert applied is False
    assert window.opened == []


def test_tutorial_region_detail_uses_valid_focused_region() -> None:
    project = _project()
    window = _tutorial_surface_window("region-1", project)

    applied = MainWindow._switch_tutorial_analysis_surface(
        cast("MainWindow", window), AnalysisOperationSurface.REGION_DETAIL
    )

    assert applied is True
    assert window.opened == ["region-1"]
