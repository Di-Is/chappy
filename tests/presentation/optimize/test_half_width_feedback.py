"""Tests for the half-width edit outcome to feedback-display mapping."""

from __future__ import annotations

from chappy.presentation.optimize import (
    FeedbackLevel,
    HalfWidthAdjustedView,
    HalfWidthAppliedView,
    HalfWidthFeedbackAdjusted,
    HalfWidthFeedbackApplied,
    HalfWidthFeedbackInvariantError,
    HalfWidthFeedbackRejectedComponentRange,
    HalfWidthFeedbackRejectedOutOfBounds,
    HalfWidthFeedbackRetainedAlreadyEqual,
    HalfWidthFeedbackRetainedMinimum,
    HalfWidthInvariantErrorView,
    HalfWidthRejectedView,
    HalfWidthRejectionReason,
    HalfWidthRetainedView,
    half_width_feedback,
)


def test_applied_outcome_maps_to_info_feedback_without_cell_annotation() -> None:
    """An exact-match apply should be an info message with no cell annotation."""
    outcome = HalfWidthAppliedView(applied=25.0, affected_count=3)
    result = half_width_feedback(outcome)
    assert result == HalfWidthFeedbackApplied(
        applied=25.0, affected_count=3, level=FeedbackLevel.INFO, show_cell_annotation=False
    )


def test_adjusted_outcome_maps_to_info_feedback_with_cell_annotation() -> None:
    """A widened apply should be an info message that also annotates the cell."""
    outcome = HalfWidthAdjustedView(requested=10.0, applied=25.0, affected_count=2)
    result = half_width_feedback(outcome)
    assert result == HalfWidthFeedbackAdjusted(
        requested=10.0,
        applied=25.0,
        affected_count=2,
        level=FeedbackLevel.INFO,
        show_cell_annotation=True,
    )


def test_retained_outcome_already_equal_maps_to_dedicated_feedback() -> None:
    """A no-op edit matching the current value should use the already-equal message."""
    outcome = HalfWidthRetainedView(requested=25.0, retained=25.0, already_equal=True)
    result = half_width_feedback(outcome)
    assert result == HalfWidthFeedbackRetainedAlreadyEqual(
        retained=25.0, level=FeedbackLevel.INFO, show_cell_annotation=True
    )


def test_retained_outcome_clamped_to_minimum_maps_to_dedicated_feedback() -> None:
    """A no-op edit clamped to the model-center minimum should report both values."""
    outcome = HalfWidthRetainedView(requested=5.0, retained=30.0, already_equal=False)
    result = half_width_feedback(outcome)
    assert result == HalfWidthFeedbackRetainedMinimum(
        requested=5.0, retained=30.0, level=FeedbackLevel.INFO, show_cell_annotation=True
    )


def test_rejected_outcome_component_range_maps_to_dedicated_feedback() -> None:
    """A rejection because model centers exceed the range should cite the maximum only."""
    outcome = HalfWidthRejectedView(
        reason=HalfWidthRejectionReason.COMPONENT_OUTSIDE_SUPPORTED_RANGE,
        requested=5000.0,
        supported_minimum=10.0,
        supported_maximum=2000.0,
    )
    result = half_width_feedback(outcome)
    assert result == HalfWidthFeedbackRejectedComponentRange(
        supported_maximum=2000.0, level=FeedbackLevel.ERROR, show_cell_annotation=True
    )


def test_rejected_outcome_out_of_bounds_maps_to_dedicated_feedback() -> None:
    """A rejection for a plain out-of-bounds request should cite both bounds."""
    outcome = HalfWidthRejectedView(
        reason=HalfWidthRejectionReason.OUT_OF_BOUNDS,
        requested=1.0,
        supported_minimum=10.0,
        supported_maximum=2000.0,
    )
    result = half_width_feedback(outcome)
    assert result == HalfWidthFeedbackRejectedOutOfBounds(
        supported_minimum=10.0,
        supported_maximum=2000.0,
        level=FeedbackLevel.ERROR,
        show_cell_annotation=True,
    )


def test_invariant_error_outcome_maps_to_error_feedback_without_cell_annotation() -> None:
    """An invariant error should be an error message without a cell annotation."""
    outcome = HalfWidthInvariantErrorView(component_id="component-1")
    result = half_width_feedback(outcome)
    assert result == HalfWidthFeedbackInvariantError(
        component_id="component-1", level=FeedbackLevel.ERROR, show_cell_annotation=False
    )
