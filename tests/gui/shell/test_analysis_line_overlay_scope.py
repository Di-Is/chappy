"""Regression tests for Analysis confirmed-line overlay scoping."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.editing_mode import EditingMode
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.modes.analysis.contracts import PanelState
from chappy.gui.modes.analysis.intents import OpenAnalysisRegionIntent
from chappy.gui.modes.analysis.surface_coordinator import AnalysisSurfaceCoordinator
from chappy.gui.modes.common.analysis_navigation import AnalysisNavigationState, AnalysisSurface
from chappy.gui.shell.analysis_surface_ui_adapter import (
    AnalysisSurfaceUiAdapter,
    AnalysisSurfaceUiPorts,
)
from chappy.gui.shell.main_window import MainWindow
from chappy.gui.shell.mode_line_overlay_adapter import LineOverlayWindow, ModeLineOverlayAdapter

if TYPE_CHECKING:
    from chappy.gui.modes.analysis.surface_policy import AnalysisSurfaceUiPolicy
    from chappy.gui.spectrum.policy import SpectrumPolicy
    from chappy.gui.utils.absorption_overlays import RegionPayload


class _Navigation:
    """Hold Analysis focus and surface state for the shell test."""

    def __init__(self, project: SpectroscopyProject) -> None:
        self._project = project
        self.state = AnalysisNavigationState()

    def focus_region(self, region_id: str) -> bool:
        """Focus an existing project region."""
        if region_id not in self._project.absorption_regions:
            return False
        self.state = self.state.with_focused_region(region_id)
        return True

    def set_surface(self, surface: AnalysisSurface) -> None:
        """Persist the selected Analysis surface."""
        self.state = self.state.with_surface(surface)

    def clear_focus_if(self, region_id: str) -> None:
        """Clear the focused region when it matches."""
        if self.state.focused_region_id == region_id:
            self.state = self.state.with_focused_region(None).with_surface(
                AnalysisSurface.OVERVIEW
            )


class _SpectrumView:
    """Record spectrum policies and confirmed overlay payloads."""

    def __init__(self) -> None:
        self.policies: list[SpectrumPolicy] = []
        self.region_updates: list[list[RegionPayload]] = []

    def apply_policy(self, policy: SpectrumPolicy) -> None:
        """Record an applied spectrum policy."""
        self.policies.append(policy)

    def set_absorption_line_regions(self, regions: list[RegionPayload]) -> None:
        """Record one complete confirmed-region update."""
        self.region_updates.append(regions)


class _Workspace:
    """Accept Analysis surface policies and focus requests."""

    def apply_policy(self, policy: AnalysisSurfaceUiPolicy) -> None:
        """Accept one Analysis workspace policy."""
        _ = policy

    def focus_right_page(self) -> None:
        """Accept a Detail focus request."""

    def focus_bottom_page(self) -> None:
        """Accept an Overview focus request."""

    def announce(self, message: str) -> None:
        """Accept an accessibility announcement."""
        _ = message


class _VisiblePane:
    """Accept shell visibility changes."""

    def setVisible(self, visible: bool) -> None:
        """Accept a visibility update."""
        _ = visible


class _Guard:
    """Allow all tested Analysis transitions."""

    def fit_running(self) -> bool:
        """Report no running fit."""
        return False

    def commit_pending_editor(self) -> bool:
        """Allow leaving Region Detail."""
        return True

    def focus_invalid_editor(self) -> None:
        """Reject an unexpected invalid-editor path."""
        raise AssertionError("No invalid editor is expected")


class _Presentation:
    """Accept destination surface refreshes."""

    def refresh_overview(self) -> None:
        """Accept an Overview refresh."""

    def refresh_region_detail(self, region_id: str) -> None:
        """Accept a Region Detail refresh."""
        _ = region_id


class _ModeShell:
    """Route Analysis refreshes to the production overlay adapter."""

    def __init__(self, overlays: ModeLineOverlayAdapter) -> None:
        self._overlays = overlays

    def get_current_mode(self) -> EditingMode:
        """Return Analysis as the displayed top-level mode."""
        return EditingMode.ANALYSIS

    def refresh_line_overlays_for_mode(self, mode: EditingMode) -> None:
        """Refresh confirmed overlays for Analysis."""
        assert mode is EditingMode.ANALYSIS
        self._overlays.show_confirmed_line_overlays()


class _Window:
    """Expose the production MainWindow overlay-scope behavior."""

    def __init__(
        self,
        *,
        project: SpectroscopyProject,
        navigation: _Navigation,
        spectrum_view: _SpectrumView,
    ) -> None:
        self.current_project = project
        self.identify_coordinator = None
        self.view_stack = SimpleNamespace(spectrum_view=spectrum_view)
        self._analysis_navigation = navigation
        self._analysis_surface_coordinator: AnalysisSurfaceCoordinator | None = None
        self.mode_shell_coordinator: _ModeShell | None = None

    @property
    def confirmed_line_overlay_region_id(self) -> str | None:
        """Delegate confirmed-line scope selection to MainWindow."""
        return MainWindow.confirmed_line_overlay_region_id.__get__(self, MainWindow)


def _project() -> SpectroscopyProject:
    """Build two regions with one confirmed line each."""
    project = SpectroscopyProject(name="analysis-line-overlay-scope")
    for region_id, line_id, rest_wavelength in (
        ("region-1", "line-1", 1215.67),
        ("region-2", "line-2", 1548.2),
    ):
        project.absorption_regions[region_id] = AbsorptionRegion(
            region_id=region_id, line_ids=[line_id]
        )
        project.absorption_lines[line_id] = AbsorptionLine(
            line_id=line_id,
            species="H I",
            rest_wavelength=rest_wavelength,
            center_z=1.0,
            window_kms=120.0,
            multiplet_label="transition",
            transition_name="transition",
            oscillator_strength=0.1,
            gamma_value=1.0e8,
            region_id=region_id,
        )
    return project


def test_detail_filters_confirmed_overlays_and_overview_restores_all_lines() -> None:
    """Surface changes must redraw Detail scope and then restore Overview scope."""
    project = _project()
    navigation = _Navigation(project)
    spectrum_view = _SpectrumView()
    window = _Window(project=project, navigation=navigation, spectrum_view=spectrum_view)
    overlays = ModeLineOverlayAdapter(cast("LineOverlayWindow", window))
    window.mode_shell_coordinator = _ModeShell(overlays)
    ui_adapter = AnalysisSurfaceUiAdapter(
        AnalysisSurfaceUiPorts(
            workspace=cast("object", _Workspace()),
            spectrum_view=cast("object", spectrum_view),
            bottom_pane=cast("object", _VisiblePane()),
            data_control=cast("object", _VisiblePane()),
            actions={},
            refresh_confirmed_line_overlays=lambda: MainWindow._refresh_analysis_line_overlays(
                cast("MainWindow", window)
            ),
        )
    )
    surface = AnalysisSurfaceCoordinator(
        navigation=navigation,
        workspace=_Workspace(),
        policies=ui_adapter,
        guard=_Guard(),
        presentation=_Presentation(),
    )
    window._analysis_surface_coordinator = surface

    assert surface.open_region(OpenAnalysisRegionIntent("region-1")) is True

    assert [region["id"] for region in spectrum_view.region_updates[-1]] == ["line-1"]
    assert spectrum_view.policies[-1].plot_policy.display_command.render_absorption_line_labels

    assert surface.back_to_overview() is True

    assert {region["id"] for region in spectrum_view.region_updates[-1]} == {"line-1", "line-2"}


def test_detail_without_navigation_focus_restores_all_line_overlays() -> None:
    """A stale Detail panel state must not prevent the all-line overlay fallback."""
    project = _project()
    navigation = _Navigation(project)
    spectrum_view = _SpectrumView()
    window = _Window(project=project, navigation=navigation, spectrum_view=spectrum_view)
    overlays = ModeLineOverlayAdapter(cast("LineOverlayWindow", window))
    window.mode_shell_coordinator = _ModeShell(overlays)
    ui_adapter = AnalysisSurfaceUiAdapter(
        AnalysisSurfaceUiPorts(
            workspace=cast("object", _Workspace()),
            spectrum_view=cast("object", spectrum_view),
            bottom_pane=cast("object", _VisiblePane()),
            data_control=cast("object", _VisiblePane()),
            actions={},
            refresh_confirmed_line_overlays=lambda: MainWindow._refresh_analysis_line_overlays(
                cast("MainWindow", window)
            ),
        )
    )
    surface = AnalysisSurfaceCoordinator(
        navigation=navigation,
        workspace=_Workspace(),
        policies=ui_adapter,
        guard=_Guard(),
        presentation=_Presentation(),
    )
    window._analysis_surface_coordinator = surface
    assert surface.open_region(OpenAnalysisRegionIntent("region-1")) is True

    navigation.state = navigation.state.with_focused_region(None)
    assert surface.panel_state is PanelState.REGION_DETAIL

    overlays.show_confirmed_line_overlays()

    assert {region["id"] for region in spectrum_view.region_updates[-1]} == {"line-1", "line-2"}
