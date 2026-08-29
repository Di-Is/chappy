"""Tests for optimize tree render controller."""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtWidgets import QTreeWidgetItem

from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.modes.analysis.region_detail.tree.tree_render_controller import (
    OptimizeTreeRenderController,
)


class _Port:
    """Panel-port test double."""

    def __init__(self) -> None:
        self.clear_count = 0
        self.empty_count = 0
        self.rendered_groups: tuple[tuple[AbsorptionLine, ...], ...] = ()
        self.rendered_components: dict[str, AbsorberComponent] = {}
        self.rendered_count = 0
        self.component_rows: list[tuple[QTreeWidgetItem, AbsorberComponent]] = []
        self.refreshed_rows: list[tuple[QTreeWidgetItem, AbsorberComponent]] = []
        self.sync_tie_labels_calls: list[SpectroscopyProject] = []
        self.cosmology_reload_count = 0

    def reload_cosmology_display_cache(self) -> None:
        """Record cosmology cache reload requests."""
        self.cosmology_reload_count += 1

    def clear_tree_view(self) -> None:
        """Record tree clearing."""
        self.clear_count += 1

    def apply_empty_tree_state(self) -> None:
        """Record empty-state refresh."""
        self.empty_count += 1

    def sync_tie_labels(self, project: SpectroscopyProject) -> None:
        """Record tie label synchronization requests."""
        self.sync_tie_labels_calls.append(project)

    def render_tree_groups(
        self,
        groups: tuple[tuple[AbsorptionLine, ...], ...],
        component_index: Mapping[str, AbsorberComponent],
    ) -> None:
        """Record render inputs."""
        self.rendered_groups = groups
        self.rendered_components = dict(component_index)

    def apply_region_tree_rendered(self) -> None:
        """Record rendered-state refresh."""
        self.rendered_count += 1

    def iter_component_tree_rows(self) -> list[tuple[QTreeWidgetItem, AbsorberComponent]]:
        """Return configured component rows."""
        return self.component_rows

    def refresh_component_tree_row(
        self, item: QTreeWidgetItem, component: AbsorberComponent
    ) -> None:
        """Record row refresh requests."""
        self.refreshed_rows.append((item, component))


def _line(line_id: str, *, center_z: float, model_ids: list[str] | None = None) -> AbsorptionLine:
    """Return a minimal absorption line."""
    return AbsorptionLine(
        line_id=line_id,
        species="H I",
        rest_wavelength=1215.67,
        center_z=center_z,
        window_kms=150.0,
        region_id="region-1",
        multiplet_label="",
        transition_name=f"H I {line_id}",
        oscillator_strength=0.1,
        gamma_value=1e8,
        model_ids=model_ids or [],
    )


def test_clear_tree_refreshes_empty_state() -> None:
    """Controller should clear rows and refresh dependent empty state."""
    port = _Port()
    controller = OptimizeTreeRenderController(port=port)

    controller.clear_tree()

    assert port.clear_count == 1
    assert port.empty_count == 1
    assert port.rendered_count == 0


def test_rebuild_without_project_refreshes_empty_state() -> None:
    """Controller should stop after clearing when no project is available."""
    port = _Port()
    controller = OptimizeTreeRenderController(port=port)
    region = AbsorptionRegion(region_id="region-1", line_ids=["line-1"])

    controller.rebuild_region(None, region)

    assert port.clear_count == 1
    assert port.empty_count == 1
    assert port.rendered_groups == ()
    assert port.rendered_count == 0


def test_rebuild_region_sorts_lines_and_indexes_components() -> None:
    """Controller should build sorted grouped lines and referenced components."""
    project = SpectroscopyProject()
    component = AbsorberComponent(component_id="component-1")
    project.model.add_component(component)
    high = _line("high", center_z=2.0, model_ids=[component.id])
    low = _line("low", center_z=1.0)
    project.absorption_lines = {high.line_id: high, low.line_id: low}
    region = AbsorptionRegion(region_id="region-1", line_ids=[high.line_id, low.line_id])

    port = _Port()
    controller = OptimizeTreeRenderController(port=port)
    controller.rebuild_region(project, region)

    assert port.clear_count == 1
    assert port.empty_count == 0
    assert tuple(group[0].line_id for group in port.rendered_groups) == ("low", "high")
    assert port.rendered_components == {component.id: component}
    assert port.rendered_count == 1
    assert port.sync_tie_labels_calls == [project]


def test_rebuild_region_requires_project_model() -> None:
    """Existing project without a model is an invalid render state."""
    project = SpectroscopyProject()
    project.model = None
    line = _line("line-1", center_z=1.0)
    project.absorption_lines = {line.line_id: line}
    region = AbsorptionRegion(region_id="region-1", line_ids=[line.line_id])
    port = _Port()
    controller = OptimizeTreeRenderController(port=port)

    try:
        controller.rebuild_region(project, region)
    except RuntimeError as exc:
        assert "Project model is required" in str(exc)
    else:
        raise AssertionError("Expected missing project model to fail fast")


def test_refresh_model_parameters_updates_rows_with_current_components() -> None:
    """Controller should refresh rendered rows using current project components."""
    project = SpectroscopyProject()
    stale_component = AbsorberComponent(component_id="component-1", redshift=1.0)
    current_component = AbsorberComponent(component_id="component-1", redshift=2.0)
    project.model.add_component(current_component)
    item = QTreeWidgetItem()

    port = _Port()
    port.component_rows = [(item, stale_component)]
    controller = OptimizeTreeRenderController(port=port)
    controller.refresh_model_parameters(project)

    assert port.refreshed_rows == [(item, current_component)]
