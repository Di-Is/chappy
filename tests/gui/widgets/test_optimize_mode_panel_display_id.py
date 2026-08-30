"""Tests for RegionDetailPanel display ID feature."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QTreeWidget

from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.modes.analysis.region_detail.editor import OptimizeEditor
from chappy.gui.modes.analysis.region_detail.panel import RegionDetailPanel
from chappy.gui.modes.analysis.region_detail.tree.tree_columns import COL_ID, COL_Z
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
    return OptimizeEditor()


@pytest.fixture
def panel(optimize_editor: OptimizeEditor) -> RegionDetailPanel:
    """Create RegionDetailPanel instance."""
    parameter_mutation_usecase, tie_set_edit_usecase = build_region_detail_usecases()
    return RegionDetailPanel(
        optimize_editor=optimize_editor,
        analysis_focus=AnalysisFocusRecorder(),
        mode_state=_ModeState(),
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


class TestDisplayIdInTree:
    """Tests for display ID rendering in tree widget."""

    def test_line_row_displays_1_based_index(self, panel: RegionDetailPanel) -> None:
        """Parent row should display 1-based index in ID column."""
        # Setup: Create project with one region containing one line
        project = SpectroscopyProject()
        line = _make_line("line_1", center_z=1.5, region_id="region_1")
        region = _make_region("region_1", ["line_1"])

        project.absorption_lines[line.line_id] = line
        project.absorption_regions[region.region_id] = region

        tree = _render_project(panel, project)

        # Verify: First parent row has "1" in ID column
        assert tree.topLevelItemCount() == 1
        row = tree.topLevelItem(0)
        assert row is not None
        assert row.text(COL_ID) == "1"

    def test_model_row_id_column_is_empty(self, panel: RegionDetailPanel) -> None:
        """Child row (model) should have empty ID column."""
        # Setup: Create project with line that has a model
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

        # Verify: Child row (model) has empty ID column
        assert tree.topLevelItemCount() == 1
        row = tree.topLevelItem(0)
        assert row is not None
        assert row.childCount() == 1
        child = row.child(0)
        assert child is not None
        assert child.text(COL_ID) == ""

    def test_display_index_follows_center_z_order(self, panel: RegionDetailPanel) -> None:
        """Display index should follow center_z ascending order."""
        # Setup: Create project with multiple lines in different z order
        project = SpectroscopyProject()

        # Add lines in reverse z order
        line_high_z = _make_line("line_high", center_z=2.5, region_id="region_1")
        line_low_z = _make_line("line_low", center_z=1.0, region_id="region_1")
        line_mid_z = _make_line("line_mid", center_z=1.8, region_id="region_1")

        region = _make_region("region_1", ["line_high", "line_low", "line_mid"])

        project.absorption_lines["line_high"] = line_high_z
        project.absorption_lines["line_low"] = line_low_z
        project.absorption_lines["line_mid"] = line_mid_z
        project.absorption_regions[region.region_id] = region

        tree = _render_project(panel, project)

        # Verify: Lines are displayed in z-ascending order with correct IDs
        assert tree.topLevelItemCount() == 3

        # First should be line_low (z=1.0) with ID "1"
        row_0 = tree.topLevelItem(0)
        row_1 = tree.topLevelItem(1)
        row_2 = tree.topLevelItem(2)
        assert row_0 is not None
        assert row_1 is not None
        assert row_2 is not None
        assert row_0.text(COL_ID) == "1"
        assert row_0.text(COL_Z) == "1.00000"

        # Second should be line_mid (z=1.8) with ID "2"
        assert row_1.text(COL_ID) == "2"
        assert row_1.text(COL_Z) == "1.80000"

        # Third should be line_high (z=2.5) with ID "3"
        assert row_2.text(COL_ID) == "3"
        assert row_2.text(COL_Z) == "2.50000"

    def test_display_index_tie_break_by_rest_wavelength(self, panel: RegionDetailPanel) -> None:
        """When center_z is equal, lines are sorted by rest_wavelength."""
        project = SpectroscopyProject()

        # Add lines with same z but different wavelengths
        line_long_wl = _make_line(
            "line_long", center_z=1.5, rest_wavelength=2796.35, region_id="region_1"
        )
        line_short_wl = _make_line(
            "line_short", center_z=1.5, rest_wavelength=1215.67, region_id="region_1"
        )

        region = _make_region("region_1", ["line_long", "line_short"])

        project.absorption_lines["line_long"] = line_long_wl
        project.absorption_lines["line_short"] = line_short_wl
        project.absorption_regions[region.region_id] = region

        tree = _render_project(panel, project)

        # Verify: Shorter wavelength first
        assert tree.topLevelItemCount() == 2
        row_0 = tree.topLevelItem(0)
        row_1 = tree.topLevelItem(1)
        assert row_0 is not None
        assert row_1 is not None
        assert row_0.text(COL_ID) == "1"
        assert row_1.text(COL_ID) == "2"
