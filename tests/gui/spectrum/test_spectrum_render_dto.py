"""Tests for spectrum model windowing and render DTO assembly."""

from __future__ import annotations

from typing import cast

import numpy as np
import pytest
from numpy.testing import assert_allclose

from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.core.spectrum import Spectrum
from chappy.presentation.spectrum import (
    ModelWindowBuilder,
    SpectrumRenderDTOAssembler,
    component_curve_color,
)


def _line(line_id: str, lambda_range: tuple[float, float]) -> AbsorptionLine:
    """Create a typed absorption line for windowing tests."""
    return AbsorptionLine(
        line_id=line_id,
        species="H I",
        rest_wavelength=1215.67,
        center_z=0.0,
        window_kms=200.0,
        multiplet_label="LyA",
        transition_name="Lyα",
        oscillator_strength=0.4164,
        gamma_value=6.265e8,
        lambda_range=lambda_range,
    )


def test_model_windowing_merges_and_clips_region_windows() -> None:
    """ModelWindowBuilder should merge line ranges and clip to analysis range."""
    lines_by_id = {"a": _line("a", (1000.0, 1010.0)), "b": _line("b", (1008.0, 1020.0))}
    region = AbsorptionRegion(
        region_id="region", line_ids=["a", "b"], analysis_range=(1005.0, 1015.0)
    )

    windows = ModelWindowBuilder().region_wavelength_windows(lines_by_id, region)

    assert windows == [(1005.0, 1015.0)]


def test_model_windowing_allows_missing_region_as_empty() -> None:
    """A missing selected region is a valid empty render window."""
    windows = ModelWindowBuilder().region_wavelength_windows({}, None)

    assert windows == []


def test_model_windowing_rejects_malformed_analysis_range() -> None:
    """Malformed presentation snapshots should not become empty render windows."""
    region = AbsorptionRegion(
        region_id="region", line_ids=(), analysis_range=cast(tuple[float, float], ("bad", 1015.0))
    )

    with pytest.raises(ValueError, match="could not convert"):
        ModelWindowBuilder().region_wavelength_windows({}, region)


def test_model_windowing_rejects_malformed_line_lambda_range() -> None:
    """Malformed line windows should fail instead of falling back to derived bounds."""
    lines_by_id = {"a": _line("a", cast(tuple[float, float], ("bad", 1010.0)))}
    region = AbsorptionRegion(region_id="region", line_ids=["a"])

    with pytest.raises(ValueError, match="could not convert"):
        ModelWindowBuilder().region_wavelength_windows(lines_by_id, region)


def test_spectrum_render_dto_assembler_slices_model_and_residuals() -> None:
    """Assembler should return windowed model and residual arrays."""
    project = SpectroscopyProject()
    project.absorption_lines["a"] = _line("a", (1001.0, 1003.0))
    region = AbsorptionRegion(region_id="region", line_ids=["a"])
    wavelength = np.array([1000.0, 1001.0, 1002.0, 1003.0, 1004.0])

    project.model.observed_spectrum = Spectrum(
        wavelength=wavelength, flux=np.array([1.0, 0.9, 0.8, 0.9, 1.0])
    )
    project.model.model_spectrum = Spectrum(
        wavelength=wavelength, flux=np.array([1.0, 0.95, 0.85, 0.95, 1.0])
    )
    project.model._residuals = np.array([0.0, -0.05, -0.05, -0.05, 0.0])

    dto = SpectrumRenderDTOAssembler(ModelWindowBuilder()).build(project, region)

    assert dto.windows == ((1001.0, 1003.0),)
    assert dto.has_model
    assert dto.has_residual
    assert dto.model_wavelength is not None
    assert dto.model_flux is not None
    assert dto.residual_values is not None
    assert_allclose(dto.model_wavelength, [1001.0, 1002.0, 1003.0])
    assert_allclose(dto.model_flux, [0.95, 0.85, 0.95])
    assert_allclose(dto.residual_values, [-0.05, -0.05, -0.05])


def _project_with_absorbers() -> tuple[SpectroscopyProject, AbsorptionRegion]:
    """Create a project whose region window holds two enabled absorbers."""
    project = SpectroscopyProject()
    project.absorption_lines["a"] = _line("a", (1000.0, 1005.0))
    region = AbsorptionRegion(region_id="region", line_ids=["a"])
    wavelength = np.linspace(999.0, 1006.0, 200)
    project.model.observed_spectrum = Spectrum(
        wavelength=wavelength, flux=np.ones_like(wavelength)
    )
    project.model.components.extend(
        [
            AbsorberComponent(component_id="abs-1", wavelength=1001.0, column_density=13.5),
            AbsorberComponent(component_id="abs-2", wavelength=1003.0, column_density=13.8),
        ]
    )
    return project, region


def test_render_dto_omits_component_curves_unless_requested() -> None:
    """Component curves cost a model evaluation, so they stay off by default."""
    project, region = _project_with_absorbers()

    dto = SpectrumRenderDTOAssembler(ModelWindowBuilder()).build(project, region)

    assert dto.component_curves == ()


def test_render_dto_windows_component_curves_with_identity_colors() -> None:
    """Requested component curves are windowed and coloured by component order."""
    project, region = _project_with_absorbers()

    dto = SpectrumRenderDTOAssembler(ModelWindowBuilder()).build(
        project, region, include_component_curves=True
    )

    assert [curve.component_id for curve in dto.component_curves] == ["abs-1", "abs-2"]
    assert [curve.color for curve in dto.component_curves] == [
        component_curve_color(0),
        component_curve_color(1),
    ]
    for curve in dto.component_curves:
        assert curve.wavelength.min() >= 1000.0
        assert curve.wavelength.max() <= 1005.0
        assert curve.flux.shape == curve.wavelength.shape
        assert not curve.emphasized
    assert dto.component_curves[0].flux.min() < 0.9


def test_render_dto_marks_only_the_emphasized_component_curve() -> None:
    """The selected component is the one drawn with emphasis."""
    project, region = _project_with_absorbers()

    dto = SpectrumRenderDTOAssembler(ModelWindowBuilder()).build(
        project, region, include_component_curves=True, emphasized_component_id="abs-2"
    )

    assert [curve.emphasized for curve in dto.component_curves] == [False, True]
