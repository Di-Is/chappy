"""Tests for optimize tree row renderer."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTreeWidgetItem

from chappy.core.absorption.models import AbsorptionLine
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.cosmology import (
    PLANCK_2018,
    CosmologyParameters,
    comoving_distance_mpc,
    lookback_time_gyr,
)
from chappy.gui.modes.analysis.region_detail.tree.tree_columns import (
    ROLE_EDIT_KIND,
    ROLE_RAW_ERROR,
    ROLE_RAW_VALUE,
    TreeCellEditKind,
)
from chappy.gui.modes.analysis.region_detail.tree.tree_row_renderer import (
    OptimizeTreeParameterColumn,
    OptimizeTreeRowColumns,
    OptimizeTreeRowRenderer,
)
from chappy.gui.modes.analysis.region_detail.tree.tree_widget import OptimizeTreeWidget

COL_ANALYSIS_HALF_WIDTH = 6
COL_WAVELENGTH = 7
COL_LOOKBACK = 8
COL_COMOVING = 9


@pytest.fixture(name="qapp")
def fixture_qapp() -> QApplication:
    """Provide a QApplication instance for Qt items."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _Port:
    """Renderer-port test double."""

    def __init__(self) -> None:
        self.styled_items: list[QTreeWidgetItem] = []
        self.ensure_count = 0
        self.tie_labels: dict[str, str] = {}
        self.tie_tooltips: dict[str, str] = {}
        self.stale_components: set[str] = set()
        self.cosmology = PLANCK_2018

    def tree_display_name_for_line(self, line: AbsorptionLine) -> str:
        """Return a deterministic display label."""
        return f"display:{line.transition_name}"

    def ensure_tree_covering_factor_parameter(self, component: AbsorberComponent) -> None:
        """Record covering factor initialization."""
        self.ensure_count += 1

    def apply_tree_parameter_styles(self, item: QTreeWidgetItem) -> None:
        """Record style applications."""
        self.styled_items.append(item)

    def tie_label_for(self, component: AbsorberComponent, parameter_name: str) -> str | None:
        """Return a configured tie label for the given parameter, if any."""
        return self.tie_labels.get(parameter_name)

    def tie_tooltip_for(self, component: AbsorberComponent, parameter_name: str) -> str | None:
        """Return a configured tie tooltip for the given parameter, if any."""
        return self.tie_tooltips.get(parameter_name)

    def is_tree_component_stale(self, component: AbsorberComponent) -> bool:
        """Return whether the component id was marked stale for this test."""
        return component.id in self.stale_components

    def tree_cosmology_parameters(self) -> CosmologyParameters:
        """Return the configured cosmology parameters for this test."""
        return self.cosmology


def _columns() -> OptimizeTreeRowColumns:
    """Return the production column layout used by row renderer tests."""
    return OptimizeTreeRowColumns(
        column_count=10,
        id_column=0,
        species_column=1,
        redshift_column=2,
        wavelength_column=COL_WAVELENGTH,
        lookback_column=COL_LOOKBACK,
        comoving_column=COL_COMOVING,
        analysis_half_width_column=COL_ANALYSIS_HALF_WIDTH,
        parameter_columns=(
            OptimizeTreeParameterColumn("redshift", 2, "{:.5f}", 0.0),
            OptimizeTreeParameterColumn("column_density", 3, "{:.2f}", 0.0),
            OptimizeTreeParameterColumn("b_parameter", 4, "{:.1f}", 0.0),
            OptimizeTreeParameterColumn("covering_factor", 5, "{:.3f}", 1.0),
        ),
    )


def _line(
    line_id: str, *, model_ids: list[str] | None = None, rest_wavelength: float = 1215.67
) -> AbsorptionLine:
    """Return a minimal absorption line."""
    return AbsorptionLine(
        line_id=line_id,
        species="H I",
        rest_wavelength=rest_wavelength,
        center_z=2.0,
        window_kms=150.0,
        region_id="region-1",
        multiplet_label="",
        transition_name="Ly alpha",
        oscillator_strength=0.1,
        gamma_value=1e8,
        model_ids=model_ids or [],
    )


def _component(component_id: str = "component-1") -> AbsorberComponent:
    """Return an absorber component with deterministic parameters."""
    component = AbsorberComponent(
        component_id=component_id,
        wavelength=1215.67,
        redshift=2.0,
        column_density=13.5,
        b_parameter=18.0,
    )
    component.parameters["redshift"].error = 0.000012
    component.parameters["column_density"].error = 0.15
    return component


