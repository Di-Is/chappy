"""Presentation view models and pure transforms for velocity views."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol

from chappy.core.constants import LIGHT_SPEED_KMS
from chappy.presentation.spectrum import (
    DEFAULT_SPECTRUM_DISPLAY_OPTIONS,
    SpectrumDisplayOptions,
    component_curve_color,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    import numpy as np
    from numpy.typing import NDArray

    from chappy.core.absorption.models import AbsorptionLine
    from chappy.core.components.absorber import AbsorberComponent
    from chappy.core.spectrum_model import SpectrumModel

type VelocityUnit = Literal["km/s", "m/s"]


@dataclass(slots=True)
class VelocitySliceParams:
    """Parameters describing a velocity slice transformation."""

    rest_wavelength: float
    center_redshift: float
    display_half_width_kms: float
    unit: VelocityUnit = "km/s"


@dataclass(slots=True)
class VelocityComponentInfo:
    """Information about a component in velocity space."""

    component_id: str
    velocity: float
    rest_wavelength: float
    label: str
    tie_label: str | None = None


@dataclass(frozen=True, slots=True)
class VelocityMaskRegionInfo:
    """Mask region already transformed into velocity-space coordinates."""

    velocity_min: float
    velocity_max: float
    color: str


@dataclass(frozen=True, slots=True)
class VelocityCenterLineInfo:
    """Center-line marker already transformed into velocity-space coordinates."""

    velocity: float
    color: str
    label: str


@dataclass(slots=True)
class VelocitySliceInfo:
    """Descriptor for an individual velocity subplot."""

    rest_wavelength: float
    label: str
    tie_group_key: str
    center_z: float | None = None
    line_id: str | None = None
    region_id: str | None = None
    is_primary: bool = False
    default_selected: bool = False
    selected: bool | None = None
    analysis_half_width_kms: float | None = None
    components: list[VelocityComponentInfo] = field(default_factory=list)
    mask_regions: list[VelocityMaskRegionInfo] = field(default_factory=list)
    center_lines: list[VelocityCenterLineInfo] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate the optional scientific analysis half-width."""
        if self.analysis_half_width_kms is not None:
            value = float(self.analysis_half_width_kms)
            if not math.isfinite(value) or value <= 0.0:
                msg = "Analysis half-width must be finite and positive."
                raise ValueError(msg)
            self.analysis_half_width_kms = value


@dataclass(frozen=True, slots=True)
class VelocitySpectrumData:
    """Spectrum arrays required by the velocity view."""

    wavelength: NDArray[np.float64]
    flux: NDArray[np.float64]
    error: NDArray[np.float64] | None = None


@dataclass(frozen=True, slots=True)
class VelocityComponentProfile:
    """One absorber transmission curve on the observed wavelength grid."""

    component_id: str
    color: str
    emphasized: bool
    spectrum: VelocitySpectrumData


@dataclass(frozen=True, slots=True)
class VelocityViewData:
    """Complete non-Qt data package consumed by the velocity view."""

    observed: VelocitySpectrumData | None
    model: VelocitySpectrumData | None
    slices: tuple[VelocitySliceInfo, ...]
    selection_scope_key: str | None = None
    component_profiles: tuple[VelocityComponentProfile, ...] = ()
    show_error_spectrum: bool = True


class VelocityViewProjectPort(Protocol):
    """Project state required to build velocity view data."""

    @property
    def model(self) -> SpectrumModel:
        """Return the current spectrum model."""
        ...

    def find_absorption_line(self, line_id: str) -> AbsorptionLine | None:
        """Return an absorption line by ID."""
        ...

    def find_absorber_component(self, component_id: str) -> AbsorberComponent | None:
        """Return an absorber component by ID."""
        ...

    def find_lines_for_region(self, region_id: str) -> list[AbsorptionLine] | None:
        """Return absorption lines assigned to a region."""
        ...


