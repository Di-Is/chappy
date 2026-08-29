"""Tests for optimize model addition use case."""

from __future__ import annotations

from chappy.application.optimize import (
    AddOptimizeModelComponentsUseCase,
    ModelAdditionRequest,
    model_addition_wavelength_range,
)
from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.atomic_data import AtomicLine, AtomicLineData
from chappy.core.components.tie_set import FULL_TIE_MASK
from chappy.core.spectroscopy_project import SpectroscopyProject


def _line(
    line_id: str,
    *,
    species: str = "X",
    rest_wavelength: float = 1200.0,
    multiplet_ids: list[str] | None = None,
) -> AbsorptionLine:
    """Build an absorption line for model-addition tests."""
    return AbsorptionLine(
        line_id=line_id,
        species=species,
        rest_wavelength=rest_wavelength,
        center_z=1.0,
        window_kms=150.0,
        multiplet_label="",
        transition_name=f"{species} {rest_wavelength:.1f}",
        oscillator_strength=0.0,
        gamma_value=0.0,
        multiplet_ids=list(multiplet_ids or []),
    )


def _request(redshift: float = 1.2) -> ModelAdditionRequest:
    """Build a default model-addition request."""
    return ModelAdditionRequest(
        redshift=redshift, column_density=13.0, b_parameter=10.0, covering_factor=0.8
    )


def _usecase() -> AddOptimizeModelComponentsUseCase:
    """Build the model-addition use case with an explicit atomic data provider."""
    return AddOptimizeModelComponentsUseCase(AtomicLineData)


class _AtomicData:
    """Small atomic data provider for model-addition use case tests."""

    def __init__(self, lines: tuple[AtomicLine, ...]) -> None:
        self._lines = {line.line_id: line for line in lines}
        self._by_species_wavelength = {
            (line.species, round(line.wavelength_angstrom, 3)): line for line in lines
        }

    def get_line_by_id(self, line_id: str) -> AtomicLine | None:
        """Return an atomic line by identifier."""
        return self._lines.get(line_id)

    def get_lines_by_multiplet(self, multiplet_id: str) -> list[AtomicLine]:
        """Return atomic lines in a multiplet."""
        return [line for line in self._lines.values() if line.multiplet_id == multiplet_id]

    def get_line_by_species_wavelength(self, species: str, wavelength: float) -> AtomicLine | None:
        """Return an atomic line by species and wavelength."""
        return self._by_species_wavelength.get((species, round(wavelength, 3)))


def _atomic_line(
    identifier: str,
    *,
    wavelength: float,
    oscillator_strength: float,
    gamma_value: float,
    multiplet_id: str = "doublet",
) -> AtomicLine:
    """Build an atomic line for use case tests."""
    return AtomicLine(
        line_identifier=identifier,
        species="Mg II",
        wavelength_angstrom=wavelength,
        oscillator_strength=oscillator_strength,
        gamma_value=gamma_value,
        multiplet_id=multiplet_id,
    )


def test_add_components_creates_project_model_and_links_line() -> None:
    """Adding a single line creates one component and links it to the line."""
    project = SpectroscopyProject()
    line = _line("line-a")
    project.absorption_lines[line.line_id] = line

    result = _usecase().add_components(project, line, _request())

    assert project.model is not None
    assert tuple(result.components_by_line_id) == ("line-a",)
    component = result.components_by_line_id["line-a"]
    assert line.model_ids == [component.id]
    assert line.needs_optimization is True
    assert component in project.model.components
    assert component.parameters["redshift"].value == 1.2
    assert component.parameters["covering_factor"].value == 0.8
    assert component.parameters["covering_factor"].fixed is True
    assert result.tie_sets == ()


def test_add_components_expands_region_multiplet_siblings() -> None:
    """Adding one multiplet member creates sibling components and a multiplet group."""
    project = SpectroscopyProject()
    first = _line("line-a", rest_wavelength=1200.0, multiplet_ids=["line-b"])
    second = _line("line-b", rest_wavelength=1210.0, multiplet_ids=["line-a"])
    region = AbsorptionRegion(region_id="region-1", line_ids=[first.line_id, second.line_id])
    first.region_id = region.region_id
    second.region_id = region.region_id
    project.absorption_regions[region.region_id] = region
    project.absorption_lines[first.line_id] = first
    project.absorption_lines[second.line_id] = second

    result = _usecase().add_components(project, first, _request())

    assert set(result.components_by_line_id) == {"line-a", "line-b"}
    assert len(result.tie_sets) == 1
    tie_set = result.tie_sets[0]
    assert project.model is not None
    assert tie_set in tuple(project.model.iter_tie_sets())
    assert {component.id for component in tie_set.components} == {
        result.components_by_line_id["line-a"].id,
        result.components_by_line_id["line-b"].id,
    }
    assert first.model_ids == [result.components_by_line_id["line-a"].id]
    assert second.model_ids == [result.components_by_line_id["line-b"].id]


