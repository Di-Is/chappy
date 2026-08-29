"""Typed velocity-display range state and pure session transitions."""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from typing import TYPE_CHECKING, Literal, NewType

if TYPE_CHECKING:
    from collections.abc import Iterable

MIN_VELOCITY_DISPLAY_HALF_WIDTH_KMS = 10.0
MAX_VELOCITY_DISPLAY_HALF_WIDTH_KMS = 5000.0

type VelocityDisplayRangeSource = Literal["auto", "manual"]
VelocityDisplayScopeKey = NewType("VelocityDisplayScopeKey", str)


@dataclass(frozen=True, slots=True)
class VelocityDisplayHalfWidth:
    """Positive plot-local half-width in km/s."""

    value: float

    def __post_init__(self) -> None:
        """Reject invalid values instead of silently clamping them."""
        value = float(self.value)
        if not math.isfinite(value):
            msg = "Velocity display half-width must be finite."
            raise ValueError(msg)
        if (
            not MIN_VELOCITY_DISPLAY_HALF_WIDTH_KMS
            <= value
            <= (MAX_VELOCITY_DISPLAY_HALF_WIDTH_KMS)
        ):
            msg = (
                "Velocity display half-width must be between "
                f"{MIN_VELOCITY_DISPLAY_HALF_WIDTH_KMS:g} and "
                f"{MAX_VELOCITY_DISPLAY_HALF_WIDTH_KMS:g} km/s."
            )
            raise ValueError(msg)
        object.__setattr__(self, "value", value)


@dataclass(frozen=True, slots=True)
class VelocityAnalysisBounds:
    """Symmetric scientific analysis boundaries rendered on a velocity subplot."""

    lower_kms: float
    upper_kms: float

    @classmethod
    def from_half_width(cls, half_width_kms: float) -> VelocityAnalysisBounds:
        """Build symmetric boundaries from a positive finite half-width."""
        value = float(half_width_kms)
        if not math.isfinite(value) or value <= 0.0:
            msg = "Analysis half-width must be finite and positive."
            raise ValueError(msg)
        return cls(lower_kms=-value, upper_kms=value)

    @property
    def half_width_kms(self) -> float:
        """Return the positive half-width represented by these bounds."""
        return self.upper_kms


@dataclass(frozen=True, slots=True)
class VelocityDisplayRangeState:
    """Overlay-session display range state for one typed display scope."""

    value: VelocityDisplayHalfWidth
    source: VelocityDisplayRangeSource
    scope_key: VelocityDisplayScopeKey

    def __post_init__(self) -> None:
        """Require an explicit owning overlay scope for the session value."""
        if not self.scope_key:
            msg = "Velocity display range state requires a scope key."
            raise ValueError(msg)


def derive_velocity_display_half_width(
    analysis_half_widths: Iterable[float],
) -> VelocityDisplayHalfWidth:
    """Derive the next deterministic nice display half-width above the maximum."""
    values = tuple(Decimal(str(float(value))) for value in analysis_half_widths)
    if not values:
        msg = "At least one analysis half-width is required."
        raise ValueError(msg)
    if any(not value.is_finite() or value <= 0 for value in values):
        msg = "Analysis half-widths must be finite and positive."
        raise ValueError(msg)

    maximum = max(values)
    exponent = maximum.adjusted()
    scale = Decimal(10) ** exponent
    quantum = max(Decimal(10), scale / Decimal(4))
    steps = (maximum / quantum).to_integral_value(rounding=ROUND_FLOOR) + 1
    derived = float(steps * quantum)
    return VelocityDisplayHalfWidth(derived)


def initialize(
    scope_key: VelocityDisplayScopeKey, analysis_half_widths: Iterable[float]
) -> VelocityDisplayRangeState:
    """Start an automatic overlay display-range session."""
    return VelocityDisplayRangeState(
        value=derive_velocity_display_half_width(analysis_half_widths),
        source="auto",
        scope_key=scope_key,
    )


def commit_manual(
    state: VelocityDisplayRangeState, value: VelocityDisplayHalfWidth
) -> VelocityDisplayRangeState:
    """Commit a validated manual display value without changing scope ownership."""
    return VelocityDisplayRangeState(value=value, source="manual", scope_key=state.scope_key)


def fit_view_to_analysis_ranges(
    scope_key: VelocityDisplayScopeKey, analysis_half_widths: Iterable[float]
) -> VelocityDisplayRangeState:
    """Explicitly return to an automatically derived range for the current display scope."""
    return initialize(scope_key, analysis_half_widths)


def switch_scope(
    state: VelocityDisplayRangeState,
    scope_key: VelocityDisplayScopeKey,
    analysis_half_widths: Iterable[float],
) -> VelocityDisplayRangeState:
    """Switch overlay scope while preserving manual values and re-deriving automatic values."""
    if state.scope_key == scope_key:
        return state
    if state.source == "manual":
        return VelocityDisplayRangeState(value=state.value, source="manual", scope_key=scope_key)
    return initialize(scope_key, analysis_half_widths)


def clear() -> None:
    """Return the explicit empty overlay-session state."""


__all__ = [
    "MAX_VELOCITY_DISPLAY_HALF_WIDTH_KMS",
    "MIN_VELOCITY_DISPLAY_HALF_WIDTH_KMS",
    "VelocityAnalysisBounds",
    "VelocityDisplayHalfWidth",
    "VelocityDisplayRangeSource",
    "VelocityDisplayRangeState",
    "VelocityDisplayScopeKey",
    "clear",
    "commit_manual",
    "derive_velocity_display_half_width",
    "fit_view_to_analysis_ranges",
    "initialize",
    "switch_scope",
]
