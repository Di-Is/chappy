"""Qt-free input DTOs for Region Detail presentation decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


@dataclass(frozen=True, slots=True)
class FitReadyView:
    """Fit workflow is idle and ready to start."""


@dataclass(frozen=True, slots=True)
class FitRunningView:
    """A fit is currently executing."""


@dataclass(frozen=True, slots=True)
class FitChi2View:
    """Fit completed and produced a chi-squared statistic."""

    chi2: float
    reduced: float | None


@dataclass(frozen=True, slots=True)
class FitCompleteView:
    """Fit completed without a chi-squared statistic."""


@dataclass(frozen=True, slots=True)
class FitFailedView:
    """Fit failed without an application-supplied message.

    A message-less failure is a legitimate FAILED status; no field is
    fabricated to hold an empty string.
    """


@dataclass(frozen=True, slots=True)
class FitCustomView:
    """Fit produced an application-supplied status message."""

    message: str


type FitStatusView = (
    FitReadyView | FitRunningView | FitChi2View | FitCompleteView | FitFailedView | FitCustomView
)


@dataclass(frozen=True, slots=True)
class HalfWidthAppliedView:
    """A half-width edit was applied exactly as requested."""

    applied: float
    affected_count: int


@dataclass(frozen=True, slots=True)
class HalfWidthAdjustedView:
    """A half-width edit was widened to include all model centers."""

    requested: float
    applied: float
    affected_count: int


@dataclass(frozen=True, slots=True)
class HalfWidthRetainedView:
    """A valid half-width edit produced no change to the derived state."""

    requested: float
    retained: float
    already_equal: bool


class HalfWidthRejectionReason(Enum):
    """Distinguishes the two rejection messages the panel can show."""

    COMPONENT_OUTSIDE_SUPPORTED_RANGE = auto()
    OUT_OF_BOUNDS = auto()


@dataclass(frozen=True, slots=True)
class HalfWidthRejectedView:
    """A half-width edit was rejected for a user-correctable reason."""

    reason: HalfWidthRejectionReason
    requested: float
    supported_minimum: float
    supported_maximum: float


@dataclass(frozen=True, slots=True)
class HalfWidthInvariantErrorView:
    """A half-width edit failed because project state was inconsistent."""

    component_id: str


type HalfWidthEditOutcomeView = (
    HalfWidthAppliedView
    | HalfWidthAdjustedView
    | HalfWidthRetainedView
    | HalfWidthRejectedView
    | HalfWidthInvariantErrorView
)