def test_populate_line_row_sets_line_values(qapp: QApplication) -> None:
    """Renderer should populate a non-editable line row."""
    assert qapp is not None
    port = _Port()
    renderer = OptimizeTreeRowRenderer(columns=_columns(), port=port)
    item = QTreeWidgetItem()
    line = _line("line-1")

    renderer.populate_line_row(item, line, 3)

    assert item.text(0) == "3"
    assert item.text(1) == "display:Ly alpha"
    assert item.text(2) == "2.00000"
    assert item.text(COL_WAVELENGTH) == "3647.01"
    assert item.text(COL_ANALYSIS_HALF_WIDTH) == "±150"
    assert (
        item.data(COL_ANALYSIS_HALF_WIDTH, ROLE_EDIT_KIND)
        == TreeCellEditKind.LINE_ANALYSIS_HALF_WIDTH
    )
    assert item.text(3) == "—"
    assert item.data(3, ROLE_EDIT_KIND) == TreeCellEditKind.NONE
    assert item.data(0, Qt.ItemDataRole.UserRole) is line
    assert item.flags() & Qt.ItemFlag.ItemIsEditable


def test_populate_model_row_sets_parameter_values(qapp: QApplication) -> None:
    """Renderer should populate component rows with integrated value ± error cells."""
    assert qapp is not None
    port = _Port()
    renderer = OptimizeTreeRowRenderer(columns=_columns(), port=port)
    item = QTreeWidgetItem()
    component = _component()

    renderer.populate_model_row(item, component, 2)

    assert item.text(1) == "c2"
    assert item.text(2) == "2.000000 ± 0.000012"
    assert item.text(3) == "13.50 ± 0.15"
    assert item.text(4) == "18.0"
    assert item.text(COL_WAVELENGTH) == "3647.01"
    assert item.text(COL_ANALYSIS_HALF_WIDTH) == ""
    assert item.data(2, Qt.ItemDataRole.UserRole) == "redshift"
    assert item.data(0, Qt.ItemDataRole.UserRole) is component
    assert item.data(2, ROLE_RAW_VALUE) == 2.0
    assert item.data(2, ROLE_RAW_ERROR) == 0.000012
    assert item.data(4, ROLE_RAW_ERROR) is None
    assert item in port.styled_items
    assert port.ensure_count == 1


def test_zero_parameter_error_is_not_coerced_to_fallback_value(qapp: QApplication) -> None:
    """A zero error should render as unavailable, not as a fallback uncertainty."""
    assert qapp is not None
    port = _Port()
    renderer = OptimizeTreeRowRenderer(columns=_columns(), port=port)
    item = QTreeWidgetItem()
    component = _component()
    component.parameters["redshift"].error = 0.0

    renderer.populate_model_row(item, component, 1)

    assert item.text(2) == "2.00000"
    assert item.data(2, ROLE_RAW_ERROR) is None


def test_populate_model_row_hides_error_when_stale(qapp: QApplication) -> None:
    """A stale component should render the fallback value without ± error."""
    assert qapp is not None
    port = _Port()
    renderer = OptimizeTreeRowRenderer(columns=_columns(), port=port)
    item = QTreeWidgetItem()
    component = _component()
    port.stale_components.add(component.id)

    renderer.populate_model_row(item, component, 1)

    assert item.text(2) == "2.00000"
    assert item.text(3) == "13.50"
    assert item.data(2, ROLE_RAW_ERROR) is None
    assert "Uncertainty" in item.toolTip(2)


def test_populate_multiplet_row_deduplicates_components(qapp: QApplication) -> None:
    """Renderer should deduplicate model IDs across grouped multiplet lines."""
    assert qapp is not None
    port = _Port()
    renderer = OptimizeTreeRowRenderer(columns=_columns(), port=port)
    component = _component()
    first = _line("line-1", model_ids=[component.id])
    second = _line("line-2", model_ids=[component.id])
    first.multiplet_label = "H I multiplet"
    second.multiplet_label = "H I multiplet"
    item = QTreeWidgetItem()

    renderer.populate_multiplet_row(item, (first, second), 1, {component.id: component})

    assert item.text(1) == "H I multiplet"
    assert item.childCount() == 1
    assert item.child(0).data(0, Qt.ItemDataRole.UserRole) is component
    assert item.child(0).text(1) == "1216 c1"


