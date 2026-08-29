"""Typed scalar conversion helpers shared across layers."""

from __future__ import annotations

import math
from typing import SupportsFloat, SupportsIndex, TypeGuard, overload

FloatLike = SupportsFloat | SupportsIndex | str


def is_float_like(value: object) -> TypeGuard[FloatLike]:
    """Return whether value can be passed to ``float`` within typed code."""
    return isinstance(value, str | SupportsFloat | SupportsIndex)


@overload
def coerce_float(
    value: object | None, *, default: float, require_finite: bool = False
) -> float: ...


@overload
def coerce_float(
    value: object | None, *, default: None = None, require_finite: bool = False
) -> float | None: ...


def coerce_float(
    value: object | None, *, default: float | None = None, require_finite: bool = False
) -> float | None:
    """Convert a scalar value to float, returning a fallback on failure.

    Args:
        value: Raw scalar value to convert.
        default: Value returned when conversion fails.
        require_finite: Whether ``nan`` and infinite values should be rejected.

    Returns:
        Converted float value, or the provided fallback.
    """
    if value is None or not is_float_like(value):
        return default

    try:
        result = float(value)
    except (TypeError, ValueError):
        return default

    if require_finite and not math.isfinite(result):
        return default

    return result
