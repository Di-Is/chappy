"""Build typed render inputs for velocity subplots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from chappy.presentation.velocity.display_range import (
    VelocityAnalysisBounds,
    VelocityDisplayHalfWidth,
)
from chappy.presentation.velocity.selection_model import resolve_velocity_slice_selection
from chappy.presentation.velocity.transforms import compute_residual, compute_velocity_slice
from chappy.presentation.velocity.view_model import (
    VelocityCenterLineInfo,
    VelocityComponentInfo,
    VelocityComponentProfile,
    VelocityMaskRegionInfo,
    VelocitySliceInfo,
    VelocitySliceParams,
    VelocitySpectrumData,
    VelocityUnit,
)

type VelocitySliceRenderFailureReason = Literal[
    "no_spectrum", "no_slices", "no_lines", "no_samples", "conversion_failed"
]


@dataclass(frozen=True, slots=True)
class VelocitySliceRenderFailure:
    """Placeholder state for a velocity subplot."""

    kind: Literal["failure"]
    reason: VelocitySliceRenderFailureReason
    title: str
    primary: bool
    selected: bool
    selection_enabled: bool
    components: tuple[VelocityComponentInfo, ...]


@dataclass(frozen=True, slots=True)
class VelocityCurveSources:
    """Spectra and display toggles shared by every subplot of one velocity refresh."""

    observed: VelocitySpectrumData | None
    model: VelocitySpectrumData | None = None
    component_profiles: tuple[VelocityComponentProfile, ...] = ()
    show_error_spectrum: bool = True


@dataclass(frozen=True, slots=True)
class VelocityComponentProfileCurve:
    """One absorber transmission curve already converted into velocity space."""

    component_id: str
    color: str
    emphasized: bool
    velocity: tuple[float, ...]
    flux: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class VelocitySliceRenderData:
    """Fully prepared render input for a velocity subplot."""

    kind: Literal["data"]
    title: str
    primary: bool
    selected: bool
    selection_enabled: bool
    components: tuple[VelocityComponentInfo, ...]
    observed_velocity: tuple[float, ...]
    observed_flux: tuple[float, ...]
    observed_error: tuple[float, ...] | None
    display_half_width_kms: float
    analysis_bounds: VelocityAnalysisBounds | None
    analysis_out_of_view: bool
    model_velocity: tuple[float, ...] | None
    model_flux: tuple[float, ...] | None
    residual: tuple[float, ...] | None
    mask_regions: tuple[VelocityMaskRegionInfo, ...]
    center_lines: tuple[VelocityCenterLineInfo, ...]
    component_markers: tuple[VelocityComponentInfo, ...]
    component_profile_curves: tuple[VelocityComponentProfileCurve, ...] = ()


type VelocitySliceRenderInput = VelocitySliceRenderData | VelocitySliceRenderFailure


def build_velocity_slot_render_input(
    slice_info: VelocitySliceInfo | None,
    *,
    default_title: str,
    sources: VelocityCurveSources,
    display_half_width: VelocityDisplayHalfWidth,
    unit: VelocityUnit,
    optimize_mode: bool,
    empty_reason: Literal["no_lines", "no_slices"],
) -> VelocitySliceRenderInput:
    """Build a typed render input for a subplot slot."""
    if slice_info is None:
        return VelocitySliceRenderFailure(
            kind="failure",
            reason=empty_reason,
            title=default_title,
            primary=False,
            selected=False,
            selection_enabled=False,
            components=(),
        )

    return build_velocity_slice_render_input(
        slice_info,
        sources=sources,
        display_half_width=display_half_width,
        unit=unit,
        optimize_mode=optimize_mode,
    )


def build_velocity_slice_render_input(
    slice_info: VelocitySliceInfo,
    *,
    sources: VelocityCurveSources,
    display_half_width: VelocityDisplayHalfWidth,
    unit: VelocityUnit,
    optimize_mode: bool,
) -> VelocitySliceRenderInput:
    """Build a typed render input for a single velocity slice."""
    observed = sources.observed
    model = sources.model
    title = slice_info.label
    primary = slice_info.is_primary
    selected = resolve_velocity_slice_selection(slice_info)
    components = tuple(slice_info.components)

    if observed is None:
        return VelocitySliceRenderFailure(
            kind="failure",
            reason="no_spectrum",
            title=title,
            primary=primary,
            selected=selected,
            selection_enabled=False,
            components=components,
        )

    if slice_info.center_z is None:
        return VelocitySliceRenderFailure(
            kind="failure",
            reason="no_lines",
            title=title,
            primary=primary,
            selected=selected,
            selection_enabled=True,
            components=components,
        )

    display_half_width_kms = display_half_width.value
    if optimize_mode and slice_info.analysis_half_width_kms is None:
        msg = "Optimize velocity slices require an analysis half-width."
        raise ValueError(msg)
    analysis_bounds: VelocityAnalysisBounds | None = None
    if slice_info.analysis_half_width_kms is not None:
        analysis_bounds = VelocityAnalysisBounds.from_half_width(
            slice_info.analysis_half_width_kms
        )
    params = VelocitySliceParams(
        rest_wavelength=slice_info.rest_wavelength,
        center_redshift=slice_info.center_z,
        display_half_width_kms=display_half_width_kms,
        unit=unit,
    )

    try:
        observed_velocity, observed_flux, observed_error = compute_velocity_slice(
            observed.wavelength, observed.flux, observed.error, params
        )
    except ValueError:
        return VelocitySliceRenderFailure(
            kind="failure",
            reason="conversion_failed",
            title=title,
            primary=primary,
            selected=selected,
            selection_enabled=True,
            components=components,
        )

    if observed_velocity.size == 0:
        return VelocitySliceRenderFailure(
            kind="failure",
            reason="no_samples",
            title=title,
            primary=primary,
            selected=selected,
            selection_enabled=True,
            components=components,
        )

    model_velocity: tuple[float, ...] | None = None
    model_flux: tuple[float, ...] | None = None
    residual: tuple[float, ...] | None = None
    if model is not None:
        try:
            velocity_model, flux_model, _ = compute_velocity_slice(
                model.wavelength, model.flux, None, params
            )
        except ValueError:
            velocity_model = None
            flux_model = None
        if velocity_model is not None and flux_model is not None and velocity_model.size > 0:
            model_velocity = tuple(float(value) for value in velocity_model.tolist())
            model_flux = tuple(float(value) for value in flux_model.tolist())
            if optimize_mode:
                try:
                    residual_array = compute_residual(
                        observed_velocity, observed_flux, velocity_model, flux_model
                    )
                except ValueError:
                    residual = None
                else:
                    residual = tuple(float(value) for value in residual_array.tolist())

    return VelocitySliceRenderData(
        kind="data",
        title=title,
        primary=primary,
        selected=selected,
        selection_enabled=True,
        components=components,
        observed_velocity=tuple(float(value) for value in observed_velocity.tolist()),
        observed_flux=tuple(float(value) for value in observed_flux.tolist()),
        observed_error=(
            tuple(float(value) for value in observed_error.tolist())
            if observed_error is not None and sources.show_error_spectrum
            else None
        ),
        display_half_width_kms=display_half_width_kms,
        analysis_bounds=analysis_bounds,
        analysis_out_of_view=(
            analysis_bounds is not None and analysis_bounds.half_width_kms > display_half_width_kms
        ),
        model_velocity=model_velocity,
        model_flux=model_flux,
        residual=residual,
        mask_regions=tuple(slice_info.mask_regions) if optimize_mode else (),
        center_lines=tuple(slice_info.center_lines) if optimize_mode else (),
        component_markers=components if optimize_mode else (),
        component_profile_curves=_build_component_profile_curves(
            sources.component_profiles, params
        ),
    )


def _build_component_profile_curves(
    component_profiles: tuple[VelocityComponentProfile, ...], params: VelocitySliceParams
) -> tuple[VelocityComponentProfileCurve, ...]:
    """Convert each absorber transmission curve into this slice's velocity space."""
    curves: list[VelocityComponentProfileCurve] = []
    for component_profile in component_profiles:
        spectrum = component_profile.spectrum
        try:
            velocity, flux, _ = compute_velocity_slice(
                spectrum.wavelength, spectrum.flux, None, params
            )
        except ValueError:
            continue
        if velocity.size == 0:
            continue
        curves.append(
            VelocityComponentProfileCurve(
                component_id=component_profile.component_id,
                color=component_profile.color,
                emphasized=component_profile.emphasized,
                velocity=tuple(float(value) for value in velocity.tolist()),
                flux=tuple(float(value) for value in flux.tolist()),
            )
        )
    return tuple(curves)
