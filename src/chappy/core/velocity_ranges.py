"""Canonical scientific velocity-range value types."""

from __future__ import annotations

import math
from dataclasses import dataclass

DEFAULT_ANALYSIS_HALF_WIDTH_KMS = 200.0
MIN_ANALYSIS_HALF_WIDTH_KMS = 10.0
MAX_ANALYSIS_HALF_WIDTH_KMS = 2000.0


@dataclass(frozen=True, slots=True)
class LineAnalysisHalfWidth:
    """Validated half-width of one line's scientific analysis range."""

    kms: float

    def __post_init__(self) -> None:
        """Reject non-finite values and values outside the supported range."""
        value = float(self.kms)
        if not math.isfinite(value):
            msg = "Line analysis half-width must be finite."
            raise ValueError(msg)
        if not MIN_ANALYSIS_HALF_WIDTH_KMS <= value <= MAX_ANALYSIS_HALF_WIDTH_KMS:
            msg = (
                "Line analysis half-width must be between "
                f"{MIN_ANALYSIS_HALF_WIDTH_KMS:g} and {MAX_ANALYSIS_HALF_WIDTH_KMS:g} km/s."
            )
            raise ValueError(msg)
        object.__setattr__(self, "kms", value)


@dataclass(frozen=True, slots=True)
class NewCandidateAnalysisHalfWidth:
    """Validated analysis half-width copied into newly created identify candidates."""

    kms: float

    def __post_init__(self) -> None:
        """Reject invalid draft values instead of silently clamping them."""
        validated = LineAnalysisHalfWidth(self.kms)
        object.__setattr__(self, "kms", validated.kms)


@dataclass(frozen=True, slots=True)
class MultipletGroupingVelocityTolerance:
    """Velocity tolerance used only by identify multiplet grouping policy."""

    kms: float

    def __post_init__(self) -> None:
        """Require a positive finite grouping tolerance."""
        value = float(self.kms)
        if not math.isfinite(value) or value <= 0.0:
            msg = "Multiplet grouping velocity tolerance must be finite and positive."
            raise ValueError(msg)
        object.__setattr__(self, "kms", value)


DEFAULT_IDENTIFY_MULTIPLET_GROUPING_TOLERANCE = MultipletGroupingVelocityTolerance(200.0)


__all__ = [
    "DEFAULT_ANALYSIS_HALF_WIDTH_KMS",
    "DEFAULT_IDENTIFY_MULTIPLET_GROUPING_TOLERANCE",
    "MAX_ANALYSIS_HALF_WIDTH_KMS",
    "MIN_ANALYSIS_HALF_WIDTH_KMS",
    "LineAnalysisHalfWidth",
    "MultipletGroupingVelocityTolerance",
    "NewCandidateAnalysisHalfWidth",
]
