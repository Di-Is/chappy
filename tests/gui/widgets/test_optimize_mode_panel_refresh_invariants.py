"""Regression tests for side-effect-free Analysis Detail display refreshes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from PySide6.QtCore import QObject

from chappy.application.project_document import ProjectDocument
from chappy.application.project_mapper import project_to_document
from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.analysis import (
    AnalysisArtifact,
    AnalysisRevision,
    FitSummary,
    RegionAnalysisState,
)
from chappy.core.change_set import ChangeSet
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.components.continuum import ContinuumComponent
from chappy.core.components.tie_set import ParameterTieSet
from chappy.core.editing_mode import EditingMode
from chappy.core.masking import MaskDefinition
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.modes.analysis.contracts import BottomPage, RightPage
from chappy.gui.modes.analysis.lifecycle import AnalysisLifecycleCoordinator
from chappy.gui.modes.analysis.region_detail.editor import OptimizeEditor
from chappy.gui.modes.analysis.region_detail.panel import RegionDetailPanel
from chappy.gui.modes.analysis.surface_coordinator import AnalysisSurfaceCoordinator
from chappy.gui.modes.analysis.surface_policy import AnalysisSurfaceUiPolicy
from chappy.gui.modes.common.analysis_navigation import AnalysisNavigationState, AnalysisSurface
from chappy.gui.modes.common.lifecycle import ModeRefreshRequest
from tests.gui.widgets.optimize_panel_helpers import (
    AnalysisFocusRecorder,
    NoOpModelAdditionUseCase,
    build_region_detail_usecases,
)

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class _ModeState(QObject):
    """Mode-state test double used by Detail group selection."""

    def __init__(self) -> None:
        super().__init__()
        self.active_regions: list[AbsorptionRegion | None] = []

    def set_focused_region(
        self, region: AbsorptionRegion | None, *, emit_signal: bool = True
    ) -> ChangeSet:
        """Record the selected region without changing project state."""
        _ = emit_signal
        self.active_regions.append(region)
        return ChangeSet.empty()


@dataclass(frozen=True, slots=True)
class _ScientificSerializationSnapshot:
    """Complete project-file-equivalent scientific state used by refresh tests.

    The typed document includes revisions, artifacts and every FitSummary field,
    line freshness/windows, model parameters, continuum points, tie topology,
    masks, resolution settings, analysis ranges, and project timestamps.
    """

    document: ProjectDocument


@dataclass(slots=True)
class _LifecyclePort:
    """Record required Analysis lifecycle shell-port calls."""

    calls: list[str] = field(default_factory=list)

    def show_confirmed_line_overlays(self) -> None:
        self.calls.append("overlays")

    def show_identify_line_overlays(self) -> None:
        self.calls.append("identify-overlays")

    def clear_line_overlays(self) -> None:
        self.calls.append("clear-overlays")

    def hide_for_identify_mode(self) -> None:
        self.calls.append("identify-velocity")

    def hide_for_analysis(self) -> None:
        self.calls.append("velocity")

    def disable_for_continuum_mode(self) -> None:
        self.calls.append("continuum-velocity")

    def show_continuum(self) -> None:
        self.calls.append("show-continuum")

    def hide_continuum(self) -> None:
        self.calls.append("continuum")


@dataclass(slots=True)
class _Navigation:
    """Navigation state used by the real surface restoration coordinator."""

    state: AnalysisNavigationState
    persisted_surfaces: list[AnalysisSurface] = field(default_factory=list)

    def focus_region(self, _region_id: str) -> bool:
        return True

    def set_surface(self, surface: AnalysisSurface) -> None:
        self.persisted_surfaces.append(surface)


@dataclass(slots=True)
class _Workspace:
    """Minimal workspace port for a read-only surface restore."""

    current_right_page: RightPage = RightPage.SUMMARY
    current_bottom_page: BottomPage = BottomPage.REVIEW

    def show_right_page(self, page: RightPage) -> None:
        self.current_right_page = page

    def show_bottom_page(self, page: BottomPage) -> None:
        self.current_bottom_page = page

    def apply_policy(self, policy: AnalysisSurfaceUiPolicy) -> None:
        self.show_right_page(policy.right_page)
        self.show_bottom_page(policy.bottom_page)

    def focus_right_page(self, page: RightPage | None = None) -> None:
        if page is not None:
            self.show_right_page(page)

    def focus_bottom_page(self, page: BottomPage | None = None) -> None:
        if page is not None:
            self.show_bottom_page(page)

    def announce(self, _message: str) -> None:
        return


@dataclass(slots=True)
class _PolicyPort:
    """Apply policies through the same workspace boundary as production."""

    workspace: _Workspace
    applied: list[AnalysisSurfaceUiPolicy] = field(default_factory=list)

    def apply(self, policy: AnalysisSurfaceUiPolicy) -> None:
        self.applied.append(policy)
        self.workspace.apply_policy(policy)


class _Guard:
    """Inactive transition guard required by surface restoration."""

    def fit_running(self) -> bool:
        return False

    def commit_pending_editor(self) -> bool:
        return True

    def focus_invalid_editor(self) -> None:
        return


@dataclass(slots=True)
class _Presentation:
    """Record surface-entry presentation refreshes without touching a real panel."""

    overview_refreshes: int = 0
    region_detail_refreshes: list[str] = field(default_factory=list)

    def refresh_overview(self) -> None:
        self.overview_refreshes += 1

    def refresh_region_detail(self, region_id: str) -> None:
        self.region_detail_refreshes.append(region_id)


@pytest.fixture
def panel(qtbot: QtBot) -> RegionDetailPanel:
    """Create a Region Detail panel with its required ports."""
    editor = OptimizeEditor()
    parameter_mutation_usecase, tie_set_edit_usecase = build_region_detail_usecases()
    widget = RegionDetailPanel(
        optimize_editor=editor,
        analysis_focus=AnalysisFocusRecorder(),
        mode_state=_ModeState(),
        model_addition_usecase=NoOpModelAdditionUseCase(),
        parameter_mutation_usecase=parameter_mutation_usecase,
        tie_set_edit_usecase=tie_set_edit_usecase,
        velocity_plot_active_provider=lambda: False,
        project_file_path_provider=lambda: None,
    )
    qtbot.addWidget(editor)
    qtbot.addWidget(widget)
    return widget


def _project_with_complete_scientific_state() -> SpectroscopyProject:
    """Create a serializable project exercising every refresh-sensitive fact."""
    project = SpectroscopyProject()
    region_id = "region-1"
    fresh_line = AbsorptionLine(
        line_id="line-fresh",
        species="H I",
        rest_wavelength=1215.67,
        center_z=1.0,
        window_kms=135.0,
        region_id=region_id,
        multiplet_label="H I 1215.7",
        transition_name="H I 1215.7",
        oscillator_strength=0.1,
        gamma_value=1e8,
        needs_optimization=False,
    )
    stale_line = AbsorptionLine(
        line_id="line-stale",
        species="C IV",
        rest_wavelength=1548.20,
        center_z=1.0,
        window_kms=275.0,
        region_id=region_id,
        multiplet_label="C IV 1548.2",
        transition_name="C IV 1548.2",
        oscillator_strength=0.1,
        gamma_value=1e8,
        needs_optimization=True,
    )
    region = AbsorptionRegion(
        region_id=region_id,
        line_ids=[fresh_line.line_id, stale_line.line_id],
        analysis_range=(2430.0, 3110.0),
    )
    project.load_absorption_state(
        regions={region_id: region},
        lines={fresh_line.line_id: fresh_line, stale_line.line_id: stale_line},
    )

    first = AbsorberComponent(
        name="H I component",
        wavelength=fresh_line.rest_wavelength,
        column_density=13.4,
        b_parameter=11.0,
        redshift=fresh_line.center_z,
        oscillator_strength=fresh_line.oscillator_strength,
        gamma=fresh_line.gamma_value,
        component_id="component-fresh",
        group_id=region_id,
    )
    second = AbsorberComponent(
        name="C IV component",
        wavelength=stale_line.rest_wavelength,
        column_density=14.2,
        b_parameter=19.0,
        redshift=stale_line.center_z,
        oscillator_strength=stale_line.oscillator_strength,
        gamma=stale_line.gamma_value,
        component_id="component-stale",
        group_id=region_id,
    )
    first.parameters["column_density"].error = 0.12
    second.parameters["b_parameter"].fixed = True
    project.model.add_component(first)
    project.model.add_component(second)
    fresh_line.model_ids.append(first.id)
    stale_line.model_ids.append(second.id)

    tie_set = ParameterTieSet("shared-redshift", mask=frozenset({"redshift"}), origin="user")
    tie_set.add_component(first)
    tie_set.add_component(second)
    project.model.add_tie_set(tie_set)

    continuum = ContinuumComponent(name="Science continuum")
    continuum.set_continuum_points([(2400.0, 1.01), (2600.0, 0.99), (2900.0, 1.02), (3200.0, 1.0)])
    project.model.add_component(continuum)
    project.model.add_mask_definition(
        MaskDefinition.from_range(
            2500.0, 2510.0, label="Telluric", identifier="mask-1"
        ).with_group_id(region_id)
    )
    project.set_resolution(48_000.0, True)
    project.set_region_analysis_state(
        RegionAnalysisState(
            region_id=region_id,
            current_revision=AnalysisRevision(7),
            artifact=AnalysisArtifact(
                region_id=region_id,
                source_revision=AnalysisRevision(6),
                fit_summary=FitSummary(
                    chi_squared=12.5,
                    reduced_chi_squared=1.25,
                    degrees_of_freedom=10.0,
                    n_parameters=4,
                    n_function_evaluations=17,
                ),
            ),
        )
    )
    project.modified = datetime(2025, 1, 2, 3, 4, tzinfo=UTC)
    return project


def _scientific_snapshot(project: SpectroscopyProject) -> _ScientificSerializationSnapshot:
    """Capture the same typed scientific payload written by project persistence."""
    return _ScientificSerializationSnapshot(document=project_to_document(project))


def test_set_project_preserves_complete_scientific_state(panel: RegionDetailPanel) -> None:
    """Assigning a project for display must preserve its serialized science."""
    project = _project_with_complete_scientific_state()
    before = _scientific_snapshot(project)

    panel.set_project(project)

    assert _scientific_snapshot(project) == before


def test_regular_refresh_preserves_complete_scientific_state(panel: RegionDetailPanel) -> None:
    """A normal Detail refresh must preserve the complete serialized science."""
    project = _project_with_complete_scientific_state()
    panel.set_project(project)
    before = _scientific_snapshot(project)

    panel.refresh()

    assert _scientific_snapshot(project) == before


def test_history_refresh_preserves_complete_scientific_state(panel: RegionDetailPanel) -> None:
    """A history refresh must preserve the restored complete scientific state."""
    project = _project_with_complete_scientific_state()
    panel.set_project(project)
    before = _scientific_snapshot(project)

    panel.refresh_for_history("region-1")

    assert _scientific_snapshot(project) == before


def test_analysis_activation_and_detail_restore_preserve_complete_scientific_state() -> None:
    """Analysis activation and persisted Detail restore are display-only operations."""
    project = _project_with_complete_scientific_state()
    lifecycle_port = _LifecyclePort()
    lifecycle = AnalysisLifecycleCoordinator(lifecycle_port, lifecycle_port)
    navigation = _Navigation(
        AnalysisNavigationState(
            surface=AnalysisSurface.REGION_DETAIL, focused_region_id="region-1"
        )
    )
    workspace = _Workspace()
    policies = _PolicyPort(workspace)
    surfaces = AnalysisSurfaceCoordinator(
        navigation=navigation,
        workspace=workspace,
        policies=policies,
        guard=_Guard(),
        presentation=_Presentation(),
    )
    before = _scientific_snapshot(project)

    lifecycle.set_project(project)
    lifecycle.activate()
    lifecycle.refresh(ModeRefreshRequest(mode=EditingMode.ANALYSIS, reason="project-restored"))
    surfaces.restore()

    assert lifecycle.project is project
    assert lifecycle.active is True
    assert workspace.current_right_page is RightPage.DETAIL
    assert workspace.current_bottom_page is BottomPage.PARAMETERS
    assert navigation.persisted_surfaces == []
    assert _scientific_snapshot(project) == before


def test_analysis_overview_restore_preserves_complete_scientific_state() -> None:
    """Restoring Overview applies only UI policy and never rewrites project science."""
    project = _project_with_complete_scientific_state()
    navigation = _Navigation(AnalysisNavigationState(surface=AnalysisSurface.OVERVIEW))
    workspace = _Workspace(
        current_right_page=RightPage.DETAIL, current_bottom_page=BottomPage.PARAMETERS
    )
    policies = _PolicyPort(workspace)
    surfaces = AnalysisSurfaceCoordinator(
        navigation=navigation,
        workspace=workspace,
        policies=policies,
        guard=_Guard(),
        presentation=_Presentation(),
    )
    before = _scientific_snapshot(project)

    surfaces.restore()

    assert workspace.current_right_page is RightPage.SUMMARY
    assert workspace.current_bottom_page is BottomPage.REVIEW
    assert navigation.persisted_surfaces == []
    assert _scientific_snapshot(project) == before
