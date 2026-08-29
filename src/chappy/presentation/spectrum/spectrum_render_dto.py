"""DTO assembly for model and residual spectrum rendering."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from chappy.presentation.spectrum.visual_tokens import component_curve_color

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

    from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
    from chappy.core.spectrum_model import SpectrumModel
    from chappy.presentation.spectrum.model_window_builder import ModelWindowBuilder


@dataclass(frozen=True, slots=True)
class SpectrumComponentCurve:
    """One absorber transmission curve ready for plotting."""

    component_id: str
    color: str
    wavelength: NDArray[np.float64]
    flux: NDArray[np.float64]
    emphasized: bool = False


@dataclass(frozen=True, slots=True)
class SpectrumRenderDTO:
    """Windowed data required to render optimize-mode model and residual curves."""

    windows: tuple[tuple[float, float], ...]
    model_wavelength: NDArray[np.float64] | None = None
    model_flux: NDArray[np.float64] | None = None
    residual_wavelength: NDArray[np.float64] | None = None
    residual_values: NDArray[np.float64] | None = None
    component_curves: tuple[SpectrumComponentCurve, ...] = field(default_factory=tuple)

    @property
    def has_model(self) -> bool:
        """Return True when model curve data is available."""
        return self.model_wavelength is not None and self.model_flux is not None

    @property
    def has_residual(self) -> bool:
        """Return True when residual curve data is available."""
        return self.residual_wavelength is not None and self.residual_values is not None


class SpectrumRenderProjectPort(Protocol):
    """Project state required to assemble spectrum render DTOs."""

    absorption_lines: dict[str, AbsorptionLine]

    @property
    def model(self) -> SpectrumModel:
        """Return the current spectrum model."""
        ...


class SpectrumRenderDTOAssembler:
    """Build render DTOs from project model state and selected region."""

    def __init__(self, windowing: ModelWindowBuilder) -> None:
        """Initialise the assembler.

        Args:
            windowing: Required window builder dependency.
        """
        self._windowing = windowing

    def build(
        self,
        project: SpectrumRenderProjectPort,
        region: AbsorptionRegion | None,
        *,
        include_component_curves: bool = False,
        emphasized_component_id: str | None = None,
    ) -> SpectrumRenderDTO:
        """Return windowed model, residual and optional per-component curve data."""
        windows = self._windowing.region_wavelength_windows(project.absorption_lines, region)
        if not windows:
            return SpectrumRenderDTO(windows=())

        model = project.model
        model_wavelength: NDArray[np.float64] | None = None
        model_flux: NDArray[np.float64] | None = None
        residual_wavelength: NDArray[np.float64] | None = None
        residual_values: NDArray[np.float64] | None = None

        if model.model_spectrum is not None:
            window_wavelength, window_flux = self._windowing.slice_data_to_windows(
                model.model_spectrum.wavelength, model.model_spectrum.flux, windows
            )
            if window_wavelength.size > 0:
                model_wavelength = window_wavelength
                model_flux = window_flux

        if model.residuals is not None and model.observed_spectrum is not None:
            window_wavelength, window_residuals = self._windowing.slice_data_to_windows(
                model.observed_spectrum.wavelength, model.residuals, windows
            )
            if window_wavelength.size > 0:
                residual_wavelength = window_wavelength
                residual_values = window_residuals

        component_curves: tuple[SpectrumComponentCurve, ...] = ()
        if include_component_curves:
            component_curves = self._build_component_curves(
                model, windows, emphasized_component_id
            )

        return SpectrumRenderDTO(
            windows=tuple(windows),
            model_wavelength=model_wavelength,
            model_flux=model_flux,
            residual_wavelength=residual_wavelength,
            residual_values=residual_values,
            component_curves=component_curves,
        )

    def _build_component_curves(
        self,
        model: SpectrumModel,
        windows: list[tuple[float, float]],
        emphasized_component_id: str | None,
    ) -> tuple[SpectrumComponentCurve, ...]:
        """Return windowed transmission curves for every enabled absorber."""
        if model.observed_spectrum is None:
            return ()

        grid = model.observed_spectrum.wavelength
        curves: list[SpectrumComponentCurve] = []
        for index, (component_id, flux) in enumerate(model.component_transmissions_on(grid)):
            window_wavelength, window_flux = self._windowing.slice_data_to_windows(
                grid, flux, windows
            )
            if window_wavelength.size == 0:
                continue
            curves.append(
                SpectrumComponentCurve(
                    component_id=component_id,
                    color=component_curve_color(index),
                    wavelength=window_wavelength,
                    flux=window_flux,
                    emphasized=component_id == emphasized_component_id,
                )
            )
        return tuple(curves)
