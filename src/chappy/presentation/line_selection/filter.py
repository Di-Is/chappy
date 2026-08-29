"""Filtering logic for the line selection dialog.

This module holds the Qt-independent portion of line filtering: building the
search criteria, validating the wavelength range, detecting no-op re-filters,
and running the search. The dialog remains responsible for reading widget
values and presenting the results.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from chappy.core.atomic_data import SearchFilters

if TYPE_CHECKING:
    from chappy.core.atomic_data import AtomicLine


@dataclass(frozen=True, slots=True)
class LineSearchCriteria:
    """Normalized filter inputs collected from the dialog."""

    keyword: str = ""
    element: str = ""
    charge_state: int | None = None
    wavelength_min: float | None = None
    wavelength_max: float | None = None

    def has_valid_range(self) -> bool:
        """Return whether the wavelength bounds are consistent.

        Returns:
            ``False`` only when both bounds are set and min exceeds max.
        """
        return not (
            self.wavelength_min is not None
            and self.wavelength_max is not None
            and self.wavelength_min > self.wavelength_max
        )

    def to_search_filters(self) -> SearchFilters:
        """Convert the criteria into core search filters."""
        return SearchFilters(
            query=self.keyword,
            element_filter=self.element,
            charge_state=self.charge_state,
            wavelength_min=self.wavelength_min,
            wavelength_max=self.wavelength_max,
        )


class LineFilterStatus(StrEnum):
    """Outcome of evaluating a filter request."""

    APPLIED = "applied"
    UNCHANGED = "unchanged"
    INVALID_RANGE = "invalid_range"


@dataclass(frozen=True, slots=True)
class LineFilterResult:
    """Result of a filter evaluation."""

    status: LineFilterStatus
    lines: tuple[AtomicLine, ...] = ()


class AtomicLineSearch(Protocol):
    """Minimal port for searching atomic lines."""

    def search_lines(self, filters: SearchFilters | None = None) -> list[AtomicLine]:
        """Return atomic lines matching the provided filters."""
        ...


class LineSelectionFilterEvaluator:
    """Evaluate line filter requests against an atomic line source."""

    def __init__(self, search: AtomicLineSearch) -> None:
        """Initialize the evaluator.

        Args:
            search: Atomic line source used to run the filtered query.
        """
        self._search = search

    def evaluate(
        self, criteria: LineSearchCriteria, previous: LineSearchCriteria | None
    ) -> LineFilterResult:
        """Evaluate a filter request.

        Args:
            criteria: Newly requested filter criteria.
            previous: Criteria that produced the currently displayed result.

        Returns:
            Result describing the outcome and, when applied, matching lines.
        """
        if not criteria.has_valid_range():
            return LineFilterResult(LineFilterStatus.INVALID_RANGE)

        if previous == criteria:
            return LineFilterResult(LineFilterStatus.UNCHANGED)

        lines = tuple(self._search.search_lines(criteria.to_search_filters()))
        return LineFilterResult(LineFilterStatus.APPLIED, lines)
