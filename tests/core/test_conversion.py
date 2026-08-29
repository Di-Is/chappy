"""Tests for scalar conversion helpers."""

from __future__ import annotations

import math

from chappy.core.conversion import coerce_float


def test_coerce_float_returns_converted_value() -> None:
    """String and numeric inputs are converted to float."""
    assert coerce_float("1.25", default=None) == 1.25
    assert coerce_float(2, default=None) == 2.0


def test_coerce_float_returns_default_for_invalid_value() -> None:
    """Invalid inputs return the provided fallback."""
    assert coerce_float("bad", default=None) is None
    assert coerce_float(object(), default=3.5) == 3.5


def test_coerce_float_can_reject_non_finite_values() -> None:
    """Finite mode rejects NaN and infinity."""
    assert coerce_float(math.nan, default=None, require_finite=True) is None
    assert coerce_float(math.inf, default=4.0, require_finite=True) == 4.0
    assert coerce_float(math.inf, default=None) == math.inf
