"""Pure formatting helpers for value-with-error tree cells.

This module rounds an uncertainty to two significant figures and formats the
paired value to the same number of decimal places. It intentionally does not
implement the PDG variable-digit rounding rule (the "354/949" convention);
it is a fixed two-significant-figure simplification used only for display.
"""

from __future__ import annotations

import math

_SIGNIFICANT_FIGURES = 2
_LOG10_EPSILON = 1e-12


def format_value_with_error(value: float, error: float | None, fallback_spec: str) -> str:
    """Format a value paired with its uncertainty, rounded to 2 significant figures.

    If ``error`` is ``None``, non-finite, or non-positive, only ``value`` is
    formatted using ``fallback_spec`` (e.g. ``"{:.5f}"``). Otherwise the error
    is rounded to 2 significant figures, the decimal place count is derived
    from that rounded error, and both value and error are formatted with that
    many decimals as ``"{value} ± {error}"``.
    """
    if error is None or not math.isfinite(error) or error <= 0:
        return fallback_spec.format(value)

    rounded_error = _round_to_significant_figures(error, _SIGNIFICANT_FIGURES)
    decimals = _decimals_for(rounded_error)

    value_str = f"{value:.{decimals}f}"
    error_str = f"{rounded_error:.{decimals}f}"
    return f"{value_str} ± {error_str}"


def _round_to_significant_figures(x: float, figures: int) -> float:
    magnitude = _floor_log10(x)
    factor = 10.0 ** (figures - 1 - magnitude)
    rounded_units = round(x * factor)
    return float(rounded_units) / factor


def _decimals_for(rounded_error: float) -> int:
    magnitude = _floor_log10(rounded_error)
    return max(0, 1 - magnitude)


def _floor_log10(x: float) -> int:
    # A tiny epsilon guards against float log10 dipping just below an exact
    # power of ten (e.g. log10(0.1) landing at -1.0000000000000002).
    return math.floor(math.log10(x) + _LOG10_EPSILON)
