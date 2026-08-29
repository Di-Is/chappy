"""Tests for optimize export feedback signaling."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from PySide6.QtTest import QSignalSpy

from chappy.gui.modes.analysis.region_detail.editor import OptimizeEditor
from chappy.gui.modes.analysis.region_detail.panel import RegionDetailPanel
from chappy.gui.modes.analysis.region_detail.workflows.port_adapters import (
    OptimizeExportWorkflowPortAdapter,
)
from tests.gui.widgets.optimize_panel_helpers import (
    AnalysisFocusRecorder,
    NoOpModelAdditionUseCase,
    build_region_detail_usecases,
)


if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


@pytest.fixture
def panel(qtbot: "QtBot") -> RegionDetailPanel:
    """Instantiate RegionDetailPanel for export tests."""
    editor = OptimizeEditor()
    parameter_mutation_usecase, tie_set_edit_usecase = build_region_detail_usecases()
    return RegionDetailPanel(
        optimize_editor=editor,
        analysis_focus=AnalysisFocusRecorder(),
        model_addition_usecase=NoOpModelAdditionUseCase(),
        parameter_mutation_usecase=parameter_mutation_usecase,
        tie_set_edit_usecase=tie_set_edit_usecase,
        velocity_plot_active_provider=lambda: False,
        project_file_path_provider=lambda: None,
    )


def test_emit_export_success_emits_feedback(panel: RegionDetailPanel) -> None:
    """Ensure export success triggers feedback without modals."""
    spy = QSignalSpy(panel.export_feedback)
    adapter = OptimizeExportWorkflowPortAdapter(
        project_provider=lambda: None,
        group_selection_controller=panel._group_selection_controller,  # noqa: SLF001
        settings_adapter=panel._settings_adapter,  # noqa: SLF001
        project_file_path_provider=lambda: None,
        emit_export_feedback=panel.export_feedback.emit,
        focused_region_id_provider=lambda: None,
    )
    adapter.emit_export_success("Exported CSV to /tmp/result.csv")

    assert spy.count() == 1
    message, timeout_ms, level = spy.at(0)
    assert "CSV" in message
    assert timeout_ms == 3500
    assert level == "success"
