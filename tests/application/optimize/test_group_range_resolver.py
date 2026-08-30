"""Tests for OptimizeGroupRangeResolver (Qt-independent)."""

from __future__ import annotations

import pytest

from chappy.application.optimize.group_range_resolver import OptimizeGroupRangeResolver
from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion


def _line(
    line_id: str,
    *,
    rest_wavelength: float,
    center_z: float,
    window_kms: float = 0.0,
    lambda_range: tuple[float, float] | None = None,
) -> AbsorptionLine:
    return AbsorptionLine(
        line_id=line_id,
        species="HI",
        rest_wavelength=rest_wavelength,
        center_z=center_z,
        window_kms=window_kms,
        multiplet_label="",
        transition_name="",
        oscillator_strength=0.0,
        gamma_value=0.0,
        lambda_range=lambda_range,
    )


def test_none_group_returns_none() -> None:
    """A missing group resolves to None."""
    assert OptimizeGroupRangeResolver({}).resolve(None) is None


def test_region_uses_analysis_range_when_present() -> None:
    """An absorption region prefers its explicit analysis range."""
    region = AbsorptionRegion(region_id="r1", analysis_range=(1500.0, 1600.0))

    assert OptimizeGroupRangeResolver({}).resolve(region) == (1500.0, 1600.0)


def test_region_derives_from_member_lines_lambda_range() -> None:
    """Without an analysis range, member line lambda_range bounds are aggregated."""
    lines = {
        "a": _line("a", rest_wavelength=1000.0, center_z=0.0, lambda_range=(1190.0, 1210.0)),
        "b": _line("b", rest_wavelength=1000.0, center_z=0.0, lambda_range=(1250.0, 1280.0)),
    }
    region = AbsorptionRegion(region_id="r", line_ids=["a", "b"])

    assert OptimizeGroupRangeResolver(lines).resolve(region) == (1190.0, 1280.0)


def test_region_derives_from_observed_window_when_no_lambda_range() -> None:
    """Lines without lambda_range fall back to observed wavelength ± window."""
    # observed = 1000 * (1 + 1.0) = 2000; window 300 km/s; c ~ 299792.458
    line = _line("a", rest_wavelength=1000.0, center_z=1.0, window_kms=300.0)
    region = AbsorptionRegion(region_id="r", line_ids=["a"])

    result = OptimizeGroupRangeResolver({"a": line}).resolve(region)

    assert result is not None
    lower, upper = result
    assert lower < 2000.0 < upper
    # symmetric window around the observed center
    assert abs((2000.0 - lower) - (upper - 2000.0)) < 1e-6


def test_region_with_missing_line_fails_fast() -> None:
    """A region whose line reference is absent is an invalid snapshot."""
    region = AbsorptionRegion(region_id="r", line_ids=["missing"])

    with pytest.raises(KeyError, match="missing"):
        OptimizeGroupRangeResolver({}).resolve(region)


def test_region_invalid_analysis_range_fails_fast() -> None:
    """Malformed explicit analysis ranges fail fast."""
    region = AbsorptionRegion(region_id="r", analysis_range=(1600.0, 1500.0))

    with pytest.raises(ValueError, match="analysis_range"):
        OptimizeGroupRangeResolver({}).resolve(region)


def test_line_invalid_lambda_range_fails_fast() -> None:
    """Malformed member line bounds fail fast."""
    line = _line("a", rest_wavelength=1000.0, center_z=0.0, lambda_range=(1210.0, 1190.0))
    region = AbsorptionRegion(region_id="r", line_ids=["a"])

    with pytest.raises(ValueError, match="lambda_range"):
        OptimizeGroupRangeResolver({"a": line}).resolve(region)


def test_line_without_usable_bounds_fails_fast() -> None:
    """A referenced line without a usable range is an invalid optimize snapshot."""
    line = _line("a", rest_wavelength=1000.0, center_z=1.0, window_kms=0.0)
    region = AbsorptionRegion(region_id="r", line_ids=["a"])

    with pytest.raises(ValueError, match="valid wavelength bounds"):
        OptimizeGroupRangeResolver({"a": line}).resolve(region)