def test_populate_multiplet_row_renders_mixed_analysis_half_width(qapp: QApplication) -> None:
    """A multiplet with different scientific widths should expose an editable Mixed cell."""
    assert qapp is not None
    renderer = OptimizeTreeRowRenderer(columns=_columns(), port=_Port())
    first = _line("line-1")
    second = _line("line-2")
    first.window_kms = 100.0
    second.window_kms = 150.0
    first.multiplet_label = "H I multiplet"
    second.multiplet_label = "H I multiplet"
    item = QTreeWidgetItem()

    renderer.populate_multiplet_row(item, (first, second), 1, {})

    assert item.text(COL_ANALYSIS_HALF_WIDTH) == "Mixed"
    assert item.data(COL_ANALYSIS_HALF_WIDTH, ROLE_RAW_VALUE) is None
    assert (
        item.data(COL_ANALYSIS_HALF_WIDTH, ROLE_EDIT_KIND)
        == TreeCellEditKind.LINE_ANALYSIS_HALF_WIDTH
    )


def test_tree_rejects_line_parameter_and_component_analysis_width_edits(
    qapp: QApplication,
) -> None:
    """Row type and column type must both match before an editor can open."""
    assert qapp is not None
    renderer = OptimizeTreeRowRenderer(columns=_columns(), port=_Port())
    tree = OptimizeTreeWidget()
    tree.setColumnCount(10)
    line_item = QTreeWidgetItem(tree)
    component_item = QTreeWidgetItem(tree)
    renderer.populate_line_row(line_item, _line("line-1"), 1)
    renderer.populate_model_row(component_item, _component(), 1)

    line_parameter_index = tree.indexFromItem(line_item, 3)
    component_analysis_index = tree.indexFromItem(component_item, COL_ANALYSIS_HALF_WIDTH)

    assert tree.edit(line_parameter_index) is False
    assert tree.edit(component_analysis_index) is False


def test_populate_multiplet_row_renders_all_line_components(qapp: QApplication) -> None:
    """Renderer should render every component of every line under a multiplet row."""
    assert qapp is not None
    port = _Port()
    renderer = OptimizeTreeRowRenderer(columns=_columns(), port=port)
    first_a = _component("first-a")
    first_b = _component("first-b")
    second_a = _component("second-a")
    second_b = _component("second-b")
    first = _line("line-1", model_ids=[first_a.id, first_b.id], rest_wavelength=2796.35)
    second = _line("line-2", model_ids=[second_a.id, second_b.id], rest_wavelength=2803.35)
    first.multiplet_label = "Mg II multiplet"
    second.multiplet_label = "Mg II multiplet"
    item = QTreeWidgetItem()
    component_index = {
        first_a.id: first_a,
        first_b.id: first_b,
        second_a.id: second_a,
        second_b.id: second_b,
    }

    renderer.populate_multiplet_row(item, (first, second), 1, component_index)

    assert item.childCount() == 4
    assert [item.child(i).text(1) for i in range(4)] == [
        "2796 c1",
        "2796 c2",
        "2803 c1",
        "2803 c2",
    ]
    assert item.child(0).data(0, Qt.ItemDataRole.UserRole) is first_a
    assert item.child(1).data(0, Qt.ItemDataRole.UserRole) is first_b
    assert item.child(2).data(0, Qt.ItemDataRole.UserRole) is second_a
    assert item.child(3).data(0, Qt.ItemDataRole.UserRole) is second_b


def test_populate_model_row_prefixes_labeled_value_cells(qapp: QApplication) -> None:
    """Masked parameter cells should be prefixed with the tie label."""
    assert qapp is not None
    port = _Port()
    port.tie_labels["redshift"] = "A"
    port.tie_tooltips["redshift"] = "Shared z [A]: c1, c2"
    renderer = OptimizeTreeRowRenderer(columns=_columns(), port=port)
    item = QTreeWidgetItem()
    component = _component()

    renderer.populate_model_row(item, component, 1)

    assert item.text(2) == "[A] 2.000000 ± 0.000012"
    assert item.toolTip(2).startswith("Shared z [A]: c1, c2")


def test_populate_model_row_leaves_unmasked_cells_unlabeled(qapp: QApplication) -> None:
    """Parameters outside the tie mask should render without a label or tooltip."""
    assert qapp is not None
    port = _Port()
    port.tie_labels["redshift"] = "A"
    port.tie_tooltips["redshift"] = "Shared z [A]: c1, c2"
    renderer = OptimizeTreeRowRenderer(columns=_columns(), port=port)
    item = QTreeWidgetItem()
    component = _component()

    renderer.populate_model_row(item, component, 1)

    assert item.text(3) == "13.50 ± 0.15"
    assert "Shared" not in item.toolTip(3)


