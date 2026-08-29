"""Tests for optimization export use case."""

from __future__ import annotations

from chappy.application.optimize import (
    CosmologyParametersSnapshot,
    OptimizationExportLine,
    OptimizationExportRequest,
    OptimizeExportUseCase,
)
from chappy.application.optimize.export_usecase import (
    build_export_filename_stem,
    build_optimization_export_request,
)
from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.analysis import FitSummary
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.cosmology import PLANCK_2018


def _build_export_request() -> OptimizationExportRequest:
    """Create an export request with one line row.

    Returns:
        Export request used by document tests.
    """
    summary = FitSummary(
        chi_squared=1.0, reduced_chi_squared=0.9, degrees_of_freedom=30, n_parameters=4
    )
    line = OptimizationExportLine(
        region_name="C IV @ 5000.0-5200.0 (1)",
        line_display_id=1,
        component_display_id=1,
        redshift=2.0,
        redshift_error=1.2e-4,
        column_density=13.5,
        column_density_error=5e-2,
        b_parameter=12.0,
        b_parameter_error=0.3,
        covering_factor=0.9,
        covering_factor_error=0.02,
        line_species="C IV",
        model_label="C IV 1548",
        rest_wavelength=1548.2043,
        oscillator_strength=0.19,
        gamma_value=2.65e8,
        multiplet_label="C IV 1548/C IV 1551",
    )
    return OptimizationExportRequest(
        project_name="Test Project",
        region_id="region-1",
        region_name="C IV @ 5000.0-5200.0 (1)",
        lines=(line,),
        analysis_range=(5000.0, 5200.0),
        cosmology=CosmologyParametersSnapshot(
            h0=67.66, omega_m=0.3111, omega_lambda=0.6889, omega_k=0.0
        ),
        fit_summary=summary,
    )


def test_build_document_matches_existing_group_csv_contract() -> None:
    """Export use case should build the established CSV header and rows."""
    request = _build_export_request()

    document = OptimizeExportUseCase().build_document(request)

    assert document.header == (
        "region_name",
        "line_id",
        "component_id",
        "z",
        "z_err",
        "logN[cm-2]",
        "logN_err[cm-2]",
        "b[km/s]",
        "b_err[km/s]",
        "Cf",
        "Cf_err",
        "comoving_distance[Mpc]",
        "lookback_time[Gyr]",
        "chi_squared",
        "reduced_chi_squared",
        "degrees_of_freedom",
        "n_parameters",
        "line_species",
        "model_label",
        "rest_wavelength[Å]",
        "observed_wavelength[Å]",
        "oscillator_strength",
        "gamma[s-1]",
        "multiplet_label",
        "cosmology_h0",
        "cosmology_omega_m",
        "cosmology_omega_lambda",
        "cosmology_omega_k",
    )
    assert len(document.rows) == 1
    row = document.rows[0]
    assert row[0] == "C IV @ 5000.0-5200.0 (1)"
    assert row[1] == "1"
    assert row[2] == "1"
    assert row[3].startswith("2.0000000")
    assert row[5].startswith("13.5000")
    assert row[7].startswith("12.0000")
    assert row[9].startswith("0.9000")
    assert row[11]
    assert row[12]
    assert row[17] == "C IV"
    assert row[18] == "C IV 1548"
    assert row[21] == "0.190000"
    assert row[22] == "265000000.000000"
    assert row[23] == "C IV 1548/C IV 1551"
    assert row[24]
    assert document.filename_stem == "test_project_c_iv___5000_0-5200_0__1_"


class _Project:
    """Export project port test double."""

    def __init__(self, lines: list[AbsorptionLine], components: list[AbsorberComponent]) -> None:
        self.name = "Test Project"
        self.absorption_lines = {line.line_id: line for line in lines}
        self._components = {component.id: component for component in components}

    def find_absorber_component(self, component_id: str) -> AbsorberComponent | None:
        """Return a registered component by ID."""
        return self._components.get(component_id)


def _mg_ii_line(
    line_id: str,
    *,
    rest_wavelength: float,
    transition_name: str,
    oscillator_strength: float,
    multiplet_ids: list[str],
    model_ids: list[str],
) -> AbsorptionLine:
    """Return one Mg II multiplet member line."""
    return AbsorptionLine(
        line_id=line_id,
        species="Mg II",
        rest_wavelength=rest_wavelength,
        center_z=1.0,
        window_kms=150.0,
        multiplet_label="Mg II 2796/Mg II 2803",
        transition_name=transition_name,
        oscillator_strength=oscillator_strength,
        gamma_value=2.6e8,
        multiplet_ids=multiplet_ids,
        model_ids=model_ids,
    )


