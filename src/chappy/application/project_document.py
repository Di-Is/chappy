"""Typed project document snapshots used at persistence boundaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from datetime import datetime

    import numpy as np
    from numpy.typing import NDArray

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]
type ComponentKind = Literal["absorber", "continuum"]


@dataclass(frozen=True, slots=True)
class SpectrumDocument:
    """Observed spectrum arrays and metadata."""

    wavelength: NDArray[np.float64]
    flux: NDArray[np.float64]
    error: NDArray[np.float64] | None
    header: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ParameterDocument:
    """Serializable model parameter snapshot."""

    name: str
    value: float
    min_val: float
    max_val: float
    fixed: bool
    error: float
    unit: str | None


@dataclass(frozen=True, slots=True)
class ComponentDocument:
    """Serializable spectral model component snapshot."""

    component_id: str
    kind: ComponentKind
    name: str
    enabled: bool
    parameters: tuple[ParameterDocument, ...] = ()
    wavelength: float | None = None
    oscillator_strength: float | None = None
    gamma: float | None = None
    group_id: str | None = None
    continuum_points: tuple[tuple[float, float], ...] = ()
    is_shared_with_absorption: bool = True


@dataclass(frozen=True, slots=True)
class MaskDocument:
    """Serializable wavelength mask snapshot."""

    identifier: str
    label: str
    mode: str
    start_wavelength: float | None
    end_wavelength: float | None
    center: float | None
    half_width: float | None
    note: str
    color: str | None
    enabled: bool
    group_id: str | None


@dataclass(frozen=True, slots=True)
class TieSharedParameterDocument:
    """Serializable shared parameter state for a parameter tie set."""

    name: str
    value: float
    fixed: bool


@dataclass(frozen=True, slots=True)
class TieSetDocument:
    """Serializable parameter tie set snapshot."""

    uid: str
    tie_id: str
    name: str
    origin: str
    mask: tuple[str, ...]
    component_ids: tuple[str, ...]
    member_uids: tuple[str, ...] = ()
    shared_parameters: tuple[TieSharedParameterDocument, ...] = ()


@dataclass(frozen=True, slots=True)
class AbsorptionRegionDocument:
    """Serializable absorption region snapshot."""

    region_id: str
    line_ids: tuple[str, ...]
    display_color: str
    analysis_range: tuple[float, float] | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AbsorptionLineDocument:
    """Serializable absorption line snapshot."""

    line_id: str
    species: str
    rest_wavelength: float
    center_z: float
    window_kms: float
    multiplet_label: str
    transition_name: str
    oscillator_strength: float
    gamma_value: float
    lambda_range: tuple[float, float] | None
    region_id: str | None
    multiplet_ids: tuple[str, ...]
    model_ids: tuple[str, ...]
    needs_optimization: bool
    created_by: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class FitSummaryDocument:
    """Serializable numerical evidence from one successful fit."""

    chi_squared: float | None
    reduced_chi_squared: float | None
    degrees_of_freedom: float | None
    n_parameters: int | None
    n_function_evaluations: int | None
    outcome: str | None


@dataclass(frozen=True, slots=True)
class AnalysisArtifactDocument:
    """Serializable fit evidence tied to one region input revision."""

    region_id: str
    source_revision: int
    fit_summary: FitSummaryDocument


@dataclass(frozen=True, slots=True)
class RegionAnalysisStateDocument:
    """Serializable project-owned analysis state for one region."""

    region_id: str
    current_revision: int
    artifact: AnalysisArtifactDocument | None


@dataclass(frozen=True, slots=True)
class IdentifyStateDocument:
    """Serializable identify-mode session state."""

    work_phase: str
    reference_z: float
    last_added_wavelength: float | None
    last_click_wavelength: float | None


@dataclass(frozen=True, slots=True)
class ProjectDocument:
    """Complete project document snapshot for persistence."""

    name: str
    spectrum_filename: str | None
    created: datetime
    modified: datetime
    metadata: JsonObject
    settings: JsonObject
    spectrum: SpectrumDocument | None
    components: tuple[ComponentDocument, ...]
    masks: tuple[MaskDocument, ...]
    fit_wavelength_range: tuple[float, float] | None
    tie_sets: tuple[TieSetDocument, ...]
    absorption_regions: tuple[AbsorptionRegionDocument, ...]
    absorption_lines: tuple[AbsorptionLineDocument, ...]
    analysis_states: tuple[RegionAnalysisStateDocument, ...]
    identify_state: IdentifyStateDocument