def test_populate_model_row_untied_component_is_unlabeled(qapp: QApplication) -> None:
    """A component with no tie label configured should render plain values."""
    assert qapp is not None
    port = _Port()
    renderer = OptimizeTreeRowRenderer(columns=_columns(), port=port)
    item = QTreeWidgetItem()
    component = _component()

    renderer.populate_model_row(item, component, 1)

    assert item.text(2) == "2.000000 ± 0.000012"
    assert "Shared" not in item.toolTip(2)


def test_populate_model_row_renders_lookback_and_comoving_columns(qapp: QApplication) -> None:
    """Component rows should show cosmology-derived values matching core.cosmology directly."""
    assert qapp is not None
    port = _Port()
    renderer = OptimizeTreeRowRenderer(columns=_columns(), port=port)
    item = QTreeWidgetItem()
    component = _component()

    renderer.populate_model_row(item, component, 1)

    expected_lookback = lookback_time_gyr(2.0, PLANCK_2018)
    expected_comoving = comoving_distance_mpc(2.0, PLANCK_2018)
    assert item.text(COL_LOOKBACK) == f"{expected_lookback:.3f}"
    assert item.text(COL_COMOVING) == f"{expected_comoving:.1f}"


def test_populate_line_row_renders_lookback_and_comoving_columns(qapp: QApplication) -> None:
    """Line rows should derive cosmology columns from center_z."""
    assert qapp is not None
    port = _Port()
    renderer = OptimizeTreeRowRenderer(columns=_columns(), port=port)
    item = QTreeWidgetItem()
    line = _line("line-1")

    renderer.populate_line_row(item, line, 1)

    expected_lookback = lookback_time_gyr(line.center_z, PLANCK_2018)
    expected_comoving = comoving_distance_mpc(line.center_z, PLANCK_2018)
    assert item.text(COL_LOOKBACK) == f"{expected_lookback:.3f}"
    assert item.text(COL_COMOVING) == f"{expected_comoving:.1f}"


def test_populate_multiplet_row_uses_first_line_center_z_for_cosmology_columns(
    qapp: QApplication,
) -> None:
    """A grouped multiplet parent row should use lines[0].center_z for cosmology columns."""
    assert qapp is not None
    port = _Port()
    renderer = OptimizeTreeRowRenderer(columns=_columns(), port=port)
    component = _component()
    first = _line("line-1", model_ids=[component.id])
    second = _line("line-2", model_ids=[component.id])
    first.multiplet_label = "H I multiplet"
    second.multiplet_label = "H I multiplet"
    second.center_z = 3.5
    item = QTreeWidgetItem()

    renderer.populate_multiplet_row(item, (first, second), 1, {component.id: component})

    expected_lookback = lookback_time_gyr(first.center_z, PLANCK_2018)
    expected_comoving = comoving_distance_mpc(first.center_z, PLANCK_2018)
    assert item.text(COL_LOOKBACK) == f"{expected_lookback:.3f}"
    assert item.text(COL_COMOVING) == f"{expected_comoving:.1f}"


def test_populate_model_row_zero_redshift_renders_zero_cosmology_columns(
    qapp: QApplication,
) -> None:
    """A zero redshift should render zero lookback/comoving values without failing."""
    assert qapp is not None
    port = _Port()
    renderer = OptimizeTreeRowRenderer(columns=_columns(), port=port)
    item = QTreeWidgetItem()
    component = _component()
    component.parameters["redshift"].value = 0.0

    renderer.populate_model_row(item, component, 1)

    assert item.text(COL_LOOKBACK) == "0.000"
    assert item.text(COL_COMOVING) == "0.0"


def test_populate_model_row_missing_redshift_parameter_uses_default(qapp: QApplication) -> None:
    """A component missing the redshift parameter should fall back to z=0 without failing."""
    assert qapp is not None
    port = _Port()
    renderer = OptimizeTreeRowRenderer(columns=_columns(), port=port)
    item = QTreeWidgetItem()
    component = _component()
    del component.parameters["redshift"]

    renderer.populate_model_row(item, component, 1)

    assert item.text(COL_LOOKBACK) == "0.000"
    assert item.text(COL_COMOVING) == "0.0"