def build_velocity_view_data(
    project: VelocityViewProjectPort | None,
    slices: Iterable[VelocitySliceInfo],
    *,
    selection_scope_key: str | None = None,
    display_half_width_kms: float,
    include_optimize_overlays: bool,
    tie_label_resolver: Callable[[AbsorberComponent], str | None] | None = None,
    display_options: SpectrumDisplayOptions = DEFAULT_SPECTRUM_DISPLAY_OPTIONS,
    emphasized_component_id: str | None = None,
) -> VelocityViewData:
    """Build velocity view data without exposing project lookup to the view."""
    source_slices = tuple(slices)
    if project is None:
        return VelocityViewData(
            selection_scope_key=selection_scope_key,
            observed=None,
            model=None,
            slices=source_slices,
            show_error_spectrum=display_options.show_error_spectrum,
        )

    observed_spectrum = project.model.observed_spectrum
    model_spectrum = project.model.model_spectrum
    observed = (
        VelocitySpectrumData(
            wavelength=observed_spectrum.wavelength,
            flux=observed_spectrum.flux,
            error=observed_spectrum.error,
        )
        if observed_spectrum is not None
        else None
    )
    model = (
        VelocitySpectrumData(
            wavelength=model_spectrum.wavelength, flux=model_spectrum.flux, error=None
        )
        if model_spectrum is not None
        else None
    )

    enriched_slices = tuple(
        _enrich_slice(
            project,
            slice_info,
            display_half_width_kms=display_half_width_kms,
            include_optimize_overlays=include_optimize_overlays,
            tie_label_resolver=tie_label_resolver,
        )
        for slice_info in source_slices
    )
    component_profiles: tuple[VelocityComponentProfile, ...] = ()
    if display_options.show_component_profiles and observed_spectrum is not None:
        component_profiles = _build_component_profiles(
            project, observed_spectrum.wavelength, emphasized_component_id
        )

    return VelocityViewData(
        selection_scope_key=selection_scope_key,
        observed=observed,
        model=model,
        slices=enriched_slices,
        component_profiles=component_profiles,
        show_error_spectrum=display_options.show_error_spectrum,
    )


def _build_component_profiles(
    project: VelocityViewProjectPort,
    wavelength: NDArray[np.float64],
    emphasized_component_id: str | None,
) -> tuple[VelocityComponentProfile, ...]:
    """Return one transmission curve per enabled absorber on the observed grid."""
    return tuple(
        VelocityComponentProfile(
            component_id=component_id,
            color=component_curve_color(index),
            emphasized=component_id == emphasized_component_id,
            spectrum=VelocitySpectrumData(wavelength=wavelength, flux=flux, error=None),
        )
        for index, (component_id, flux) in enumerate(
            project.model.component_transmissions_on(wavelength)
        )
    )


def _enrich_slice(
    project: VelocityViewProjectPort,
    slice_info: VelocitySliceInfo,
    *,
    display_half_width_kms: float,
    include_optimize_overlays: bool,
    tie_label_resolver: Callable[[AbsorberComponent], str | None] | None = None,
) -> VelocitySliceInfo:
    """Return a slice enriched with project-derived velocity metadata."""
    components = _build_components_for_line(project, slice_info, tie_label_resolver)
    if not include_optimize_overlays:
        return _replace_slice_metadata(
            slice_info, components=components, mask_regions=[], center_lines=[]
        )

    return _replace_slice_metadata(
        slice_info,
        components=components,
        mask_regions=_build_mask_regions(project, slice_info, display_half_width_kms),
        center_lines=_build_center_lines(project, slice_info, display_half_width_kms),
    )


