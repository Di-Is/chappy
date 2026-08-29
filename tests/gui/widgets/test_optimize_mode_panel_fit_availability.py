"""Tests for RegionDetailPanel fit availability reasons and action hierarchy."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, cast

import numpy as np
import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QScrollArea, QVBoxLayout

from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.analysis import FitSummary
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.core.spectrum import Spectrum
from chappy.gui.modes.analysis.region_detail.editor import OptimizeEditor
from chappy.gui.modes.analysis.region_detail.panel import RegionDetailPanel
from chappy.presentation.optimize import (
    FitBlockedReason,
    FitFailedView,
    FitReadyView,
    FitRunningView,
)
from tests.gui.widgets.optimize_panel_helpers import (
    AnalysisFocusRecorder,
    NoOpModelAdditionUseCase,
    build_region_detail_usecases,
)

if TYPE_CHECKING:
    from contextlib import AbstractContextManager

    from pytestqt.qtbot import QtBot

    from chappy.application.optimize import ModelAdditionRequest, ModelAdditionResult
    from chappy.gui.modes.analysis.region_detail.adapters.history_adapter import (
        OptimizeHistoryRecorder,
    )


class _ModeState(QObject):
    """Mode state test double that enables group selection."""

    group_removed = Signal(str)


@pytest.fixture
def panel(qtbot: "QtBot") -> RegionDetailPanel:
    """Create an optimize panel for fit availability tests."""
    editor = OptimizeEditor()
    qtbot.addWidget(editor)
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
    qtbot.addWidget(widget)
    return widget


def _make_line(line_id: str, *, region_id: str) -> AbsorptionLine:
    """Create a minimal AbsorptionLine for testing."""
    return AbsorptionLine(
        line_id=line_id,
        species="H I",
        rest_wavelength=1215.67,
        center_z=1.0,
        window_kms=150.0,
        region_id=region_id,
        multiplet_label="",
        transition_name="H I 1215.7",
        oscillator_strength=0.4164,
        gamma_value=6.265e8,
    )


def _project_with_spectrum() -> SpectroscopyProject:
    """Create a project whose model owns an observed spectrum."""
    project = SpectroscopyProject()
    wavelength = np.linspace(2400.0, 2470.0, 50)
    project.model.set_observed_spectrum(
        Spectrum(wavelength=wavelength, flux=np.ones_like(wavelength))
    )
    return project


def _add_region_with_line(project: SpectroscopyProject, *, with_component: bool) -> None:
    """Add one region and line, optionally with an absorber component."""
    line = _make_line("line-1", region_id="region-1")
    if with_component:
        component = AbsorberComponent(
            name="H I",
            wavelength=1215.67,
            column_density=14.0,
            b_parameter=10.0,
            redshift=1.0,
            oscillator_strength=0.4164,
            gamma=6.265e8,
        )
        project.model.add_component(component)
        line.model_ids = [component.id]
    project.absorption_lines[line.line_id] = line
    project.absorption_regions["region-1"] = AbsorptionRegion(
        region_id="region-1", line_ids=[line.line_id]
    )


def test_no_project_reports_missing_spectrum(panel: RegionDetailPanel) -> None:
    """Without a project the disabled fit surfaces the spectrum prerequisite."""
    assert panel._fit_blocked_reason() is FitBlockedReason.NO_SPECTRUM
    assert not panel._actions_view._optimize_button.isEnabled()
    assert panel._actions_view._optimize_button.toolTip() == "Load a spectrum to enable fitting."
    assert panel._actions_view._summary_note_label.text() == "Load a spectrum to enable fitting."
    assert panel._actions_view._summary_state_value.text() == "—"
    assert panel._actions_view.add_model_button().isHidden()
    assert panel._actions_view._export_button.isHidden()


def test_spectrum_without_region_reports_region_selection(panel: RegionDetailPanel) -> None:
    """With a spectrum but no selectable region the reason names region selection."""
    panel.set_project(_project_with_spectrum())

    assert panel._fit_blocked_reason() is FitBlockedReason.NO_REGION_SELECTED
    assert not panel._actions_view._optimize_button.isEnabled()
    assert panel._actions_view._summary_note_label.text() == "Select a region to enable fitting."


def test_empty_region_shows_add_component_cta_as_primary(panel: RegionDetailPanel) -> None:
    """A region without components surfaces a primary add-component CTA."""
    project = _project_with_spectrum()
    _add_region_with_line(project, with_component=False)
    panel.set_project(project)
    panel.refresh()

    assert panel._fit_blocked_reason() is FitBlockedReason.NO_MODEL_COMPONENTS
    assert not panel._actions_view.add_model_button().isHidden()
    assert panel._actions_view.add_model_button().isEnabled()
    assert panel._actions_view.add_model_button().property("variant") == "primary"
    assert panel._actions_view.add_model_button().text() == "Add Component"
    assert "H I 1215.7" in panel._actions_view.add_model_button().toolTip()
    assert panel._actions_view._optimize_button.isHidden()
    assert panel._actions_view._export_button.isHidden()
    expected = "Add a model component to this region to enable fitting."
    assert panel._actions_view._summary_note_label.text() == expected
    assert panel._actions_view._summary_component_value.text() == "0"


def test_region_with_component_is_ready_to_fit(panel: RegionDetailPanel) -> None:
    """All prerequisites satisfied enables fit as the primary action."""
    project = _project_with_spectrum()
    _add_region_with_line(project, with_component=True)
    panel.set_project(project)
    panel.refresh()

    assert panel._fit_blocked_reason() is None
    assert not panel._actions_view._optimize_button.isHidden()
    assert panel._actions_view._optimize_button.isEnabled()
    assert panel._actions_view._optimize_button.toolTip() == "Run fit (F5)"
    assert panel._actions_view._optimize_button.property("variant") == "primary"
    assert panel._actions_view._summary_state_value.text() == "Not fitted"
    assert panel._actions_view._summary_note_label.text() == "Run a fit to see results here."
    assert panel._actions_view._summary_component_value.text() == "1"
    assert not panel._actions_view._export_button.isHidden()
    assert not panel._actions_view._export_button.isEnabled()
    assert panel._actions_view._export_button.property("variant") == "secondary"
    assert panel._actions_view.add_model_button().isHidden()


def test_fitted_region_promotes_export_to_primary(panel: RegionDetailPanel) -> None:
    """A region with up-to-date fit evidence makes export the primary action."""
    project = _project_with_spectrum()
    _add_region_with_line(project, with_component=True)
    panel.set_project(project)
    panel.refresh()

    panel._group_selection_controller.record_successful_fit(
        project, "region-1", FitSummary(chi_squared=1.234, reduced_chi_squared=1.08)
    )
    panel._update_optimize_button_state()

    assert panel._actions_view._export_button.isEnabled()
    assert panel._actions_view._export_button.property("variant") == "primary"
    assert panel._actions_view._optimize_button.isEnabled()
    assert panel._actions_view._optimize_button.property("variant") == "secondary"
    assert panel._actions_view._summary_state_value.text() == "Fitted"
    assert "χ² = 1.234" in panel._actions_view._summary_fit_value.text()
    assert "χ²ν = 1.080" in panel._actions_view._summary_fit_value.text()
    assert panel._actions_view._summary_note_label.isHidden()
    assert panel._actions_view._summary_note_label.text() == ""


def test_running_fit_disables_button_with_running_reason(panel: RegionDetailPanel) -> None:
    """The editor's is_fitting() flag is surfaced while a fit executes."""
    project = _project_with_spectrum()
    _add_region_with_line(project, with_component=True)
    panel.set_project(project)
    panel.refresh()

    panel.optimize_editor._fit_in_progress = True  # noqa: SLF001 - simulate editor mid-fit
    panel._update_optimize_button_state()

    assert panel._fit_blocked_reason() is FitBlockedReason.FIT_RUNNING
    assert not panel._actions_view._optimize_button.isEnabled()
    assert panel._actions_view._optimize_button.toolTip() == "Optimizing..."

    panel.optimize_editor._fit_in_progress = False  # noqa: SLF001
    panel._update_optimize_button_state()
    assert panel._actions_view._optimize_button.isEnabled()


