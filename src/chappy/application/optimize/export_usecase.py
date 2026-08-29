"""Use case for building optimization export documents."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Protocol

from chappy.application.optimize.models import (
    CosmologyParametersSnapshot,
    OptimizationExportDocument,
    OptimizationExportLine,
    OptimizationExportRequest,
)
from chappy.core.absorption_display import (
    format_region_display,
    group_lines_by_multiplet,
    iter_component_display_rows,
    sort_lines_for_display,
)
from chappy.core.analysis import FitSummary
from chappy.core.cosmology import CosmologyParameters, comoving_distance_mpc, lookback_time_gyr

if TYPE_CHECKING:
    from collections.abc import Iterable

    from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
    from chappy.core.components.absorber import AbsorberComponent


class OptimizeExportProjectPort(Protocol):
    """Project operations required to build optimization export requests."""

    name: str
    absorption_lines: dict[str, AbsorptionLine]

    def find_absorber_component(self, component_id: str) -> AbsorberComponent | None:
        """Return an absorber component by ID."""
        ...


class OptimizeExportUseCase:
    """Build optimization export documents from typed request data."""

    def build_document(self, request: OptimizationExportRequest) -> OptimizationExportDocument:
        """Build a CSV document for one absorption region.

        Args:
            request: Typed export request containing normalized line snapshots.

        Returns:
            Export document with a stable filename stem, header, and rows.
        """
        return OptimizationExportDocument(
            filename_stem=build_export_filename_stem(request.project_name, request.region_name),
            header=_CSV_HEADER,
            rows=tuple(self._build_rows(request)),
        )

    def _build_rows(self, request: OptimizationExportRequest) -> Iterable[tuple[str, ...]]:
        """Build CSV rows for all requested export lines.

        Args:
            request: Typed export request containing normalized line snapshots.

        Yields:
            CSV row tuples in display order.
        """
        summary = request.fit_summary
        base_stats = (
            _format_decimal(summary.chi_squared, 6),
            _format_decimal(summary.reduced_chi_squared, 6),
            _format_decimal(summary.degrees_of_freedom, 3),
            str(summary.n_parameters) if summary.n_parameters is not None else "",
        )
        cosmology = request.cosmology
        cosmology_columns = (
            _format_decimal(cosmology.h0, 3),
            _format_decimal(cosmology.omega_m, 6),
            _format_decimal(cosmology.omega_lambda, 6),
            _format_decimal(cosmology.omega_k, 6),
        )
        calculation_cosmology = CosmologyParameters(
            h0=cosmology.h0, omega_m=cosmology.omega_m, omega_lambda=cosmology.omega_lambda
        )

        for line in request.lines:
            comoving = comoving_distance_mpc(line.redshift, calculation_cosmology)
            lookback = lookback_time_gyr(line.redshift, calculation_cosmology)
            yield (
                line.region_name,
                str(line.line_display_id),
                str(line.component_display_id),
                _format_decimal(line.redshift, 7),
                _format_optional_error(line.redshift_error, 7),
                _format_decimal(line.column_density, 5),
                _format_optional_error(line.column_density_error, 5),
                _format_decimal(line.b_parameter, 5),
                _format_optional_error(line.b_parameter_error, 5),
                _format_decimal(line.covering_factor, 5),
                _format_optional_error(line.covering_factor_error, 5),
                _format_decimal(comoving, 7),
                _format_decimal(lookback, 7),
                *base_stats,
                line.line_species,
                line.model_label,
                _format_decimal(line.rest_wavelength, 5),
                _format_decimal(line.rest_wavelength * (1.0 + line.redshift), 5),
                _format_decimal(line.oscillator_strength, 6),
                _format_decimal(line.gamma_value, 6),
                line.multiplet_label,
                *cosmology_columns,
            )


def build_optimization_export_request(
    project: OptimizeExportProjectPort,
    region: AbsorptionRegion,
    cosmology: CosmologyParameters,
    fit_summary: FitSummary | None = None,
) -> OptimizationExportRequest:
    """Create an optimization export request from project state.

    Args:
        project: Project containing absorption lines and absorber components.
        region: Absorption region to export.
        cosmology: Cosmology parameters for derived quantities.
        fit_summary: Optional fit summary to include in the export.

    Returns:
        Typed request detached from mutable project and component objects.
    """
    region_name = _get_export_region_display_name(project, region)
    return OptimizationExportRequest(
        project_name=project.name or "project",
        region_id=region.region_id,
        region_name=region_name,
        lines=tuple(_iter_optimization_export_lines(project, region, region_name)),
        analysis_range=region.analysis_range,
        cosmology=CosmologyParametersSnapshot(
            h0=cosmology.h0,
            omega_m=cosmology.omega_m,
            omega_lambda=cosmology.omega_lambda,
            omega_k=cosmology.omega_k,
        ),
        fit_summary=fit_summary or FitSummary(),
    )


def _iter_optimization_export_lines(
    project: OptimizeExportProjectPort, region: AbsorptionRegion, region_name: str
) -> Iterable[OptimizationExportLine]:
    """Iterate export line snapshots in optimize tree display order.

    Args:
        project: Project containing absorption lines and absorber components.
        region: Absorption region to export.
        region_name: Display name for the exported region.

    Yields:
        Export line snapshots for each component and line pair.
    """
    for display_id, multiplet_lines in _iter_optimization_export_multiplet_groups(project, region):
        yield from _iter_optimization_multiplet_export_lines(
            project=project,
            multiplet_lines=multiplet_lines,
            display_id=display_id,
            region_name=region_name,
        )


def _iter_optimization_multiplet_export_lines(
    project: OptimizeExportProjectPort,
    multiplet_lines: list[AbsorptionLine],
    display_id: int,
    region_name: str,
) -> Iterable[OptimizationExportLine]:
    """Iterate export snapshots for one multiplet group.

    Args:
        project: Project containing absorber components.
        multiplet_lines: Lines belonging to one display multiplet group.
        display_id: One-based display ID for the multiplet group.
        region_name: Display name for the exported region.

    Yields:
        Export line snapshots for each line and its own components, numbered
        exactly as the optimize tree displays them.
    """
    if not multiplet_lines:
        return

    for line, component, component_index in iter_component_display_rows(
        multiplet_lines, project.find_absorber_component
    ):
        yield OptimizationExportLine(
            region_name=region_name,
            line_display_id=display_id,
            component_display_id=component_index,
            redshift=_export_parameter_value(component, "redshift"),
            redshift_error=_export_parameter_error(component, "redshift"),
            column_density=_export_parameter_value(component, "column_density"),
            column_density_error=_export_parameter_error(component, "column_density"),
            b_parameter=_export_parameter_value(component, "b_parameter"),
            b_parameter_error=_export_parameter_error(component, "b_parameter"),
            covering_factor=_export_parameter_value(component, "covering_factor"),
            covering_factor_error=_export_parameter_error(component, "covering_factor"),
            line_species=line.species,
            model_label=line.transition_name,
            rest_wavelength=line.rest_wavelength,
            oscillator_strength=line.oscillator_strength,
            gamma_value=line.gamma_value,
            multiplet_label=line.multiplet_label,
        )


def _iter_optimization_export_multiplet_groups(
    project: OptimizeExportProjectPort, region: AbsorptionRegion
) -> Iterable[tuple[int, list[AbsorptionLine]]]:
    """Iterate multiplet groups with display IDs matching the optimize tree.

    Args:
        project: Project containing absorption lines.
        region: Absorption region containing line IDs.

    Yields:
        Tuples of one-based display ID and grouped absorption lines.
    """
    lines = list(_iter_optimization_export_region_lines(project, region))
    multiplet_groups = group_lines_by_multiplet(lines)
    yield from enumerate(multiplet_groups, start=1)


def _iter_optimization_export_region_lines(
    project: OptimizeExportProjectPort, region: AbsorptionRegion
) -> Iterable[AbsorptionLine]:
    """Iterate absorption lines in a region sorted for display.

    Args:
        project: Project containing absorption lines.
        region: Absorption region containing line IDs.

    Returns:
        Sorted absorption lines.
    """
    lines = [
        project.absorption_lines[line_id]
        for line_id in region.line_ids
        if line_id in project.absorption_lines
    ]
    return sort_lines_for_display(lines)


def _get_export_region_display_name(
    project: OptimizeExportProjectPort, region: AbsorptionRegion
) -> str:
    """Get the dynamic display name for an exported absorption region.

    Args:
        project: Project containing absorption lines.
        region: Absorption region to describe.

    Returns:
        Display name generated from line content and analysis range.
    """
    lines = list(_iter_optimization_export_region_lines(project, region))
    display_info = format_region_display(lines, region.analysis_range)
    return display_info.display_name


def _export_parameter_value(component: AbsorberComponent, key: str) -> float:
    """Read a component parameter value for export.

    Args:
        component: Absorber component to inspect.
        key: Parameter key.

    Returns:
        Parameter value, or NaN when missing.
    """
    parameter = component.parameters.get(key)
    if parameter is None:
        return math.nan
    return float(parameter.value)


def _export_parameter_error(component: AbsorberComponent, key: str) -> float | None:
    """Read a component parameter error for export.

    Args:
        component: Absorber component to inspect.
        key: Parameter key.

    Returns:
        Parameter error, or None when absent or not displayed by the optimize
        tree (non-finite or non-positive values).
    """
    parameter = component.parameters.get(key)
    if parameter is None:
        return None
    error = float(parameter.error)
    if not math.isfinite(error) or error <= 0.0:
        return None
    return error


def build_export_filename_stem(project_name: str, region_name: str) -> str:
    """Build a sanitized filename stem for optimization exports.

    Args:
        project_name: Project display name.
        region_name: Region display name.

    Returns:
        Lowercase filename stem with unsafe characters replaced by underscores.
    """
    base = f"{project_name or 'project'}_{region_name}"
    sanitized = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in base)
    return sanitized.lower()


def _format_optional_error(value: float | None, digits: int) -> str:
    """Format an optional error value.

    Args:
        value: Error value to format.
        digits: Number of decimal places.

    Returns:
        Formatted value, or an empty string when absent or non-finite.
    """
    return _format_decimal(value, digits) if value is not None else ""


def _format_decimal(value: float | None, digits: int) -> str:
    """Format a finite decimal value.

    Args:
        value: Value to format.
        digits: Number of decimal places.

    Returns:
        Formatted decimal string, or an empty string for non-finite values.
    """
    if value is None or not math.isfinite(value):
        return ""
    format_spec = f"{{:.{digits}f}}"
    if digits > 0:
        return format_spec.format(value)
    return str(round(value))


_CSV_HEADER = (
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