def _replace_slice_metadata(
    slice_info: VelocitySliceInfo,
    *,
    components: list[VelocityComponentInfo],
    mask_regions: list[VelocityMaskRegionInfo],
    center_lines: list[VelocityCenterLineInfo],
) -> VelocitySliceInfo:
    """Copy a slice while replacing project-derived rendering metadata."""
    return VelocitySliceInfo(
        rest_wavelength=slice_info.rest_wavelength,
        label=slice_info.label,
        center_z=slice_info.center_z,
        line_id=slice_info.line_id,
        region_id=slice_info.region_id,
        is_primary=slice_info.is_primary,
        default_selected=slice_info.default_selected,
        selected=slice_info.selected,
        tie_group_key=slice_info.tie_group_key,
        analysis_half_width_kms=slice_info.analysis_half_width_kms,
        components=components,
        mask_regions=mask_regions,
        center_lines=center_lines,
    )


def _build_components_for_line(
    project: VelocityViewProjectPort,
    slice_info: VelocitySliceInfo,
    tie_label_resolver: Callable[[AbsorberComponent], str | None] | None = None,
) -> list[VelocityComponentInfo]:
    """Build velocity component metadata for a slice line."""
    if not slice_info.line_id or slice_info.center_z is None:
        return list(slice_info.components)

    line = project.find_absorption_line(slice_info.line_id)
    if line is None or not line.model_ids:
        return list(slice_info.components)

    components: list[VelocityComponentInfo] = []
    for model_id in line.model_ids:
        component = project.find_absorber_component(model_id)
        if component is None:
            continue
        z_comp = component.parameters["redshift"].value
        velocity = LIGHT_SPEED_KMS * (z_comp - slice_info.center_z) / (1.0 + slice_info.center_z)
        tie_label = tie_label_resolver(component) if tie_label_resolver is not None else None
        components.append(
            VelocityComponentInfo(
                component_id=component.id,
                velocity=velocity,
                rest_wavelength=slice_info.rest_wavelength,
                label=component.name,
                tie_label=tie_label,
            )
        )
    return components


def _build_mask_regions(
    project: VelocityViewProjectPort, slice_info: VelocitySliceInfo, window: float
) -> list[VelocityMaskRegionInfo]:
    """Build velocity-space mask regions for a slice."""
    if slice_info.center_z is None:
        return []

    rest_observed = slice_info.rest_wavelength * (1.0 + slice_info.center_z)
    window_limit = abs(window)
    regions: list[VelocityMaskRegionInfo] = []
    for mask in project.model.mask_definitions:
        if not mask.enabled:
            continue
        velocity_min = (mask.wavelength_min / rest_observed - 1.0) * LIGHT_SPEED_KMS
        velocity_max = (mask.wavelength_max / rest_observed - 1.0) * LIGHT_SPEED_KMS
        if velocity_max < -window_limit or velocity_min > window_limit:
            continue
        regions.append(
            VelocityMaskRegionInfo(
                velocity_min=max(velocity_min, -window_limit),
                velocity_max=min(velocity_max, window_limit),
                color=mask.color or "#808080",
            )
        )
    return regions


def _build_center_lines(
    project: VelocityViewProjectPort, slice_info: VelocitySliceInfo, window: float
) -> list[VelocityCenterLineInfo]:
    """Build velocity-space center lines for all region components."""
    if slice_info.center_z is None or slice_info.region_id is None:
        return []

    lines = project.find_lines_for_region(slice_info.region_id) or []
    if not lines:
        return []

    ref_observed = slice_info.rest_wavelength * (1.0 + slice_info.center_z)
    center_lines: list[VelocityCenterLineInfo] = []
    for line in lines:
        if not line.model_ids:
            continue
        color = "yellow" if line.line_id == slice_info.line_id else "orange"
        for model_id in line.model_ids:
            component = project.find_absorber_component(model_id)
            if component is None:
                continue
            redshift_param = component.parameters.get("redshift")
            if redshift_param is None:
                continue
            component_observed = component.wavelength * (1.0 + redshift_param.value)
            velocity = LIGHT_SPEED_KMS * (component_observed / ref_observed - 1.0)
            if abs(velocity) <= window:
                center_lines.append(
                    VelocityCenterLineInfo(
                        velocity=velocity, color=color, label=line.transition_name
                    )
                )
    return center_lines
