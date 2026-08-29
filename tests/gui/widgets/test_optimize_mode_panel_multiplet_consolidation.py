"""Tests for RegionDetailPanel multiplet consolidation feature."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QTreeWidget

from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.components.tie_set import ParameterTieSet
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.modes.analysis.region_detail.editor import OptimizeEditor
from chappy.gui.modes.analysis.region_detail.panel import RegionDetailPanel
from chappy.gui.modes.analysis.region_detail.tree.tree_columns import COL_ID, COL_SPECIES, COL_Z
from tests.gui.widgets.optimize_panel_helpers import (
    AnalysisFocusRecorder,
    NoOpModelAdditionUseCase,
    build_region_detail_usecases,
)


if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class _ModeState(QObject):
    """Mode state test double that enables group selection."""

    group_removed = Signal(str)

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


def _make_line(
    line_id: str,
    *,
    center_z: float = 1.0,
    rest_wavelength: float = 1215.67,
    species: str = "H I",
    transition_name: str | None = None,
    region_id: str | None = None,
    multiplet_ids: list[str] | None = None,
    model_ids: list[str] | None = None,
    multiplet_label: str | None = None,
) -> AbsorptionLine:
    """Create a minimal AbsorptionLine for testing."""
    # Default transition_name to "species rest_wavelength" if not provided
    if transition_name is None:
        transition_name = f"{species} {rest_wavelength:.1f}"
    # Default multiplet_label to transition_name (for single lines)
    if multiplet_label is None:
        multiplet_label = transition_name
    return AbsorptionLine(
        line_id=line_id,
        species=species,
        transition_name=transition_name,
        rest_wavelength=rest_wavelength,
        center_z=center_z,
        window_kms=150.0,
        region_id=region_id,
        multiplet_ids=multiplet_ids if multiplet_ids is not None else [],
        model_ids=model_ids if model_ids is not None else [],
        multiplet_label=multiplet_label,
        oscillator_strength=0.1,
        gamma_value=1e8,
    )


def _make_region(region_id: str, line_ids: list[str]) -> AbsorptionRegion:
    """Create a minimal AbsorptionRegion for testing."""
    return AbsorptionRegion(region_id=region_id, line_ids=line_ids)


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


def _make_multiplet_components(
    line1: AbsorptionLine,
    line2: AbsorptionLine,
    *,
    redshift: float = 1.5,
    column_density: float = 14.0,
    b_parameter: float = 10.0,
) -> tuple[AbsorberComponent, AbsorberComponent, ParameterTieSet]:
    """Create two components linked via ParameterTieSet.

    Args:
        line1: First absorption line (will get primary component).
        line2: Second absorption line (will get secondary component).
        redshift: Shared redshift value.
        column_density: Shared column density value.
        b_parameter: Shared b parameter value.

    Returns:
        Tuple of (primary_component, secondary_component, tie_set).
    """
    # Create primary component for line1
    comp1 = AbsorberComponent(
        name=f"{line1.species}_{line1.rest_wavelength:.0f}",
        wavelength=line1.rest_wavelength,
        column_density=column_density,
        b_parameter=b_parameter,
        redshift=redshift,
    )

    # Create secondary component for line2
    comp2 = AbsorberComponent(
        name=f"{line2.species}_{line2.rest_wavelength:.0f}",
        wavelength=line2.rest_wavelength,
        column_density=column_density,
        b_parameter=b_parameter,
        redshift=redshift,
    )

    # Create ParameterTieSet and link components
    tie_set = ParameterTieSet(f"multiplet_{comp1.id}_{comp2.id}")
    tie_set.add_component(comp1)  # Primary (index 0)
    tie_set.add_component(comp2)  # Secondary (index 1)

    return comp1, comp2, tie_set


class TestMultipletConsolidation:
    """Tests for multiplet consolidation in RegionDetailPanel."""

    def test_doublet_displayed_as_single_row(self, panel: RegionDetailPanel) -> None:
        """Two lines with multiplet cross-references should display as one row."""
        project = SpectroscopyProject()

        # MgII doublet: 2796/2803
        line1 = _make_line(
            "mg2_2796",
            center_z=1.5,
            rest_wavelength=2796.35,
            species="Mg II",
            region_id="region_1",
            multiplet_ids=["mg2_2803"],
        )
        line2 = _make_line(
            "mg2_2803",
            center_z=1.5,
            rest_wavelength=2803.53,
            species="Mg II",
            region_id="region_1",
            multiplet_ids=["mg2_2796"],
        )

        region = _make_region("region_1", ["mg2_2796", "mg2_2803"])

        project.absorption_lines["mg2_2796"] = line1
        project.absorption_lines["mg2_2803"] = line2
        project.absorption_regions[region.region_id] = region

        tree = _render_project(panel, project)
        # Multiplet should be consolidated into 1 row
        assert tree.topLevelItemCount() == 1, (
            f"Expected 1 consolidated row, got {tree.topLevelItemCount()}"
        )

    def test_doublet_display_id_is_single_number(self, panel: RegionDetailPanel) -> None:
        """Multiplet row should have a single display ID."""
        project = SpectroscopyProject()

        line1 = _make_line(
            "mg2_2796",
            center_z=1.5,
            rest_wavelength=2796.35,
            species="Mg II",
            region_id="region_1",
            multiplet_ids=["mg2_2803"],
        )
        line2 = _make_line(
            "mg2_2803",
            center_z=1.5,
            rest_wavelength=2803.53,
            species="Mg II",
            region_id="region_1",
            multiplet_ids=["mg2_2796"],
        )

        region = _make_region("region_1", ["mg2_2796", "mg2_2803"])

        project.absorption_lines["mg2_2796"] = line1
        project.absorption_lines["mg2_2803"] = line2
        project.absorption_regions[region.region_id] = region

        tree = _render_project(panel, project)
        row = tree.topLevelItem(0)
        assert row is not None
        id_text = row.text(COL_ID)
        assert id_text == "1", f"Display ID should be '1', got '{id_text}'"

    def test_triplet_displayed_as_single_row(self, panel: RegionDetailPanel) -> None:
        """Three or more lines in a multiplet should display as one row."""
        project = SpectroscopyProject()

        # Simulated triplet
        line1 = _make_line(
            "line_a",
            center_z=1.5,
            rest_wavelength=1000.0,
            species="X I",
            region_id="region_1",
            multiplet_ids=["line_b", "line_c"],
        )
        line2 = _make_line(
            "line_b",
            center_z=1.5,
            rest_wavelength=1100.0,
            species="X I",
            region_id="region_1",
            multiplet_ids=["line_a", "line_c"],
        )
        line3 = _make_line(
            "line_c",
            center_z=1.5,
            rest_wavelength=1200.0,
            species="X I",
            region_id="region_1",
            multiplet_ids=["line_a", "line_b"],
        )

        region = _make_region("region_1", ["line_a", "line_b", "line_c"])

        project.absorption_lines["line_a"] = line1
        project.absorption_lines["line_b"] = line2
        project.absorption_lines["line_c"] = line3
        project.absorption_regions[region.region_id] = region

        tree = _render_project(panel, project)
        # Triplet should be consolidated into 1 row
        assert tree.topLevelItemCount() == 1, (
            f"Expected 1 consolidated row for triplet, got {tree.topLevelItemCount()}"
        )

    def test_mixed_multiplet_and_single_display_ids(self, panel: RegionDetailPanel) -> None:
        """Mixed multiplet and single lines should have consecutive display IDs."""
        project = SpectroscopyProject()

        # Single line (will be sorted first by z=1.0)
        single_line = _make_line(
            "single",
            center_z=1.0,
            rest_wavelength=1215.67,
            species="H I",
            region_id="region_1",
            multiplet_ids=[],
        )

        # Doublet (z=1.5)
        line1 = _make_line(
            "mg2_2796",
            center_z=1.5,
            rest_wavelength=2796.35,
            species="Mg II",
            region_id="region_1",
            multiplet_ids=["mg2_2803"],
        )
        line2 = _make_line(
            "mg2_2803",
            center_z=1.5,
            rest_wavelength=2803.53,
            species="Mg II",
            region_id="region_1",
            multiplet_ids=["mg2_2796"],
        )

        region = _make_region("region_1", ["single", "mg2_2796", "mg2_2803"])

        project.absorption_lines["single"] = single_line
        project.absorption_lines["mg2_2796"] = line1
        project.absorption_lines["mg2_2803"] = line2
        project.absorption_regions[region.region_id] = region

        tree = _render_project(panel, project)
        # Should have 2 rows: single + multiplet
        assert tree.topLevelItemCount() == 2, (
            f"Expected 2 rows (1 single + 1 multiplet), got {tree.topLevelItemCount()}"
        )

        # First row should be single line with ID "1"
        row_0 = tree.topLevelItem(0)
        assert row_0 is not None
        id_0 = row_0.text(COL_ID)
        assert id_0 == "1", f"First row ID should be '1', got '{id_0}'"

        # Second row should be multiplet with ID "2"
        row_1 = tree.topLevelItem(1)
        assert row_1 is not None
        id_1 = row_1.text(COL_ID)
        assert id_1 == "2", f"Second row ID should be '2', got '{id_1}'"

    def test_doublet_header_shows_combined_wavelengths(self, panel: RegionDetailPanel) -> None:
        """Multiplet row should show combined wavelengths in species column."""
        project = SpectroscopyProject()

        line1 = _make_line(
            "mg2_2796",
            center_z=1.5,
            rest_wavelength=2796.35,
            species="Mg II",
            region_id="region_1",
            multiplet_ids=["mg2_2803"],
            multiplet_label="Mg II 2796/2803",
        )
        line2 = _make_line(
            "mg2_2803",
            center_z=1.5,
            rest_wavelength=2803.53,
            species="Mg II",
            region_id="region_1",
            multiplet_ids=["mg2_2796"],
            multiplet_label="Mg II 2796/2803",
        )

        region = _make_region("region_1", ["mg2_2796", "mg2_2803"])

        project.absorption_lines["mg2_2796"] = line1
        project.absorption_lines["mg2_2803"] = line2
        project.absorption_regions[region.region_id] = region

        tree = _render_project(panel, project)
        row = tree.topLevelItem(0)
        assert row is not None
        species_text = row.text(COL_SPECIES)
        # Multiplet displays combined transition_names separated by "/"
        assert "Mg II" in species_text, f"Species column should contain species: {species_text}"
        assert "/" in species_text, f"Species column should contain '/': {species_text}"


class TestComponentConsolidation:
    """Tests for component row rendering under multiplet consolidation."""

    def test_multiplet_consolidation_shows_all_components(self, panel: RegionDetailPanel) -> None:
        """マルチプレット統合表示時、両方の成分行が遷移識別付きで表示される。

        Mg II 2796/2803 doublet with one ParameterTieSet (2 components).
        Both members should be displayed, one per line.
        """
        project = SpectroscopyProject()

        # Create doublet lines
        line1 = _make_line(
            "mg2_2796",
            center_z=1.5,
            rest_wavelength=2796.35,
            species="Mg II",
            region_id="region_1",
            multiplet_ids=["mg2_2803"],
        )
        line2 = _make_line(
            "mg2_2803",
            center_z=1.5,
            rest_wavelength=2803.35,
            species="Mg II",
            region_id="region_1",
            multiplet_ids=["mg2_2796"],
        )

        # Create components linked via ParameterTieSet
        comp1, comp2, _group = _make_multiplet_components(line1, line2, redshift=1.5)

        # Link components to lines
        line1.model_ids = [comp1.id]
        line2.model_ids = [comp2.id]

        region = _make_region("region_1", ["mg2_2796", "mg2_2803"])

        project.absorption_lines["mg2_2796"] = line1
        project.absorption_lines["mg2_2803"] = line2
        project.absorption_regions[region.region_id] = region
        project.model.add_component(comp1)
        project.model.add_component(comp2)

        tree = _render_project(panel, project)
        # Should have 1 consolidated row for the multiplet
        assert tree.topLevelItemCount() == 1, (
            f"Expected 1 consolidated row, got {tree.topLevelItemCount()}"
        )

        # Both members should be displayed, one row per line.
        parent_row = tree.topLevelItem(0)
        assert parent_row is not None
        child_count = parent_row.childCount()
        assert child_count == 2, f"Expected 2 children (both members), got {child_count}"
        assert parent_row.child(0).text(COL_SPECIES) == "2796 c1"
        assert parent_row.child(1).text(COL_SPECIES) == "2803 c1"

    def test_multiplet_consolidation_component_numbering(self, panel: RegionDetailPanel) -> None:
        """統合行配下で全成分行が線順→線内連番の順に並ぶ。

        Two ParameterTieSets with 2 components each (4 total).
        All four members should be displayed, numbered per line.
        """
        project = SpectroscopyProject()

        # Create doublet lines (Mg II)
        line1 = _make_line(
            "mg2_2796",
            center_z=1.5,
            rest_wavelength=2796.35,
            species="Mg II",
            region_id="region_1",
            multiplet_ids=["mg2_2803"],
        )
        line2 = _make_line(
            "mg2_2803",
            center_z=1.5,
            rest_wavelength=2803.35,
            species="Mg II",
            region_id="region_1",
            multiplet_ids=["mg2_2796"],
        )

        # Create first ParameterTieSet (absorber 1)
        comp1a, comp1b, _group1 = _make_multiplet_components(
            line1, line2, redshift=1.5, column_density=14.0
        )

        # Create second ParameterTieSet (absorber 2)
        comp2a, comp2b, _group2 = _make_multiplet_components(
            line1, line2, redshift=1.52, column_density=14.5
        )

        # Link components to lines (both absorbers)
        line1.model_ids = [comp1a.id, comp2a.id]
        line2.model_ids = [comp1b.id, comp2b.id]

        region = _make_region("region_1", ["mg2_2796", "mg2_2803"])

        project.absorption_lines["mg2_2796"] = line1
        project.absorption_lines["mg2_2803"] = line2
        project.absorption_regions[region.region_id] = region
        project.model.add_component(comp1a)
        project.model.add_component(comp1b)
        project.model.add_component(comp2a)
        project.model.add_component(comp2b)

        tree = _render_project(panel, project)
        # Should have 1 consolidated row for the multiplet
        assert tree.topLevelItemCount() == 1

        # All four members should be displayed (2 per line).
        parent_row = tree.topLevelItem(0)
        assert parent_row is not None
        child_count = parent_row.childCount()
        assert child_count == 4, f"Expected 4 children (2 per line), got {child_count}"

        species_texts = [parent_row.child(i).text(COL_SPECIES) for i in range(4)]
        assert species_texts == ["2796 c1", "2796 c2", "2803 c1", "2803 c2"]

    def test_single_line_shows_all_components(self, panel: RegionDetailPanel) -> None:
        """単一ライン表示時は全コンポーネントが表示される（既存動作維持）。

        Single line with ParameterTieSet (2 components).
        Both primary and secondary components should be displayed.
        """
        project = SpectroscopyProject()

        # Create single line (only one of the doublet in this region)
        line1 = _make_line(
            "mg2_2796",
            center_z=1.5,
            rest_wavelength=2796.35,
            species="Mg II",
            region_id="region_1",
            multiplet_ids=["mg2_2803"],  # References another line not in region
        )
        # line2 (mg2_2803) is NOT in this region - only line1 is present
        # Create a dummy line2 for component creation
        line2_dummy = _make_line(
            "mg2_2803",
            center_z=1.5,
            rest_wavelength=2803.53,
            species="Mg II",
            region_id="other_region",
            multiplet_ids=["mg2_2796"],
        )

        # Create components linked via ParameterTieSet
        comp1, comp2, _group = _make_multiplet_components(line1, line2_dummy, redshift=1.5)

        # Both components are on line1 (single line scenario)
        line1.model_ids = [comp1.id, comp2.id]

        # Region only contains line1
        region = _make_region("region_1", ["mg2_2796"])

        project.absorption_lines["mg2_2796"] = line1
        project.absorption_regions[region.region_id] = region
        project.model.add_component(comp1)
        project.model.add_component(comp2)

        tree = _render_project(panel, project)
        # Should have 1 row for the single line
        assert tree.topLevelItemCount() == 1

        # Should have 2 children (both components displayed for single line)
        parent_row = tree.topLevelItem(0)
        assert parent_row is not None
        child_count = parent_row.childCount()
        assert child_count == 2, (
            f"Expected 2 children (all components for single line), got {child_count}. "
            "Single line should show all components including secondary."
        )
        assert parent_row.child(0).text(COL_SPECIES) == "c1"
        assert parent_row.child(1).text(COL_SPECIES) == "c2"

    def test_non_multiplet_component_mixed(self, panel: RegionDetailPanel) -> None:
        """tie_set未設定のコンポーネントが混在するケース。

        Mix of components with and without ParameterTieSet.
        All components (tied and standalone) should be displayed.
        """
        project = SpectroscopyProject()

        # Create doublet lines
        line1 = _make_line(
            "mg2_2796",
            center_z=1.5,
            rest_wavelength=2796.35,
            species="Mg II",
            region_id="region_1",
            multiplet_ids=["mg2_2803"],
        )
        line2 = _make_line(
            "mg2_2803",
            center_z=1.5,
            rest_wavelength=2803.35,
            species="Mg II",
            region_id="region_1",
            multiplet_ids=["mg2_2796"],
        )

        # Create ParameterTieSet components
        comp1, comp2, _group = _make_multiplet_components(line1, line2, redshift=1.5)

        # Create additional component WITHOUT ParameterTieSet
        comp_standalone = AbsorberComponent(
            name="Standalone",
            wavelength=line1.rest_wavelength,
            column_density=13.5,
            b_parameter=8.0,
            redshift=1.51,
        )
        # comp_standalone.tie_set is None by default

        # Link all components to lines
        line1.model_ids = [comp1.id, comp_standalone.id]
        line2.model_ids = [comp2.id]

        region = _make_region("region_1", ["mg2_2796", "mg2_2803"])

        project.absorption_lines["mg2_2796"] = line1
        project.absorption_lines["mg2_2803"] = line2
        project.absorption_regions[region.region_id] = region
        project.model.add_component(comp1)
        project.model.add_component(comp2)
        project.model.add_component(comp_standalone)

        tree = _render_project(panel, project)
        # Should have 1 consolidated row
        assert tree.topLevelItemCount() == 1

        # Should have 3 children:
        # - comp1 (line1, tied) -> "2796 c1"
        # - comp_standalone (line1, standalone) -> "2796 c2"
        # - comp2 (line2, tied) -> "2803 c1"
        parent_row = tree.topLevelItem(0)
        assert parent_row is not None
        child_count = parent_row.childCount()
        assert child_count == 3, (
            f"Expected 3 children (2 on line1 + 1 on line2), got {child_count}."
        )
        species_texts = [parent_row.child(i).text(COL_SPECIES) for i in range(3)]
        assert species_texts == ["2796 c1", "2796 c2", "2803 c1"]

    def test_partial_mask_tie_set_components_are_shown(self, panel: RegionDetailPanel) -> None:
        """部分マスク tie set の成分行が非表示にならない（回帰テスト）。

        A user tie set sharing only redshift (partial mask) must not hide the
        component rows of its members under the consolidated multiplet row.
        """
        project = SpectroscopyProject()

        line1 = _make_line(
            "mg2_2796",
            center_z=1.5,
            rest_wavelength=2796.35,
            species="Mg II",
            region_id="region_1",
            multiplet_ids=["mg2_2803"],
        )
        line2 = _make_line(
            "mg2_2803",
            center_z=1.5,
            rest_wavelength=2803.35,
            species="Mg II",
            region_id="region_1",
            multiplet_ids=["mg2_2796"],
        )

        comp1 = AbsorberComponent(
            name="Mg II_2796",
            wavelength=line1.rest_wavelength,
            column_density=14.0,
            b_parameter=10.0,
            redshift=1.5,
        )
        comp2 = AbsorberComponent(
            name="Mg II_2803",
            wavelength=line2.rest_wavelength,
            column_density=13.0,
            b_parameter=12.0,
            redshift=1.5,
        )
        tie_set = ParameterTieSet("user-1", mask=frozenset({"redshift"}), origin="user")
        tie_set.add_component(comp1)
        tie_set.add_component(comp2)

        line1.model_ids = [comp1.id]
        line2.model_ids = [comp2.id]

        region = _make_region("region_1", ["mg2_2796", "mg2_2803"])

        project.absorption_lines["mg2_2796"] = line1
        project.absorption_lines["mg2_2803"] = line2
        project.absorption_regions[region.region_id] = region
        project.model.add_component(comp1)
        project.model.add_component(comp2)

        tree = _render_project(panel, project)
        assert tree.topLevelItemCount() == 1
        parent_row = tree.topLevelItem(0)
        assert parent_row is not None
        assert parent_row.childCount() == 2, (
            "Partial-mask tie set members must remain visible as component rows."
        )

    def test_untying_shared_components_preserves_row_structure(
        self, panel: RegionDetailPanel
    ) -> None:
        """共有解除しても子行の構造は変わらず、tie ラベルだけが消える。

        UI 仕様 §1 の要件: row structure must not reshuffle when a tie set is
        created or dissolved; only the cell label/decoration changes.
        """
        project = SpectroscopyProject()

        line1 = _make_line(
            "mg2_2796",
            center_z=1.5,
            rest_wavelength=2796.35,
            species="Mg II",
            region_id="region_1",
            multiplet_ids=["mg2_2803"],
        )
        line2 = _make_line(
            "mg2_2803",
            center_z=1.5,
            rest_wavelength=2803.35,
            species="Mg II",
            region_id="region_1",
            multiplet_ids=["mg2_2796"],
        )

        comp1, comp2, tie_set = _make_multiplet_components(line1, line2, redshift=1.5)

        line1.model_ids = [comp1.id]
        line2.model_ids = [comp2.id]

        region = _make_region("region_1", ["mg2_2796", "mg2_2803"])

        project.absorption_lines["mg2_2796"] = line1
        project.absorption_lines["mg2_2803"] = line2
        project.absorption_regions[region.region_id] = region
        project.model.add_component(comp1)
        project.model.add_component(comp2)
        project.model.add_tie_set(tie_set)

        tree = _render_project(panel, project)
        parent_row = tree.topLevelItem(0)
        assert parent_row is not None
        assert parent_row.childCount() == 2
        z_texts_before = [parent_row.child(i).text(COL_Z) for i in range(2)]
        assert all(text.startswith("[") for text in z_texts_before), (
            f"Expected tie labels on both z cells, got {z_texts_before}"
        )

        tie_set.remove_component(comp2)
        tie_set.remove_component(comp1)
        project.model.remove_tie_set(tie_set)
        panel.refresh()

        parent_row = tree.topLevelItem(0)
        assert parent_row is not None
        assert parent_row.childCount() == 2, (
            "Row structure must stay the same after untying a shared tie set."
        )
        z_texts_after = [parent_row.child(i).text(COL_Z) for i in range(2)]
        assert not any(text.startswith("[") for text in z_texts_after), (
            f"Expected tie labels removed after untying, got {z_texts_after}"
        )