def test_add_components_preserves_per_line_atomic_parameters() -> None:
    """Multiplet components should keep each line's oscillator strength and gamma."""
    first_atomic = _atomic_line(
        "MgII_2796", wavelength=2796.352, oscillator_strength=0.6123, gamma_value=2.6e8
    )
    second_atomic = _atomic_line(
        "MgII_2803", wavelength=2803.531, oscillator_strength=0.3054, gamma_value=2.5e8
    )
    usecase = AddOptimizeModelComponentsUseCase(lambda: _AtomicData((first_atomic, second_atomic)))
    project = SpectroscopyProject()
    first = _line(
        "line-a",
        species="Mg II",
        rest_wavelength=first_atomic.wavelength_angstrom,
        multiplet_ids=["line-b"],
    )
    second = _line(
        "line-b",
        species="Mg II",
        rest_wavelength=second_atomic.wavelength_angstrom,
        multiplet_ids=["line-a"],
    )
    region = AbsorptionRegion(region_id="region-1", line_ids=[first.line_id, second.line_id])
    first.region_id = region.region_id
    second.region_id = region.region_id
    project.absorption_regions[region.region_id] = region
    project.absorption_lines[first.line_id] = first
    project.absorption_lines[second.line_id] = second

    result = usecase.add_components(project, first, _request())

    first_component = result.components_by_line_id[first.line_id]
    second_component = result.components_by_line_id[second.line_id]
    assert first_component.wavelength != second_component.wavelength
    assert first_component.oscillator_strength == first_atomic.oscillator_strength
    assert second_component.oscillator_strength == second_atomic.oscillator_strength
    assert first_component.gamma == first_atomic.gamma_value
    assert second_component.gamma == second_atomic.gamma_value


def test_add_components_resolves_absorption_line_id_cross_references_by_wavelength() -> None:
    """Absorption-line UUID cross references should still preserve atomic parameters."""
    first_atomic = _atomic_line(
        "MgII_2796", wavelength=2796.352, oscillator_strength=0.6123, gamma_value=2.6e8
    )
    second_atomic = _atomic_line(
        "MgII_2803", wavelength=2803.531, oscillator_strength=0.3054, gamma_value=2.5e8
    )
    usecase = AddOptimizeModelComponentsUseCase(lambda: _AtomicData((first_atomic, second_atomic)))
    project = SpectroscopyProject()
    first = _line(
        "absorption-uuid-1",
        species="Mg II",
        rest_wavelength=first_atomic.wavelength_angstrom,
        multiplet_ids=["absorption-uuid-2"],
    )
    second = _line(
        "absorption-uuid-2",
        species="Mg II",
        rest_wavelength=second_atomic.wavelength_angstrom,
        multiplet_ids=["absorption-uuid-1"],
    )
    region = AbsorptionRegion(region_id="region-1", line_ids=[first.line_id, second.line_id])
    first.region_id = region.region_id
    second.region_id = region.region_id
    project.absorption_regions[region.region_id] = region
    project.absorption_lines[first.line_id] = first
    project.absorption_lines[second.line_id] = second

    result = usecase.add_components(project, first, _request())

    first_component = result.components_by_line_id[first.line_id]
    second_component = result.components_by_line_id[second.line_id]
    assert first_component.oscillator_strength == first_atomic.oscillator_strength
    assert second_component.oscillator_strength == second_atomic.oscillator_strength
    assert first_component.gamma == first_atomic.gamma_value
    assert second_component.gamma == second_atomic.gamma_value


