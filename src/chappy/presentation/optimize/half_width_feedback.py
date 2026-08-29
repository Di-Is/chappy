"""Pure mapping from a half-width edit outcome to a feedback display."""

from __future__ import annotations

import typing
from dataclasses import dataclass
from enum import Enum, auto

from chappy.presentation.optimize.models import (
    HalfWidthAdjustedView,
    HalfWidthAppliedView,
    HalfWidthEditOutcomeView,
    HalfWidthInvariantErrorView,
    HalfWidthRejectedView,
    HalfWidthRejectionReason,
    HalfWidthRetainedView,
)


class FeedbackLevel(Enum):
    """Severity of a feedback message."""

    INFO = auto()
    ERROR = auto()


@dataclass(frozen=True, slots=True)
class HalfWidthFeedbackApplied:
    """Feedback for an edit applied exactly as requested."""

    applied: float
    affected_count: int
    level: FeedbackLevel
    show_cell_annotation: bool


@dataclass(frozen=True, slots=True)
class HalfWidthFeedbackAdjusted:
    """Feedback for an edit widened to contain all model centers."""

    requested: float
    applied: float
    affected_count: int
    level: FeedbackLevel
    show_cell_annotation: bool


@dataclass(frozen=True, slots=True)
class HalfWidthFeedbackRetainedAlreadyEqual:
    """Feedback for a no-op edit that already matched the retained value."""

    retained: float
    level: FeedbackLevel
    show_cell_annotation: bool


@dataclass(frozen=True, slots=True)
class HalfWidthFeedbackRetainedMinimum:
    """Feedback for a no-op edit clamped to the model-center minimum."""

    requested: float
    retained: float
    level: FeedbackLevel
    show_cell_annotation: bool


@dataclass(frozen=True, slots=True)
class HalfWidthFeedbackRejectedComponentRange:
    """Feedback for a rejection because model centers exceed the supported range."""

    supported_maximum: float
    level: FeedbackLevel
    show_cell_annotation: bool


@dataclass(frozen=True, slots=True)
class HalfWidthFeedbackRejectedOutOfBounds:
    """Feedback for a rejection because the requested value is out of bounds."""

    supported_minimum: float
    supported_maximum: float
    level: FeedbackLevel
    show_cell_annotation: bool


@dataclass(frozen=True, slots=True)
class HalfWidthFeedbackInvariantError:
    """Feedback for a rejection caused by inconsistent project state."""

    component_id: str
    level: FeedbackLevel
    show_cell_annotation: bool


type HalfWidthFeedbackDisplay = (
    HalfWidthFeedbackApplied
    | HalfWidthFeedbackAdjusted
    | HalfWidthFeedbackRetainedAlreadyEqual
    | HalfWidthFeedbackRetainedMinimum
    | HalfWidthFeedbackRejectedComponentRange
    | HalfWidthFeedbackRejectedOutOfBounds
    | HalfWidthFeedbackInvariantError
)


def half_width_feedback(outcome: HalfWidthEditOutcomeView) -> HalfWidthFeedbackDisplay:
    """Map a half-width edit outcome to a feedback display."""
    if isinstance(outcome, HalfWidthAppliedView):
        return HalfWidthFeedbackApplied(
            applied=outcome.applied,
            affected_count=outcome.affected_count,
            level=FeedbackLevel.INFO,
            show_cell_annotation=False,
        )
    if isinstance(outcome, HalfWidthAdjustedView):
        return HalfWidthFeedbackAdjusted(
            requested=outcome.requested,
            applied=outcome.applied,
            affected_count=outcome.affected_count,
            level=FeedbackLevel.INFO,
            show_cell_annotation=True,
        )
    if isinstance(outcome, HalfWidthRetainedView):
        if outcome.already_equal:
            return HalfWidthFeedbackRetainedAlreadyEqual(
                retained=outcome.retained, level=FeedbackLevel.INFO, show_cell_annotation=True
            )
        return HalfWidthFeedbackRetainedMinimum(
            requested=outcome.requested,
            retained=outcome.retained,
            level=FeedbackLevel.INFO,
            show_cell_annotation=True,
        )
    if isinstance(outcome, HalfWidthRejectedView):
        if outcome.reason is HalfWidthRejectionReason.COMPONENT_OUTSIDE_SUPPORTED_RANGE:
            return HalfWidthFeedbackRejectedComponentRange(
                supported_maximum=outcome.supported_maximum,
                level=FeedbackLevel.ERROR,
                show_cell_annotation=True,
            )
        return HalfWidthFeedbackRejectedOutOfBounds(
            supported_minimum=outcome.supported_minimum,
            supported_maximum=outcome.supported_maximum,
            level=FeedbackLevel.ERROR,
            show_cell_annotation=True,
        )
    if isinstance(outcome, HalfWidthInvariantErrorView):
        return HalfWidthFeedbackInvariantError(
            component_id=outcome.component_id,
            level=FeedbackLevel.ERROR,
            show_cell_annotation=False,
        )
    typing.assert_never(outcome)
