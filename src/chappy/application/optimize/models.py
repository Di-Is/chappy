"""Typed models for optimize workflow use cases."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chappy.application.history.ports import LineOptimizationStateSnapshot
    from chappy.core.analysis import FitSummary
    from chappy.core.components.absorber import AbsorberComponent
    from chappy.core.components.tie_set import ParameterTieSet
    from chappy.core.velocity_ranges import LineAnalysisHalfWidth


@dataclass(frozen=True, slots=True)
class CosmologyParametersSnapshot:
    """Cosmology values used to derive export quantities."""

    h0: float
    omega_m: float
    omega_lambda: float
    omega_k: float = 0.0


@dataclass(frozen=True, slots=True)
class OptimizationExportLine:
    """One normalized line/component row input for optimization export."""

    region_name: str
    line_display_id: int
    component_display_id: int
    redshift: float
    redshift_error: float | None
    column_density: float
    column_density_error: float | None
    b_parameter: float
    b_parameter_error: float | None
    covering_factor: float
    covering_factor_error: float | None
    line_species: str
    model_label: str
    rest_wavelength: float
    oscillator_strength: float
    gamma_value: float
    multiplet_label: str


@dataclass(frozen=True, slots=True)
class OptimizationExportRequest:
    """Request for building an optimization CSV document."""

    project_name: str
    region_id: str
    region_name: str
    lines: tuple[OptimizationExportLine, ...]
    analysis_range: tuple[float, float] | None
    cosmology: CosmologyParametersSnapshot
    fit_summary: FitSummary


@dataclass(frozen=True, slots=True)
class OptimizationExportDocument:
    """CSV document generated from optimization results."""

    filename_stem: str
    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


class FitResultStatusKind(StrEnum):
    """Status kind for fit result application."""

    CHI2 = "chi2"
    COMPLETE = "complete"
    CUSTOM = "custom"
    FAILED = "failed"


class FitWorkflowStatusKind(StrEnum):
    """Status kind consumed by the fit workflow view port."""

    READY = "ready"
    RUNNING = "running"
    CHI2 = "chi2"
    COMPLETE = "complete"
    FAILED = "failed"
    CUSTOM = "custom"


type FitResultRawValue = bool | int | float | str | None
type FitResultRawPayload = Mapping[str, FitResultRawValue]


@dataclass(frozen=True, slots=True)
class FitResultPayload:
    """Normalized optimizer result payload."""

    success: bool
    message: str | None = None
    outcome: str | None = None
    chi_squared: float | None = None
    reduced_chi_squared: float | None = None
    n_parameters: int | None = None
    n_function_evaluations: int | None = None


@dataclass(frozen=True, slots=True)
class FitWorkflowStatus:
    """Status payload passed from fit workflow to the panel."""

    kind: FitWorkflowStatusKind
    value: float | None = None
    reduced_value: float | None = None
    message: str | None = None


@dataclass(frozen=True, slots=True)
class FitResultApplication:
    """Decision produced after applying a fit result payload."""

    status_kind: FitResultStatusKind
    status_value: float | None
    reduced_status_value: float | None
    raw_message: str | None
    summary: FitSummary | None
    analysis_ready: bool
    outcome: str | None = None


@dataclass(frozen=True, slots=True)
class ParameterStateSnapshot:
    """Typed snapshot of one model parameter state."""

    name: str
    value: float
    fixed: bool
    error: float


@dataclass(frozen=True, slots=True)
class ComponentParameterSnapshot:
    """Typed snapshot of one absorber component parameter set."""

    component_id: str
    parameters: tuple[ParameterStateSnapshot, ...]


@dataclass(frozen=True, slots=True)
class LineOptimizationInputSnapshot:
    """Typed input snapshot of one absorption line optimization flag."""

    line_id: str
    region_id: str | None
    needs_optimization: bool


@dataclass(frozen=True, slots=True)
class OptimizeHistorySnapshot:
    """Typed snapshot used before or after optimize fitting."""

    component_states: tuple[ComponentParameterSnapshot, ...]
    line_optimization_states: tuple[LineOptimizationStateSnapshot, ...]


@dataclass(frozen=True, slots=True)
class ModelAdditionRequest:
    """Request to create absorber model components for one absorption line."""

    redshift: float
    column_density: float
    b_parameter: float
    covering_factor: float


@dataclass(frozen=True, slots=True)
class ModelAdditionResult:
    """Result of adding absorber model components to a project."""

    components_by_line_id: dict[str, AbsorberComponent]
    tie_sets: tuple[ParameterTieSet, ...]


class LineAnalysisHalfWidthRejectionReason(StrEnum):
    """User-correctable reasons an analysis half-width edit is rejected."""

    INVALID_NUMBER = "invalid_number"
    OUTSIDE_SUPPORTED_RANGE = "outside_supported_range"
    LINE_NOT_FOUND = "line_not_found"
    COMPONENT_OUTSIDE_SUPPORTED_RANGE = "component_outside_supported_range"


class LineAnalysisHalfWidthNoChangeReason(StrEnum):
    """Reasons a valid analysis half-width request produces no mutation."""

    ALREADY_EQUAL = "already_equal"
    ALREADY_AT_REQUIRED_MINIMUM = "already_at_required_minimum"


class LineAnalysisHalfWidthInvariantKind(StrEnum):
    """Kinds of invalid project state detected before an edit transaction."""

    MISSING_COMPONENT = "missing_component"
    MISSING_COMPONENT_REDSHIFT = "missing_component_redshift"
    NONFINITE_COMPONENT_REDSHIFT = "nonfinite_component_redshift"


class LineAnalysisHalfWidthInvariantViolation(RuntimeError):  # noqa: N818
    """Fail-fast error for inconsistent line-to-component project state."""

    def __init__(
        self, kind: LineAnalysisHalfWidthInvariantKind, line_id: str, component_id: str
    ) -> None:
        """Initialize the typed invariant violation."""
        super().__init__(f"{kind.value}: line={line_id}, component={component_id}")
        self.kind = kind
        self.line_id = line_id
        self.component_id = component_id


@dataclass(frozen=True, slots=True)
class LineAnalysisHalfWidthEditRequest:
    """Request to edit one line or linked multiplet analysis half-width."""

    line_id: str
    requested_half_width: float


@dataclass(frozen=True, slots=True)
class LineAnalysisHalfWidthApplied:
    """Outcome for an edit applied exactly as requested."""

    requested: float
    applied: LineAnalysisHalfWidth
    affected_line_ids: tuple[str, ...]
    region_id: str


@dataclass(frozen=True, slots=True)
class LineAnalysisHalfWidthAdjusted:
    """Outcome for an edit widened to contain all model centers."""

    requested: float
    applied_minimum: LineAnalysisHalfWidth
    affected_line_ids: tuple[str, ...]
    constraining_component_ids: tuple[str, ...]
    region_id: str


@dataclass(frozen=True, slots=True)
class LineAnalysisHalfWidthNoChange:
    """Outcome for a valid edit whose derived project state is unchanged."""

    requested: float
    retained: LineAnalysisHalfWidth
    reason: LineAnalysisHalfWidthNoChangeReason
    affected_line_ids: tuple[str, ...]
    constraining_component_ids: tuple[str, ...]
    region_id: str


@dataclass(frozen=True, slots=True)
class LineAnalysisHalfWidthRejected:
    """Outcome for a user-correctable rejected edit."""

    reason: LineAnalysisHalfWidthRejectionReason
    requested: float
    supported_minimum: float
    supported_maximum: float


type LineAnalysisHalfWidthEditOutcome = (
    LineAnalysisHalfWidthApplied
    | LineAnalysisHalfWidthAdjusted
    | LineAnalysisHalfWidthNoChange
    | LineAnalysisHalfWidthRejected
)


@dataclass(frozen=True, slots=True)
class LineAnalysisHalfWidthLineChange:
    """Before/after scientific range state for one affected line."""

    line_id: str
    before_half_width: float
    after_half_width: LineAnalysisHalfWidth
    before_lambda_range: tuple[float, float] | None
    after_lambda_range: tuple[float, float]


@dataclass(frozen=True, slots=True)
class PreparedLineAnalysisHalfWidthChange:
    """Complete mutation payload committed through one transaction port call."""

    seed_line_id: str
    region_id: str
    line_changes: tuple[LineAnalysisHalfWidthLineChange, ...]
    region_line_ids: tuple[str, ...]
    before_region_analysis_range: tuple[float, float] | None
    after_region_analysis_range: tuple[float, float]
