"""Tests for editing Optimize line analysis half-widths."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from chappy.application.optimize import (
    EditLineAnalysisHalfWidthUseCase,
    LineAnalysisHalfWidthAdjusted,
    LineAnalysisHalfWidthApplied,
    LineAnalysisHalfWidthEditRequest,
    LineAnalysisHalfWidthInvariantKind,
    LineAnalysisHalfWidthInvariantViolation,
    LineAnalysisHalfWidthNoChange,
    LineAnalysisHalfWidthNoChangeReason,
    LineAnalysisHalfWidthRejected,
    LineAnalysisHalfWidthRejectionReason,
)
from chappy.application.optimize.models import PreparedLineAnalysisHalfWidthChange
from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.constants import LIGHT_SPEED_KMS


@dataclass
class _Port:
    """Combined read/transaction test port."""

    lines: dict[str, AbsorptionLine]
    region: AbsorptionRegion
    components: dict[str, AbsorberComponent] = field(default_factory=dict)
    committed: list[PreparedLineAnalysisHalfWidthChange] = field(default_factory=list)

    def analysis_line(self, line_id: str) -> AbsorptionLine | None:
        return self.lines.get(line_id)

    def analysis_region(self, region_id: str) -> AbsorptionRegion | None:
        return self.region if region_id == self.region.region_id else None

    def expand_analysis_multiplet_line_ids(self, seed_line_id: str) -> tuple[str, ...]:
        line = self.lines[seed_line_id]
        return tuple(sorted({seed_line_id, *line.multiplet_ids}))

    def analysis_component(self, component_id: str) -> AbsorberComponent | None:
        return self.components.get(component_id)

    def execute_line_analysis_half_width_change(
        self, change: PreparedLineAnalysisHalfWidthChange
    ) -> None:
        self.committed.append(change)


def _line(
    line_id: str,
    *,
    width: float = 150.0,
    model_ids: list[str] | None = None,
    multiplet_ids: list[str] | None = None,
) -> AbsorptionLine:
    line = AbsorptionLine(
        line_id=line_id,
        species="C IV",
        rest_wavelength=1548.2,
        center_z=1.0,
        window_kms=width,
        multiplet_label="C IV",
        transition_name=line_id,
        oscillator_strength=0.1,
        gamma_value=1e8,
        region_id="region-1",
        model_ids=model_ids or [],
        multiplet_ids=multiplet_ids or [],
    )
    line.lambda_range = _lambda_range(line, width)
    return line


def _lambda_range(line: AbsorptionLine, width: float) -> tuple[float, float]:
    observed = line.observed_wavelength()
    delta = observed * width / LIGHT_SPEED_KMS
    return (observed - delta, observed + delta)


def _component(component_id: str, *, velocity: float) -> AbsorberComponent:
    redshift = 1.0 + velocity * 2.0 / LIGHT_SPEED_KMS
    return AbsorberComponent(component_id=component_id, wavelength=1548.2, redshift=redshift)


def _usecase(port: _Port) -> EditLineAnalysisHalfWidthUseCase:
    return EditLineAnalysisHalfWidthUseCase(reader=port, transaction=port)


def _port(*lines: AbsorptionLine) -> _Port:
    region = AbsorptionRegion(region_id="region-1", line_ids=[line.line_id for line in lines])
    ranges = [line.lambda_range for line in lines if line.lambda_range is not None]
    region.analysis_range = (min(item[0] for item in ranges), max(item[1] for item in ranges))
    return _Port(lines={line.line_id: line for line in lines}, region=region)


def test_empty_component_line_applies_canonical_minimum() -> None:
    """A line with no components may shrink to the canonical minimum."""
    port = _port(_line("line-1"))

    outcome = _usecase(port).execute(LineAnalysisHalfWidthEditRequest("line-1", 10.0))

    assert isinstance(outcome, LineAnalysisHalfWidthApplied)
    assert outcome.applied.kms == 10.0
    assert len(port.committed) == 1


def test_request_is_adjusted_to_farthest_component_center() -> None:
    """A request must contain every model center instead of silently excluding one."""
    line = _line("line-1", model_ids=["component-1"])
    port = _port(line)
    port.components["component-1"] = _component("component-1", velocity=140.0)

    outcome = _usecase(port).execute(LineAnalysisHalfWidthEditRequest("line-1", 80.0))

    assert isinstance(outcome, LineAnalysisHalfWidthAdjusted)
    assert outcome.applied_minimum.kms == pytest.approx(140.0)
    assert outcome.constraining_component_ids == ("component-1",)


def test_multiplet_uses_components_from_all_same_region_lines() -> None:
    """A mixed empty/non-empty multiplet should use every existing component center."""
    first = _line("first", multiplet_ids=["second"])
    second = _line("second", model_ids=["component-2"], multiplet_ids=["first"])
    port = _port(first, second)
    port.components["component-2"] = _component("component-2", velocity=175.0)

    outcome = _usecase(port).execute(LineAnalysisHalfWidthEditRequest("first", 100.0))

    assert isinstance(outcome, LineAnalysisHalfWidthAdjusted)
    assert outcome.affected_line_ids == ("first", "second")
    assert tuple(item.line_id for item in port.committed[0].line_changes) == ("first", "second")


def test_adjusted_request_can_be_reasoned_no_change() -> None:
    """Already-required derived state should return feedback without committing."""
    line = _line("line-1", width=140.0, model_ids=["component-1"])
    port = _port(line)
    port.components["component-1"] = _component("component-1", velocity=140.0)

    outcome = _usecase(port).execute(LineAnalysisHalfWidthEditRequest("line-1", 80.0))

    assert isinstance(outcome, LineAnalysisHalfWidthNoChange)
    assert outcome.reason is LineAnalysisHalfWidthNoChangeReason.ALREADY_AT_REQUIRED_MINIMUM
    assert port.committed == []


def test_missing_component_is_typed_invariant_violation() -> None:
    """A dangling model ID must fail before a prepared change is committed."""
    port = _port(_line("line-1", model_ids=["missing"]))

    with pytest.raises(LineAnalysisHalfWidthInvariantViolation) as caught:
        _usecase(port).execute(LineAnalysisHalfWidthEditRequest("line-1", 100.0))

    assert caught.value.kind is LineAnalysisHalfWidthInvariantKind.MISSING_COMPONENT
    assert port.committed == []


def test_component_beyond_supported_maximum_is_rejected_without_commit() -> None:
    """A required range above the scientific maximum must not be clamped."""
    line = _line("line-1", model_ids=["component-1"])
    port = _port(line)
    port.components["component-1"] = _component("component-1", velocity=2500.0)

    outcome = _usecase(port).execute(LineAnalysisHalfWidthEditRequest("line-1", 100.0))

    assert isinstance(outcome, LineAnalysisHalfWidthRejected)
    assert outcome.reason is LineAnalysisHalfWidthRejectionReason.COMPONENT_OUTSIDE_SUPPORTED_RANGE
    assert port.committed == []


@pytest.mark.parametrize("requested", [float("nan"), 9.0, 2001.0, -100.0])
def test_invalid_requests_are_rejected_without_commit(requested: float) -> None:
    """Invalid input should return a typed rejection and never reach the transaction."""
    port = _port(_line("line-1"))

    outcome = _usecase(port).execute(LineAnalysisHalfWidthEditRequest("line-1", requested))

    assert isinstance(outcome, LineAnalysisHalfWidthRejected)
    assert port.committed == []
