"""Tests for bulk parameter fixing in RegionDetailPanel."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from PySide6.QtWidgets import QAbstractItemView, QTreeWidget

from chappy.gui.modes.analysis.region_detail.editor import OptimizeEditor
from chappy.gui.modes.analysis.region_detail.panel import RegionDetailPanel
from tests.gui.widgets.optimize_panel_helpers import (
    AnalysisFocusRecorder,
    NoOpModelAdditionUseCase,
    build_region_detail_usecases,
)


if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


@pytest.fixture
def optimize_editor(qtbot: "QtBot") -> OptimizeEditor:
    """Create OptimizeEditor instance."""
    return OptimizeEditor()


@pytest.fixture
def panel(optimize_editor: OptimizeEditor) -> RegionDetailPanel:
    """Create RegionDetailPanel instance."""
    parameter_mutation_usecase, tie_set_edit_usecase = build_region_detail_usecases()
    return RegionDetailPanel(
        optimize_editor=optimize_editor,
        analysis_focus=AnalysisFocusRecorder(),
        model_addition_usecase=NoOpModelAdditionUseCase(),
        parameter_mutation_usecase=parameter_mutation_usecase,
        tie_set_edit_usecase=tie_set_edit_usecase,
        velocity_plot_active_provider=lambda: False,
        project_file_path_provider=lambda: None,
    )


def _tree(panel: RegionDetailPanel) -> QTreeWidget:
    """Return the optimize parameter tree."""
    tree = panel.findChild(QTreeWidget, "analysisDetailParameterTree")
    assert tree is not None
    return tree


class TestBulkFixContext:
    """Tests covering multi-row selection and bulk fixed-state toggling."""

    def test_tree_allows_multi_row_selection(self, panel: RegionDetailPanel) -> None:
        """Tree should support extended selection for bulk operations."""
        tree = _tree(panel)
        assert tree.selectionMode() == QAbstractItemView.SelectionMode.ExtendedSelection
        assert tree.selectionBehavior() == QAbstractItemView.SelectionBehavior.SelectRows
