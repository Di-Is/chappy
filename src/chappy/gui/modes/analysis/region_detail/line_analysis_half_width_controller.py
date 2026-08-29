"""Controller for Optimize line analysis half-width edits."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from chappy.application.optimize import (
    LineAnalysisHalfWidthAdjusted,
    LineAnalysisHalfWidthApplied,
    LineAnalysisHalfWidthEditRequest,
    LineAnalysisHalfWidthInvariantViolation,
    LineAnalysisHalfWidthNoChange,
    LineAnalysisHalfWidthRejected,
)

if TYPE_CHECKING:
    from chappy.application.optimize import EditLineAnalysisHalfWidthUseCase


class LineAnalysisHalfWidthControllerResultKind(StrEnum):
    """Mode-local result kind consumed by the Optimize panel."""

    APPLIED = "applied"
    ADJUSTED = "adjusted"
    NO_CHANGE = "no_change"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class LineAnalysisHalfWidthControllerResult:
    """Mode-local result of one scientific range tree edit."""

    kind: LineAnalysisHalfWidthControllerResultKind
    requested: float
    applied: float | None = None
    affected_line_ids: tuple[str, ...] = ()
    region_id: str | None = None
    reason: str | None = None
    supported_minimum: float = 10.0
    supported_maximum: float = 2000.0


class LineAnalysisHalfWidthControllerInvariantError(RuntimeError):
    """User-intent boundary error for inconsistent model component state."""

    def __init__(self, component_id: str) -> None:
        """Initialize with the component whose state is inconsistent."""
        super().__init__(component_id)
        self.component_id = component_id


class LineAnalysisHalfWidthController:
    """Translate one typed tree-cell intent into the application use case."""

    def __init__(self, usecase: EditLineAnalysisHalfWidthUseCase) -> None:
        """Initialize the controller."""
        self._usecase = usecase

    def edit(
        self, *, line_id: str, requested_half_width: float
    ) -> LineAnalysisHalfWidthControllerResult:
        """Execute one line analysis half-width edit."""
        try:
            outcome = self._usecase.execute(
                LineAnalysisHalfWidthEditRequest(
                    line_id=line_id, requested_half_width=requested_half_width
                )
            )
        except LineAnalysisHalfWidthInvariantViolation as error:
            raise LineAnalysisHalfWidthControllerInvariantError(error.component_id) from error
        if isinstance(outcome, LineAnalysisHalfWidthApplied):
            return LineAnalysisHalfWidthControllerResult(
                kind=LineAnalysisHalfWidthControllerResultKind.APPLIED,
                requested=outcome.requested,
                applied=outcome.applied.kms,
                affected_line_ids=outcome.affected_line_ids,
                region_id=outcome.region_id,
            )
        if isinstance(outcome, LineAnalysisHalfWidthAdjusted):
            return LineAnalysisHalfWidthControllerResult(
                kind=LineAnalysisHalfWidthControllerResultKind.ADJUSTED,
                requested=outcome.requested,
                applied=outcome.applied_minimum.kms,
                affected_line_ids=outcome.affected_line_ids,
                region_id=outcome.region_id,
            )
        if isinstance(outcome, LineAnalysisHalfWidthNoChange):
            return LineAnalysisHalfWidthControllerResult(
                kind=LineAnalysisHalfWidthControllerResultKind.NO_CHANGE,
                requested=outcome.requested,
                applied=outcome.retained.kms,
                affected_line_ids=outcome.affected_line_ids,
                region_id=outcome.region_id,
                reason=outcome.reason.value,
            )
        if isinstance(outcome, LineAnalysisHalfWidthRejected):
            return LineAnalysisHalfWidthControllerResult(
                kind=LineAnalysisHalfWidthControllerResultKind.REJECTED,
                requested=outcome.requested,
                supported_minimum=outcome.supported_minimum,
                supported_maximum=outcome.supported_maximum,
                reason=outcome.reason.value,
            )
        msg = f"Unsupported line analysis half-width outcome: {type(outcome).__name__}"
        raise TypeError(msg)


__all__ = [
    "LineAnalysisHalfWidthController",
    "LineAnalysisHalfWidthControllerInvariantError",
    "LineAnalysisHalfWidthControllerResult",
    "LineAnalysisHalfWidthControllerResultKind",
]