def test_running_status_is_reflected_in_summary(panel: RegionDetailPanel) -> None:
    """A running fit status is surfaced in the results summary state row."""
    panel._view_state.set_fit_status(FitRunningView())
    panel._update_optimize_button_state()

    assert panel._actions_view._summary_state_value.text() == "Optimizing…"

    panel._view_state.set_fit_status(FitFailedView())
    panel._update_optimize_button_state()

    assert panel._actions_view._summary_state_value.text() == "Optimization failed"


def test_set_project_clears_stale_selection_and_fit_status(panel: RegionDetailPanel) -> None:
    """A new project must not retain a prior project's selected line or fit display."""
    project = _project_with_spectrum()
    _add_region_with_line(project, with_component=True)
    panel.set_project(project)
    panel.refresh()

    panel._view_state.set_selected_line_id("line-1")
    panel._view_state.set_fit_status(FitFailedView())

    panel.set_project(_project_with_spectrum())

    assert panel._view_state.selected_line_id is None
    assert panel._view_state.fit_status == FitReadyView()


def test_actions_are_ordered_above_mask_section(panel: RegionDetailPanel) -> None:
    """The results card must precede the masked-ranges card in the panel."""
    scroll = panel.findChild(QScrollArea, "analysisDetailSidePanelScroll")
    assert scroll is not None
    content = scroll.widget()
    assert content is not None
    content_layout = content.layout()
    assert isinstance(content_layout, QVBoxLayout)

    mask_index = content_layout.indexOf(panel._mask_frame)
    results_index = content_layout.indexOf(panel._actions_view)
    assert mask_index != -1
    assert results_index != -1
    assert results_index < mask_index


