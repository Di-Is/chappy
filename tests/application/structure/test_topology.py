"""Tests for exact reusable structure topology snapshots."""

from __future__ import annotations

from chappy.application.structure import StructureTopologySnapshotService
from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.masking import MaskDefinition, MaskMode
from chappy.core.spectroscopy_project import SpectroscopyProject


def _line(line_id: str, region_id: str, multiplet_ids: tuple[str, ...]) -> AbsorptionLine:
    """Build one structure line."""
    return AbsorptionLine(
        line_id=line_id,
        species="C IV",
        rest_wavelength=1548.2,
        center_z=2.0,
        window_kms=120.0,
        multiplet_label="C IV",
        transition_name=line_id,
        oscillator_strength=0.19,
        gamma_value=1e8,
        region_id=region_id,
        multiplet_ids=list(multiplet_ids),
    )


def test_restore_preserves_mapping_order_objects_and_every_topology_field() -> None:
    """Rollback should restore exact identity while leaving derived caches to the executor."""
    project = SpectroscopyProject()
    first = AbsorptionRegion(
        region_id="first",
        line_ids=["line-1"],
        display_color="#111111",
        analysis_range=(1000.0, 1010.0),
    )
    second = AbsorptionRegion(
        region_id="second",
        line_ids=["line-2"],
        display_color="#222222",
        analysis_range=(1020.0, 1030.0),
    )
    line_1 = _line("line-1", "first", ("line-2",))
    line_2 = _line("line-2", "second", ("line-1",))
    project.absorption_regions.update((("first", first), ("second", second)))
    project.absorption_lines.update((("line-1", line_1), ("line-2", line_2)))
    mask_1 = MaskDefinition(
        identifier="mask-1",
        label="first",
        mode=MaskMode.RANGE,
        start_wavelength=1000.0,
        end_wavelength=1005.0,
        group_id="first",
    )
    mask_2 = MaskDefinition(
        identifier="mask-2",
        label="second",
        mode=MaskMode.RANGE,
        start_wavelength=1020.0,
        end_wavelength=1025.0,
        group_id="second",
    )
    project.model.restore_mask_definitions_for_transaction((mask_1, mask_2), model_was_valid=False)
    component = AbsorberComponent(component_id="component", group_id="first")
    project.model.add_component(component)
    region_mapping = project.absorption_regions
    line_mapping = project.absorption_lines
    snapshot = StructureTopologySnapshotService().capture(project)

    first.line_ids[:] = ["line-2"]
    first.display_color = "#ffffff"
    first.analysis_range = None
    line_1.region_id = "second"
    line_1.multiplet_ids.clear()
    project.absorption_regions.clear()
    project.absorption_regions.update(
        (("second", AbsorptionRegion("second")), ("new", AbsorptionRegion("new")))
    )
    project.absorption_lines.clear()
    project.absorption_lines["new-line"] = _line("new-line", "new", ())
    project.model.restore_mask_definitions_for_transaction((mask_2,), model_was_valid=False)
    component.set_group("second")

    with project.model.suppress_scientific_notifications():
        StructureTopologySnapshotService().restore(project, snapshot)

    assert project.absorption_regions is region_mapping
    assert project.absorption_lines is line_mapping
    assert tuple(project.absorption_regions) == ("first", "second")
    assert tuple(project.absorption_lines) == ("line-1", "line-2")
    assert project.absorption_regions["first"] is first
    assert project.absorption_regions["second"] is second
    assert project.absorption_lines["line-1"] is line_1
    assert project.absorption_lines["line-2"] is line_2
    assert first.line_ids == ["line-1"]
    assert first.display_color == "#111111"
    assert first.analysis_range == (1000.0, 1010.0)
    assert line_1.region_id == "first"
    assert line_1.multiplet_ids == ["line-2"]
    assert project.model.mask_definitions == (mask_1, mask_2)
    assert all(
        current is expected
        for current, expected in zip(project.model.mask_definitions, (mask_1, mask_2), strict=True)
    )
    assert component.group_id == "first"
