"""Tests for RegionDetailPanel tree rebuild unification (Phase 4).

These tests verify that after removing partial update methods,
the tree rebuild still functions correctly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QTreeWidget

from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.modes.analysis.region_detail.editor import OptimizeEditor
from chappy.gui.modes.analysis.region_detail.line_analysis_half_width_controller import (
    LineAnalysisHalfWidthControllerResult,
    LineAnalysisHalfWidthControllerResultKind,
)
from chappy.gui.modes.analysis.region_detail.panel import RegionDetailPanel
from chappy.gui.modes.analysis.region_detail.tree.tree_columns import (
    COL_ANALYSIS_HALF_WIDTH,
    COL_ID,
)
from tests.gui.widgets.optimize_panel_helpers import (
    AnalysisFocusRecorder,
    NoOpModelAdditionUseCase,
    build_region_detail_usecases,
)


if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class _ModeState(QObject):
    """Mode state test double that enables group selection."""

    def __init__(self) -> None:
        super().__init__()


@pytest.fixture
def optimize_editor(qtbot: "QtBot") -> OptimizeEditor:
    """Create OptimizeEditor instance."""
    editor = OptimizeEditor()
    qtbot.addWidget(editor)
    return editor


@pytest.fixture
def panel(qtbot: "QtBot", optimize_editor: OptimizeEditor) -> RegionDetailPanel:
    """Create RegionDetailPanel instance."""
    parameter_mutation_usecase, tie_set_edit_usecase = build_region_detail_usecases()
    widget = RegionDetailPanel(
        optimize_editor=optimize_editor,
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


def _tree(panel: RegionDetailPanel) -> QTreeWidget:
    """Return the optimize parameter tree."""
    tree = panel.findChild(QTreeWidget, "analysisDetailParameterTree")
    assert tree is not None
    return tree


def _render_project(panel: RegionDetailPanel, project: SpectroscopyProject) -> QTreeWidget:
    """Render the first selectable project region through public panel workflow."""
    panel.set_project(project)
    panel.refresh()
    return _tree(panel)


def _make_line(
    line_id: str,
    *,
    center_z: float = 1.0,
    rest_wavelength: float = 1215.67,
    species: str = "H I",
    region_id: str | None = None,
) -> AbsorptionLine:
    """Create a minimal AbsorptionLine for testing."""
    return AbsorptionLine(
        line_id=line_id,
        species=species,
        rest_wavelength=rest_wavelength,
        center_z=center_z,
        window_kms=150.0,
        region_id=region_id,
        multiplet_label="",
        transition_name=f"{species} {rest_wavelength:.1f}",
        oscillator_strength=0.1,
        gamma_value=1e8,
    )


def _make_region(region_id: str, line_ids: list[str]) -> AbsorptionRegion:
    """Create a minimal AbsorptionRegion for testing."""
    return AbsorptionRegion(region_id=region_id, line_ids=line_ids)


class _LineAnalysisController:
    """Return one configured panel-level edit result."""

    def __init__(self, result: LineAnalysisHalfWidthControllerResult) -> None:
        self._result = result

    def edit(
        self, *, line_id: str, requested_half_width: float
    ) -> LineAnalysisHalfWidthControllerResult:
        _ = line_id
        _ = requested_half_width
        return self._result


@pytest.mark.parametrize(
    "result",
    [
        LineAnalysisHalfWidthControllerResult(
            kind=LineAnalysisHalfWidthControllerResultKind.NO_CHANGE,
            requested=150.0,
            applied=150.0,
            affected_line_ids=("line-1",),
            region_id="region-1",
            reason="already_equal",
        ),
        LineAnalysisHalfWidthControllerResult(
            kind=LineAnalysisHalfWidthControllerResultKind.REJECTED,
            requested=5000.0,
            reason="outside_supported_range",
        ),
    ],
)
def test_no_change_and_rejected_width_edits_do_not_request_spectrum_redraw(
    panel: RegionDetailPanel, result: LineAnalysisHalfWidthControllerResult
) -> None:
    """Only committed scientific edits should emit the spectrum refresh signal."""
    project = SpectroscopyProject()
    line = _make_line("line-1", region_id="region-1")
    region = _make_region("region-1", [line.line_id])
    project.absorption_lines[line.line_id] = line
    project.absorption_regions[region.region_id] = region
    tree = _render_project(panel, project)
    row = tree.topLevelItem(0)
    assert row is not None
    panel._line_analysis_half_width_controller = _LineAnalysisController(  # type: ignore[assignment]
        result
    )
    redraws: list[str] = []
    panel.line_analysis_half_width_changed.connect(redraws.append)

    panel._on_line_analysis_half_width_changed(row, COL_ANALYSIS_HALF_WIDTH)

    assert redraws == []


class TestTreeRebuildAfterModelAddition:
    """Tests verifying tree rebuild works correctly after model addition."""

    def test_tree_displays_model_after_rebuild(self, panel: RegionDetailPanel) -> None:
        """Tree should correctly display models after rebuild."""
        # Setup: Create project with one region and one line with a model
        project = SpectroscopyProject()
        line = _make_line("line_1", center_z=1.5, region_id="region_1")
        region = _make_region("region_1", ["line_1"])

        component = AbsorberComponent(
            name="H I",
            wavelength=1215.67,
            column_density=14.0,
            b_parameter=10.0,
            redshift=1.5,
            oscillator_strength=0.4164,
            gamma=6.265e8,
        )
        project.model.add_component(component)
        line.model_ids = [component.id]

        project.absorption_lines[line.line_id] = line
        project.absorption_regions[region.region_id] = region

        tree = _render_project(panel, project)

        # Verify: Tree has one parent with one child
        assert tree.topLevelItemCount() == 1
        row = tree.topLevelItem(0)
        assert row is not None
        assert row.childCount() == 1

    def test_display_ids_preserved_after_model_addition(self, panel: RegionDetailPanel) -> None:
        """Display IDs should remain consistent after adding models."""
        # Setup: Create project with multiple lines
        project = SpectroscopyProject()

        line_low_z = _make_line("line_low", center_z=1.0, region_id="region_1")
        line_high_z = _make_line("line_high", center_z=2.0, region_id="region_1")
        region = _make_region("region_1", ["line_low", "line_high"])

        # Add a model to high_z line
        component = AbsorberComponent(
            name="H I",
            wavelength=1215.67,
            column_density=14.0,
            b_parameter=10.0,
            redshift=2.0,
            oscillator_strength=0.4164,
            gamma=6.265e8,
        )
        project.model.add_component(component)
        line_high_z.model_ids = [component.id]

        project.absorption_lines["line_low"] = line_low_z
        project.absorption_lines["line_high"] = line_high_z
        project.absorption_regions[region.region_id] = region

        tree = _render_project(panel, project)

        # Verify: Display IDs follow z-order
        assert tree.topLevelItemCount() == 2

        # First line (low z) should have ID "1"
        row_0 = tree.topLevelItem(0)
        row_1 = tree.topLevelItem(1)
        assert row_0 is not None
        assert row_1 is not None
        assert row_0.text(COL_ID) == "1"

        # Second line (high z, has model) should have ID "2"
        assert row_1.text(COL_ID) == "2"
        assert row_1.childCount() == 1

    def test_rebuild_clears_previous_items(self, panel: RegionDetailPanel) -> None:
        """Rebuild should clear previous tree items before adding new ones."""
        # Setup: Create project with one line
        project = SpectroscopyProject()
        line = _make_line("line_1", center_z=1.5, region_id="region_1")
        region = _make_region("region_1", ["line_1"])

        project.absorption_lines[line.line_id] = line
        project.absorption_regions[region.region_id] = region

        tree = _render_project(panel, project)

        assert tree.topLevelItemCount() == 1

        # Second refresh should not duplicate items.
        panel.refresh()
        assert tree.topLevelItemCount() == 1

    def test_rebuild_with_multiple_models_per_line(self, panel: RegionDetailPanel) -> None:
        """Rebuild should correctly show multiple models for a single line."""
        # Setup: Create project with one line with multiple models
        project = SpectroscopyProject()
        line = _make_line("line_1", center_z=1.5, region_id="region_1")
        region = _make_region("region_1", ["line_1"])

        # Add two components
        component1 = AbsorberComponent(
            name="H I",
            wavelength=1215.67,
            column_density=14.0,
            b_parameter=10.0,
            redshift=1.5,
            oscillator_strength=0.4164,
            gamma=6.265e8,
        )
        component2 = AbsorberComponent(
            name="H I",
            wavelength=1215.67,
            column_density=13.5,
            b_parameter=8.0,
            redshift=1.5,
            oscillator_strength=0.4164,
            gamma=6.265e8,
        )
        project.model.add_component(component1)
        project.model.add_component(component2)
        line.model_ids = [component1.id, component2.id]

        project.absorption_lines[line.line_id] = line
        project.absorption_regions[region.region_id] = region

        tree = _render_project(panel, project)

        # Verify: One parent with two children
        assert tree.topLevelItemCount() == 1
        row = tree.topLevelItem(0)
        assert row is not None
        assert row.childCount() == 2


class TestCosmologyChangeRebuild:
    """Tests verifying the tree rebuild triggered by cosmology changes."""

    def test_notify_cosmology_changed_rebuilds_selected_region(
        self, panel: RegionDetailPanel
    ) -> None:
        """Cosmology notification should rebuild the currently selected region."""
        project = SpectroscopyProject()
        line = _make_line("line_1", center_z=1.5, region_id="region_1")
        region = _make_region("region_1", ["line_1"])
        project.absorption_lines[line.line_id] = line
        project.absorption_regions[region.region_id] = region
        _render_project(panel, project)

        rebuilt: list[str] = []

        class _RenderRecorder:
            def rebuild_region(
                self, _project: SpectroscopyProject | None, target: AbsorptionRegion
            ) -> None:
                rebuilt.append(target.region_id)

        panel._tree_view = _RenderRecorder()  # type: ignore[assignment]

        panel.notify_cosmology_changed()

        assert rebuilt == ["region_1"]

    def test_notify_cosmology_changed_without_selection_is_noop(
        self, panel: RegionDetailPanel
    ) -> None:
        """Cosmology notification without a selected region should do nothing."""
        rebuilt: list[str] = []

        class _RenderRecorder:
            def rebuild_region(
                self, _project: SpectroscopyProject | None, target: AbsorptionRegion
            ) -> None:
                rebuilt.append(target.region_id)

        panel._tree_view = _RenderRecorder()  # type: ignore[assignment]

        panel.notify_cosmology_changed()

        assert rebuilt == []