def test_back_button_uses_compact_text_variant(panel: RegionDetailPanel) -> None:
    """Back navigation is a compact text link, not the dominant control."""
    assert panel._header_view._back_button.property("variant") == "text"
    assert "Alt+Left" in panel._header_view._back_button.toolTip()


class _NullHistoryRecorder:
    """History recorder double exposing only no-op recording scopes."""

    def suppress_recording(self) -> AbstractContextManager[None]:
        """Return a no-op suppression scope."""
        return contextlib.nullcontext()

    def atomic_recording(self) -> AbstractContextManager[None]:
        """Return a no-op atomic scope."""
        return contextlib.nullcontext()


class _RecordingModelAdditionUseCase(NoOpModelAdditionUseCase):
    """Model-addition use case double recording target line identifiers."""

    def __init__(self) -> None:
        self.line_ids: list[str] = []

    def add_components(
        self, project: SpectroscopyProject, line: AbsorptionLine, request: "ModelAdditionRequest"
    ) -> "ModelAdditionResult":
        """Record the target line and return an empty result."""
        self.line_ids.append(line.line_id)
        return super().add_components(project, line, request)


def test_empty_state_cta_targets_the_only_region_line(qtbot: "QtBot") -> None:
    """Clicking the empty-state CTA resolves the region's single line directly."""
    editor = OptimizeEditor()
    qtbot.addWidget(editor)
    usecase = _RecordingModelAdditionUseCase()
    parameter_mutation_usecase, tie_set_edit_usecase = build_region_detail_usecases()
    panel = RegionDetailPanel(
        optimize_editor=editor,
        analysis_focus=AnalysisFocusRecorder(),
        mode_state=_ModeState(),
        model_addition_usecase=usecase,
        parameter_mutation_usecase=parameter_mutation_usecase,
        tie_set_edit_usecase=tie_set_edit_usecase,
        velocity_plot_active_provider=lambda: False,
        project_file_path_provider=lambda: None,
    )
    qtbot.addWidget(panel)
    panel.set_history_recorder(cast("OptimizeHistoryRecorder", _NullHistoryRecorder()))
    project = _project_with_spectrum()
    _add_region_with_line(project, with_component=False)
    panel.set_project(project)
    panel.refresh()

    assert panel._view_state.selected_line_id is None
    panel._actions_view.add_model_button().click()

    assert usecase.line_ids == ["line-1"]


def test_add_target_label_disambiguates_same_transition_by_redshift() -> None:
    """Blended lines sharing a transition name get distinct redshift-tagged labels."""
    line_a = _make_line("line-a", region_id="region-1")
    line_b = _make_line("line-b", region_id="region-1")
    line_b.center_z = 1.293
    line_a.center_z = 1.292

    label_a = RegionDetailPanel._add_target_label(line_a)
    label_b = RegionDetailPanel._add_target_label(line_b)

    assert label_a == "H I 1215.7 (z=1.292)"
    assert label_b == "H I 1215.7 (z=1.293)"
    assert label_a != label_b
