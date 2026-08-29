"""Tests for optimize parameter context controller."""

from __future__ import annotations

from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.atomic_data import AtomicLine
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.components.tie_set import ParameterTieSet
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.modes.analysis.region_detail.parameters.parameter_context_controller import (
    OptimizeParameterContextController,
)


def _controller() -> OptimizeParameterContextController:
    """Return a parameter context controller for tests."""
    return OptimizeParameterContextController(multiplet_redshift_tolerance=5e-5, min_redshift=-0.1)


def _line(
    line_id: str,
    *,
    region_id: str = "region-1",
    model_ids: list[str] | None = None,
    multiplet_ids: list[str] | None = None,
    center_z: float = 2.0,
) -> AbsorptionLine:
    """Return a minimal absorption line."""
    return AbsorptionLine(
        line_id=line_id,
        species="H I",
        rest_wavelength=1215.67,
        center_z=center_z,
        window_kms=150.0,
        lambda_range=(3500.0, 4000.0),
        region_id=region_id,
        multiplet_label="",
        transition_name="Ly alpha",
        oscillator_strength=0.1,
        gamma_value=1e8,
        model_ids=model_ids or [],
        multiplet_ids=multiplet_ids or [],
    )


def _component(component_id: str, *, redshift: float = 2.0) -> AbsorberComponent:
    """Return a deterministic absorber component."""
    return AbsorberComponent(component_id=component_id, wavelength=1215.67, redshift=redshift)


def _atomic_line(line_id: str, *, multiplet_id: str) -> AtomicLine:
    """Return atomic metadata for DB-multiplet negative tests."""
    return AtomicLine(
        line_identifier=line_id,
        species="H I",
        wavelength_angstrom=1215.67,
        oscillator_strength=0.1,
        gamma_value=1e8,
        multiplet_id=multiplet_id,
    )


def test_validate_value_uses_dynamic_redshift_bounds() -> None:
    """Controller should validate redshift against linked line bounds."""
    project = SpectroscopyProject()
    component = _component("component-1")
    project.model.add_component(component)
    line = _line("line-1", model_ids=[component.id])
    project.absorption_lines[line.line_id] = line

    controller = _controller()

    assert controller.validate_value(project, "redshift", 2.0, component) is True
    assert controller.validate_value(project, "redshift", 1.5, component) is False
    assert controller.validate_value(project, "redshift", 3.0, component) is False


def test_validate_value_handles_non_redshift_parameters() -> None:
    """Controller should validate non-redshift parameter ranges."""
    component = _component("component-1")
    controller = _controller()

    assert controller.validate_value(None, "column_density", 15.0, component) is True
    assert controller.validate_value(None, "column_density", -1.0, component) is False
    assert controller.validate_value(None, "b_parameter", 10.0, component) is True
    assert controller.validate_value(None, "b_parameter", -5.0, component) is False
    assert controller.validate_value(None, "covering_factor", 0.5, component) is True
    assert controller.validate_value(None, "covering_factor", 1.5, component) is False
    assert controller.validate_value(None, "covering_factor", -0.1, component) is False


def test_line_display_id_and_component_index() -> None:
    """Controller should resolve display id and component index."""
    project = SpectroscopyProject()
    component = _component("component-1")
    project.model.add_component(component)
    high = _line("high", model_ids=[component.id], center_z=2.0)
    low = _line("low", model_ids=[], center_z=1.0)
    project.absorption_lines = {high.line_id: high, low.line_id: low}
    project.absorption_regions = {
        "region-1": AbsorptionRegion(region_id="region-1", line_ids=["high", "low"])
    }

    controller = _controller()

    assert controller.line_for_component(project, component) is high
    assert controller.line_display_id(project, high) == 2
    assert controller.component_index(component, high) == 1


def test_collect_multiplet_components_uses_materialized_line_tokens() -> None:
    """Controller should collect materialized multiplet siblings without group objects."""
    project = SpectroscopyProject()
    first = _component("component-1")
    second = _component("component-2")
    project.model.add_component(first)
    project.model.add_component(second)
    first_line = _line("line-1", model_ids=[first.id], multiplet_ids=["line-2"])
    second_line = _line("line-2", model_ids=[second.id], multiplet_ids=["line-1"])
    project.absorption_lines = {first_line.line_id: first_line, second_line.line_id: second_line}

    components = _controller().collect_multiplet_components(project, first)

    assert components == [first, second]


def test_collect_multiplet_components_ignores_atomic_multiplet_without_links() -> None:
    """Identical DB multiplet metadata must not expand parameter context."""
    project = SpectroscopyProject()
    first = _component("component-1")
    second = _component("component-2")
    first.atomic_line = _atomic_line("atomic-1", multiplet_id="shared-db-group")
    second.atomic_line = _atomic_line("atomic-2", multiplet_id="shared-db-group")
    project.model.add_component(first)
    project.model.add_component(second)
    first_line = _line("line-1", model_ids=[first.id])
    second_line = _line("line-2", model_ids=[second.id])
    project.absorption_lines = {first_line.line_id: first_line, second_line.line_id: second_line}

    components = _controller().collect_multiplet_components(project, first)

    assert components == [first]


def test_collect_multiplet_components_uses_links_when_atomic_multiplets_differ() -> None:
    """Materialized links expand even when DB multiplet metadata differs."""
    project = SpectroscopyProject()
    first = _component("component-1")
    second = _component("component-2")
    first.atomic_line = _atomic_line("atomic-1", multiplet_id="db-a")
    second.atomic_line = _atomic_line("atomic-2", multiplet_id="db-b")
    project.model.add_component(first)
    project.model.add_component(second)
    first_line = _line("line-1", model_ids=[first.id], multiplet_ids=["line-2"])
    second_line = _line("line-2", model_ids=[second.id], multiplet_ids=["line-1"])
    project.absorption_lines = {first_line.line_id: first_line, second_line.line_id: second_line}

    components = _controller().collect_multiplet_components(project, first)

    assert components == [first, second]


def test_collect_multiplet_components_uses_full_mask_multiplet_tie_set() -> None:
    """A materialized (origin='multiplet') full-mask tie set expands to all members."""
    first = _component("component-1")
    second = _component("component-2")
    tie_set = ParameterTieSet("doublet-1", origin="multiplet")
    tie_set.add_component(first)
    tie_set.add_component(second)

    components = _controller().collect_multiplet_components(None, first)

    assert components == [first, second]


def test_collect_multiplet_components_ignores_user_tie_set() -> None:
    """A user-created tie set must not be treated as a materialized multiplet."""
    first = _component("component-1")
    second = _component("component-2")
    tie_set = ParameterTieSet("user-1", mask=frozenset({"redshift"}), origin="user")
    tie_set.add_component(first)
    tie_set.add_component(second)

    components = _controller().collect_multiplet_components(None, first)

    assert components == [first]