def _absorber(component_id: str, *, wavelength: float, column_density: float) -> AbsorberComponent:
    """Return an absorber component with a distinguishing column density."""
    return AbsorberComponent(
        component_id=component_id,
        wavelength=wavelength,
        redshift=1.0,
        column_density=column_density,
        b_parameter=10.0,
    )


def test_multiplet_export_uses_each_lines_own_components() -> None:
    """Each multiplet line should export its own components, numbered as displayed."""
    first_component = _absorber("comp-2796", wavelength=2796.35, column_density=13.0)
    second_component = _absorber("comp-2803", wavelength=2803.53, column_density=14.0)
    first = _mg_ii_line(
        "line-1",
        rest_wavelength=2796.35,
        transition_name="Mg II 2796",
        oscillator_strength=0.6155,
        multiplet_ids=["line-2"],
        model_ids=["comp-2796"],
    )
    second = _mg_ii_line(
        "line-2",
        rest_wavelength=2803.53,
        transition_name="Mg II 2803",
        oscillator_strength=0.3058,
        multiplet_ids=["line-1"],
        model_ids=["comp-2803"],
    )
    project = _Project([first, second], [first_component, second_component])
    region = AbsorptionRegion(region_id="region-1", line_ids=["line-1", "line-2"])

    request = build_optimization_export_request(project, region, PLANCK_2018)

    assert [
        (line.line_display_id, line.component_display_id, line.model_label, line.column_density)
        for line in request.lines
    ] == [(1, 1, "Mg II 2796", 13.0), (1, 1, "Mg II 2803", 14.0)]


def test_multiplet_export_includes_components_beyond_the_first_line() -> None:
    """A component attached only to a later line must not be dropped from the export."""
    shared = _absorber("comp-2796", wavelength=2796.35, column_density=13.0)
    extra = _absorber("comp-2803-extra", wavelength=2803.53, column_density=15.0)
    first = _mg_ii_line(
        "line-1",
        rest_wavelength=2796.35,
        transition_name="Mg II 2796",
        oscillator_strength=0.6155,
        multiplet_ids=["line-2"],
        model_ids=["comp-2796"],
    )
    second = _mg_ii_line(
        "line-2",
        rest_wavelength=2803.53,
        transition_name="Mg II 2803",
        oscillator_strength=0.3058,
        multiplet_ids=["line-1"],
        model_ids=["comp-2803-extra"],
    )
    project = _Project([first, second], [shared, extra])
    region = AbsorptionRegion(region_id="region-1", line_ids=["line-1", "line-2"])

    request = build_optimization_export_request(project, region, PLANCK_2018)

    assert [(line.model_label, line.column_density) for line in request.lines] == [
        ("Mg II 2796", 13.0),
        ("Mg II 2803", 15.0),
    ]


def test_single_line_export_keeps_display_numbering_for_unresolved_model_ids() -> None:
    """Single-line groups keep model-ID positions so numbers match the tree."""
    component = _absorber("comp-real", wavelength=2796.35, column_density=13.0)
    line = _mg_ii_line(
        "line-1",
        rest_wavelength=2796.35,
        transition_name="Mg II 2796",
        oscillator_strength=0.6155,
        multiplet_ids=[],
        model_ids=["comp-missing", "comp-real"],
    )
    project = _Project([line], [component])
    region = AbsorptionRegion(region_id="region-1", line_ids=["line-1"])

    request = build_optimization_export_request(project, region, PLANCK_2018)

    assert [line.component_display_id for line in request.lines] == [2]


def test_export_hides_errors_the_tree_does_not_display() -> None:
    """Non-positive parameter errors should export as absent, matching the tree."""
    component = _absorber("comp-real", wavelength=2796.35, column_density=13.0)
    component.parameters["redshift"].error = 1.2e-4
    component.parameters["column_density"].error = 0.0
    line = _mg_ii_line(
        "line-1",
        rest_wavelength=2796.35,
        transition_name="Mg II 2796",
        oscillator_strength=0.6155,
        multiplet_ids=[],
        model_ids=["comp-real"],
    )
    project = _Project([line], [component])
    region = AbsorptionRegion(region_id="region-1", line_ids=["line-1"])

    request = build_optimization_export_request(project, region, PLANCK_2018)

    assert request.lines[0].redshift_error == 1.2e-4
    assert request.lines[0].column_density_error is None


def test_build_export_filename_stem_sanitizes_project_and_region_names() -> None:
    """Filename formatter should replace path-unsafe punctuation."""
    assert (
        build_export_filename_stem("Project A", "C IV @ 5000.0-5200.0 (1)")
        == "project_a_c_iv___5000_0-5200_0__1_"
    )
