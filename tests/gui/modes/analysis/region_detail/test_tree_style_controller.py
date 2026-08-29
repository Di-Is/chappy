"""Tests for optimize tree style controller."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTreeWidgetItem

from chappy.core.absorption.models import AbsorptionLine
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.modes.analysis.region_detail.tree.tree_style_controller import (
    OptimizeTreeStyleColumns,
    OptimizeTreeStyleController,
)


@pytest.fixture(name="qapp")
def fixture_qapp() -> QApplication:
    """Provide a QApplication instance for Qt items."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _Port:
    """Style-port test double."""

    def __init__(self) -> None:
        self.ensure_count = 0
        self.tie_accent_indices: dict[str, int] = {}

    def ensure_tree_covering_factor_parameter(self, component: AbsorberComponent) -> None:
        """Record covering factor initialization requests."""
        self.ensure_count += 1

    def tie_accent_index_for(
        self, component: AbsorberComponent, parameter_name: str
    ) -> int | None:
        """Return a configured tie accent index for the given parameter, if any."""
        return self.tie_accent_indices.get(parameter_name)


def _line(line_id: str, component_id: str, *, needs_optimization: bool) -> AbsorptionLine:
    """Return a minimal absorption line linked to a component."""
    return AbsorptionLine(
        line_id=line_id,
        species="H I",
        rest_wavelength=1215.67,
        center_z=2.0,
        window_kms=150.0,
        region_id="region-1",
        multiplet_label="",
        transition_name="Ly alpha",
        oscillator_strength=0.1,
        gamma_value=1e8,
        model_ids=[component_id],
        needs_optimization=needs_optimization,
    )


def _controller(port: _Port) -> OptimizeTreeStyleController:
    """Return a style controller with compact test columns."""
    return OptimizeTreeStyleController(
        columns=OptimizeTreeStyleColumns(parameter_columns={2: "redshift", 3: "column_density"}),
        port=port,
    )


def test_apply_parameter_styles_marks_fixed_and_stale_cells(qapp: QApplication) -> None:
    """Controller should style fixed parameters and non-fixed stale cells."""
    assert qapp is not None
    component = AbsorberComponent(component_id="component-1", redshift=2.0)
    component.parameters["redshift"].fixed = True
    item = QTreeWidgetItem()
    item.setData(0, Qt.ItemDataRole.UserRole, component)

    project = SpectroscopyProject()
    project.absorption_lines = {"line-1": _line("line-1", component.id, needs_optimization=True)}
    port = _Port()
    controller = _controller(port)

    controller.apply_parameter_styles(item, project)

    fixed_color = controller._fixed_parameter_brush.color()
    assert item.background(2).color().name(fixed_color.NameFormat.HexArgb) == fixed_color.name(
        fixed_color.NameFormat.HexArgb
    )
    assert item.background(3).style() != Qt.BrushStyle.NoBrush
    assert port.ensure_count == 1


def test_apply_parameter_styles_clears_stale_cells_when_not_stale(qapp: QApplication) -> None:
    """Controller should clear stale styling when linked lines are not stale."""
    assert qapp is not None
    component = AbsorberComponent(component_id="component-1", redshift=2.0)
    item = QTreeWidgetItem()
    item.setData(0, Qt.ItemDataRole.UserRole, component)

    project = SpectroscopyProject()
    project.absorption_lines = {"line-1": _line("line-1", component.id, needs_optimization=False)}
    port = _Port()

    _controller(port).apply_parameter_styles(item, project)

    assert item.background(2).style() == Qt.BrushStyle.NoBrush
    assert item.background(3).style() == Qt.BrushStyle.NoBrush
    assert port.ensure_count == 1


def test_apply_parameter_styles_applies_tie_accent_color(qapp: QApplication) -> None:
    """A masked, tied parameter cell should receive its tie set's accent color."""
    assert qapp is not None
    component = AbsorberComponent(component_id="component-1", redshift=2.0)
    item = QTreeWidgetItem()
    item.setData(0, Qt.ItemDataRole.UserRole, component)

    port = _Port()
    port.tie_accent_indices["redshift"] = 0

    _controller(port).apply_parameter_styles(item, None)

    assert item.background(2).style() != Qt.BrushStyle.NoBrush
    assert item.background(3).style() == Qt.BrushStyle.NoBrush


def test_apply_parameter_styles_fixed_style_wins_over_tie_accent(qapp: QApplication) -> None:
    """Fixed styling should take precedence over the tie accent color."""
    assert qapp is not None
    component = AbsorberComponent(component_id="component-1", redshift=2.0)
    component.parameters["redshift"].fixed = True
    item = QTreeWidgetItem()
    item.setData(0, Qt.ItemDataRole.UserRole, component)

    port = _Port()
    port.tie_accent_indices["redshift"] = 0

    controller = _controller(port)
    controller.apply_parameter_styles(item, None)

    fixed_color = controller._fixed_parameter_brush.color()
    assert item.background(2).color().name(fixed_color.NameFormat.HexArgb) == fixed_color.name(
        fixed_color.NameFormat.HexArgb
    )


def test_apply_parameter_styles_stale_wins_over_tie_accent(qapp: QApplication) -> None:
    """A non-fixed, tied parameter cell should show the stale color when stale."""
    assert qapp is not None
    component = AbsorberComponent(component_id="component-1", redshift=2.0)
    item = QTreeWidgetItem()
    item.setData(0, Qt.ItemDataRole.UserRole, component)

    project = SpectroscopyProject()
    project.absorption_lines = {"line-1": _line("line-1", component.id, needs_optimization=True)}
    port = _Port()
    port.tie_accent_indices["redshift"] = 0

    controller = _controller(port)
    controller.apply_parameter_styles(item, project)

    stale_color = controller._stale_parameter_brush.color()
    assert item.background(2).color().name(stale_color.NameFormat.HexArgb) == stale_color.name(
        stale_color.NameFormat.HexArgb
    )
