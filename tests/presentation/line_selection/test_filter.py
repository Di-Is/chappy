"""Tests for LineSelectionFilterEvaluator (Qt-independent)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chappy.presentation.line_selection.filter import (
    LineFilterStatus,
    LineSearchCriteria,
    LineSelectionFilterEvaluator,
)

if TYPE_CHECKING:
    from chappy.core.atomic_data import AtomicLine, SearchFilters


class _FakeSearch:
    """Records the filters it receives and returns a canned result."""

    def __init__(self, lines: list[AtomicLine]) -> None:
        self.lines = lines
        self.calls: list[SearchFilters] = []

    def search_lines(self, filters: SearchFilters | None = None) -> list[AtomicLine]:
        assert filters is not None
        self.calls.append(filters)
        return self.lines


def test_invalid_range_does_not_search() -> None:
    """min > max yields INVALID_RANGE without invoking the search."""
    search = _FakeSearch([])
    evaluator = LineSelectionFilterEvaluator(search)

    criteria = LineSearchCriteria(wavelength_min=1300.0, wavelength_max=1200.0)
    result = evaluator.evaluate(criteria, None)

    assert result.status is LineFilterStatus.INVALID_RANGE
    assert result.lines == ()
    assert search.calls == []


def test_unchanged_criteria_does_not_search() -> None:
    """Re-evaluating identical criteria yields UNCHANGED without searching."""
    search = _FakeSearch([])
    evaluator = LineSelectionFilterEvaluator(search)

    criteria = LineSearchCriteria(keyword="HI")
    result = evaluator.evaluate(criteria, criteria)

    assert result.status is LineFilterStatus.UNCHANGED
    assert search.calls == []


def test_applied_builds_search_filters() -> None:
    """New criteria run the search and forward all fields to SearchFilters."""
    search = _FakeSearch([])
    evaluator = LineSelectionFilterEvaluator(search)

    criteria = LineSearchCriteria(
        keyword="Lya", element="H", charge_state=0, wavelength_min=1000.0, wavelength_max=2000.0
    )
    result = evaluator.evaluate(criteria, None)

    assert result.status is LineFilterStatus.APPLIED
    assert len(search.calls) == 1
    applied = search.calls[0]
    assert applied.query == "Lya"
    assert applied.element_filter == "H"
    assert applied.charge_state == 0
    assert applied.wavelength_min == 1000.0
    assert applied.wavelength_max == 2000.0


def test_applied_returns_searched_lines_as_tuple() -> None:
    """The result exposes searched lines as an immutable tuple."""
    sentinel: list[AtomicLine] = []
    evaluator = LineSelectionFilterEvaluator(_FakeSearch(sentinel))

    result = evaluator.evaluate(LineSearchCriteria(keyword="x"), None)

    assert result.status is LineFilterStatus.APPLIED
    assert isinstance(result.lines, tuple)


def test_changed_criteria_after_previous_runs_search() -> None:
    """Different criteria from the previous one trigger a fresh search."""
    search = _FakeSearch([])
    evaluator = LineSelectionFilterEvaluator(search)

    previous = LineSearchCriteria(keyword="HI")
    current = LineSearchCriteria(keyword="CIV")
    result = evaluator.evaluate(current, previous)

    assert result.status is LineFilterStatus.APPLIED
    assert len(search.calls) == 1
