"""Tests for the Optimize line analysis half-width controller boundary."""

from __future__ import annotations

import pytest

from chappy.application.optimize import (
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
from chappy.core.velocity_ranges import LineAnalysisHalfWidth
from chappy.gui.modes.analysis.region_detail.line_analysis_half_width_controller import (
    LineAnalysisHalfWidthController,
    LineAnalysisHalfWidthControllerInvariantError,
    LineAnalysisHalfWidthControllerResultKind,
)


class _UseCase:
    """Configurable typed outcome provider."""

    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.requests: list[LineAnalysisHalfWidthEditRequest] = []

    def execute(self, request: LineAnalysisHalfWidthEditRequest) -> object:
        self.requests.append(request)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


@pytest.mark.parametrize(
    ("outcome", "expected_kind", "expected_applied", "expected_reason"),
    [
        (
            LineAnalysisHalfWidthApplied(
                requested=120.0,
                applied=LineAnalysisHalfWidth(120.0),
                affected_line_ids=("line-1",),
                region_id="region-1",
            ),
            LineAnalysisHalfWidthControllerResultKind.APPLIED,
            120.0,
            None,
        ),
        (
            LineAnalysisHalfWidthAdjusted(
                requested=80.0,
                applied_minimum=LineAnalysisHalfWidth(140.0),
                affected_line_ids=("line-1", "line-2"),
                constraining_component_ids=("component-1",),
                region_id="region-1",
            ),
            LineAnalysisHalfWidthControllerResultKind.ADJUSTED,
            140.0,
            None,
        ),
        (
            LineAnalysisHalfWidthNoChange(
                requested=80.0,
                retained=LineAnalysisHalfWidth(140.0),
                reason=LineAnalysisHalfWidthNoChangeReason.ALREADY_AT_REQUIRED_MINIMUM,
                affected_line_ids=("line-1",),
                constraining_component_ids=("component-1",),
                region_id="region-1",
            ),
            LineAnalysisHalfWidthControllerResultKind.NO_CHANGE,
            140.0,
            "already_at_required_minimum",
        ),
        (
            LineAnalysisHalfWidthRejected(
                reason=LineAnalysisHalfWidthRejectionReason.OUTSIDE_SUPPORTED_RANGE,
                requested=2.0,
                supported_minimum=10.0,
                supported_maximum=2000.0,
            ),
            LineAnalysisHalfWidthControllerResultKind.REJECTED,
            None,
            "outside_supported_range",
        ),
    ],
)
def test_controller_maps_typed_outcomes(
    outcome: object,
    expected_kind: LineAnalysisHalfWidthControllerResultKind,
    expected_applied: float | None,
    expected_reason: str | None,
) -> None:
    """The GUI boundary should preserve application outcome semantics."""
    usecase = _UseCase(outcome)
    controller = LineAnalysisHalfWidthController(usecase)  # type: ignore[arg-type]

    result = controller.edit(line_id="line-1", requested_half_width=80.0)

    assert usecase.requests == [
        LineAnalysisHalfWidthEditRequest(line_id="line-1", requested_half_width=80.0)
    ]
    assert result.kind is expected_kind
    assert result.applied == expected_applied
    assert result.reason == expected_reason


def test_controller_translates_invariant_violation_to_gui_boundary_error() -> None:
    """An inconsistent project must expose the component ID without leaking app details."""
    usecase = _UseCase(
        LineAnalysisHalfWidthInvariantViolation(
            LineAnalysisHalfWidthInvariantKind.MISSING_COMPONENT, "line-1", "component-1"
        )
    )
    controller = LineAnalysisHalfWidthController(usecase)  # type: ignore[arg-type]

    with pytest.raises(LineAnalysisHalfWidthControllerInvariantError) as caught:
        controller.edit(line_id="line-1", requested_half_width=100.0)

    assert caught.value.component_id == "component-1"