def test_delete_and_re_add_creates_fresh_default_multiplet_tie_set() -> None:
    """Re-adding deleted multiplet components rebuilds a default multiplet tie set."""
    project = SpectroscopyProject()
    first = _line("line-a", rest_wavelength=1200.0, multiplet_ids=["line-b"])
    second = _line("line-b", rest_wavelength=1210.0, multiplet_ids=["line-a"])
    region = AbsorptionRegion(region_id="region-1", line_ids=[first.line_id, second.line_id])
    first.region_id = region.region_id
    second.region_id = region.region_id
    project.absorption_regions[region.region_id] = region
    project.absorption_lines[first.line_id] = first
    project.absorption_lines[second.line_id] = second

    original = _usecase().add_components(project, first, _request())
    original_tie_set = original.tie_sets[0]
    original_tie_set.origin = "user"
    original_tie_set.mask = frozenset({"redshift"})

    for component in original.components_by_line_id.values():
        original_tie_set.remove_component(component)
        project.remove_absorber_component(component)
    project.model.remove_tie_set(original_tie_set)
    first.model_ids.clear()
    second.model_ids.clear()

    result = _usecase().add_components(project, first, _request())

    assert len(result.tie_sets) == 1
    tie_set = result.tie_sets[0]
    assert tie_set is not original_tie_set
    assert tie_set.origin == "multiplet"
    assert tie_set.mask == FULL_TIE_MASK
    assert len(tie_set.components) == 2


def test_add_components_does_not_expand_from_atomic_multiplet_only() -> None:
    """Identical atomic multiplet metadata must not create structural links."""
    first_atomic = _atomic_line(
        "MgII_2796", wavelength=2796.352, oscillator_strength=0.6, gamma_value=1.0
    )
    second_atomic = _atomic_line(
        "MgII_2803", wavelength=2803.531, oscillator_strength=0.3, gamma_value=1.0
    )
    usecase = AddOptimizeModelComponentsUseCase(lambda: _AtomicData((first_atomic, second_atomic)))
    project = SpectroscopyProject()
    first = _line("line-a", species="Mg II", rest_wavelength=first_atomic.wavelength_angstrom)
    second = _line("line-b", species="Mg II", rest_wavelength=second_atomic.wavelength_angstrom)
    region = AbsorptionRegion(region_id="region-1", line_ids=[first.line_id, second.line_id])
    first.region_id = region.region_id
    second.region_id = region.region_id
    project.absorption_regions[region.region_id] = region
    project.absorption_lines[first.line_id] = first
    project.absorption_lines[second.line_id] = second

    result = usecase.add_components(project, first, _request())

    assert tuple(result.components_by_line_id) == (first.line_id,)
    assert result.tie_sets == ()


def test_add_components_expands_materialized_links_with_empty_atomic_multiplet() -> None:
    """Materialized absorption links remain sufficient without DB multiplet metadata."""
    first_atomic = _atomic_line(
        "MgII_2796", wavelength=2796.352, oscillator_strength=0.6, gamma_value=1.0, multiplet_id=""
    )
    second_atomic = _atomic_line(
        "MgII_2803", wavelength=2803.531, oscillator_strength=0.3, gamma_value=1.0, multiplet_id=""
    )
    usecase = AddOptimizeModelComponentsUseCase(lambda: _AtomicData((first_atomic, second_atomic)))
    project = SpectroscopyProject()
    first = _line(
        "line-a",
        species="Mg II",
        rest_wavelength=first_atomic.wavelength_angstrom,
        multiplet_ids=["line-b"],
    )
    second = _line(
        "line-b",
        species="Mg II",
        rest_wavelength=second_atomic.wavelength_angstrom,
        multiplet_ids=["line-a"],
    )
    region = AbsorptionRegion(region_id="region-1", line_ids=[first.line_id, second.line_id])
    first.region_id = region.region_id
    second.region_id = region.region_id
    project.absorption_regions[region.region_id] = region
    project.absorption_lines[first.line_id] = first
    project.absorption_lines[second.line_id] = second

    result = usecase.add_components(project, first, _request())

    assert set(result.components_by_line_id) == {first.line_id, second.line_id}
    assert len(result.tie_sets) == 1


def test_model_addition_wavelength_range_intersects_line_lambda_range() -> None:
    """Accepted model-addition bounds are constrained by the line lambda range."""
    line = _line("line-a", rest_wavelength=1000.0)
    line.center_z = 1.0
    line.window_kms = 300.0
    line.lambda_range = (1999.5, 2000.4)

    assert model_addition_wavelength_range(line) == (1999.5, 2000.4)
