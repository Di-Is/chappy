"""Regression coverage: fit/export/mask work-target reads use canonical focus.

Unit 8(b) requires that fit, export, and mask mutation targets read the
canonical Analysis focus rather than the region selector's display
projection. `current_fit_region_id`, `current_export_region_id`, and
`current_mask_group_id` used to delegate to
`OptimizeGroupSelectionController.current_group_id()` (a pure selector read),
which desynchronized from canonical focus whenever the selector was
re-projected without a matching write-back (e.g. the language-change bug in
`RegionDetailPanel._on_language_changed`). These tests force that divergence
directly and prove the adapters still resolve the canonical region.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from PySide6.QtCore import QObject, Signal

from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.modes.analysis.region_detail.editor import OptimizeEditor
from chappy.gui.modes.analysis.region_detail.mask.port_adapters import (
    OptimizeMaskWorkflowPortAdapter,
)
from chappy.gui.modes.analysis.region_detail.panel import RegionDetailPanel
from chappy.gui.modes.analysis.region_detail.workflows.port_adapters import (
    OptimizeExportWorkflowPortAdapter,
    OptimizeFitWorkflowPortAdapter,
)
from tests.gui.widgets.optimize_panel_helpers import (
    AnalysisFocusRecorder,
    NoOpModelAdditionUseCase,
    build_region_detail_usecases,
)

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class _ModeState(QObject):
    """Minimal mode-state double exposing the signal the panel wires on construction."""

    group_removed = Signal(str)


def _region(region_id: str, line_id: str) -> tuple[AbsorptionRegion, AbsorptionLine]:
    line = AbsorptionLine(
        line_id=line_id,
        species="H I",
        rest_wavelength=1215.67,
        center_z=1.0,
        window_kms=150.0,
        region_id=region_id,
        multiplet_label="Ly alpha",
        transition_name="Ly alpha",
        oscillator_strength=0.1,
        gamma_value=1e8,
    )
    region = AbsorptionRegion(
        region_id=region_id, line_ids=[line_id], analysis_range=(3500.0, 3600.0)
    )
    return region, line


def _two_region_project() -> SpectroscopyProject:
    project = SpectroscopyProject()
    for region_id, line_id in (("region-1", "line-1"), ("region-2", "line-2")):
        region, line = _region(region_id, line_id)
        project.absorption_lines[line_id] = line
        project.absorption_regions[region_id] = region
    return project


@pytest.fixture
def analysis_focus() -> AnalysisFocusRecorder:
    """Create a fresh canonical Analysis focus recorder."""
    return AnalysisFocusRecorder()


@pytest.fixture
def panel(qtbot: QtBot, analysis_focus: AnalysisFocusRecorder) -> RegionDetailPanel:
    """Create a Region Detail panel wired to a real, inspectable focus recorder."""
    editor = OptimizeEditor()
    parameter_mutation_usecase, tie_set_edit_usecase = build_region_detail_usecases()
    widget = RegionDetailPanel(
        optimize_editor=editor,
        analysis_focus=analysis_focus,
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


def _diverge_selector_from_canonical(
    panel: RegionDetailPanel, project: SpectroscopyProject
) -> None:
    """Move the selector's display to a region other than canonical focus.

    `select_group_id` only re-projects the selector; it never writes canonical
    focus back (Unit 8(a)), so this reproduces the desync a rebuild-without-
    reprojection bug (like the language-change case) would leave behind.
    """
    panel._group_selection_controller.select_group_id(project, "region-2")  # noqa: SLF001


def test_fit_and_export_targets_read_canonical_focus_when_selector_diverges(
    panel: RegionDetailPanel, analysis_focus: AnalysisFocusRecorder
) -> None:
    """Fit/export must target canonical focus even when the selector shows another region."""
    project = _two_region_project()
    panel.set_project(project)
    panel.reconcile_focus_with_selector()
    assert analysis_focus.focused_region_id() == "region-1"

    _diverge_selector_from_canonical(panel, project)
    assert panel._group_selection_controller.current_group_id() == "region-2"  # noqa: SLF001

    fit_port = OptimizeFitWorkflowPortAdapter(
        project_provider=lambda: project,
        group_selection_controller=panel._group_selection_controller,  # noqa: SLF001
        view_state=panel._view_state,  # noqa: SLF001
        tree_view=panel._tree_view,  # noqa: SLF001
        should_enable_fit=lambda: True,
        update_button_state=lambda: None,
        refresh_fit_model_rows_display=lambda: None,
        focused_region_id_provider=analysis_focus.focused_region_id,
    )
    export_port = OptimizeExportWorkflowPortAdapter(
        project_provider=lambda: project,
        group_selection_controller=panel._group_selection_controller,  # noqa: SLF001
        settings_adapter=panel._settings_adapter,  # noqa: SLF001
        project_file_path_provider=lambda: None,
        emit_export_feedback=lambda message, timeout_ms, level: None,
        focused_region_id_provider=analysis_focus.focused_region_id,
    )

    assert fit_port.current_fit_region_id() == "region-1"
    assert export_port.current_export_region_id() == "region-1"


def test_mask_target_reads_canonical_focus_when_selector_diverges(
    panel: RegionDetailPanel, analysis_focus: AnalysisFocusRecorder
) -> None:
    """A new mask must attach to canonical focus even when the selector shows another region."""
    project = _two_region_project()
    panel.set_project(project)
    panel.reconcile_focus_with_selector()
    assert analysis_focus.focused_region_id() == "region-1"

    _diverge_selector_from_canonical(panel, project)
    assert panel._group_selection_controller.current_group_id() == "region-2"  # noqa: SLF001

    mask_port = OptimizeMaskWorkflowPortAdapter(
        group_selection_controller_provider=lambda: panel._group_selection_controller,  # noqa: SLF001,E501
        mask_panel_adapter=panel._mask_panel_adapter,  # noqa: SLF001
        mask_panel=panel._mask_panel,  # noqa: SLF001
        tree_view=panel._tree_view,  # noqa: SLF001
        confirm_dialog_adapter=panel._confirm_dialog_adapter,  # noqa: SLF001
        project_provider=lambda: project,
        velocity_plot_active_provider=lambda: False,
        mask_cancel_shortcut=None,
        emit_mask_selection_request=lambda request: None,
        emit_mask_focus_changed=lambda change: None,
        emit_mask_cancel_requested=lambda: None,
        focused_region_id_provider=analysis_focus.focused_region_id,
    )

    assert mask_port.current_mask_group_id() == "region-1"
