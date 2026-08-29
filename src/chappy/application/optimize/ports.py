"""Optimize-mode application ports."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from chappy.application.optimize.models import PreparedLineAnalysisHalfWidthChange
    from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
    from chappy.core.components.absorber import AbsorberComponent


@runtime_checkable
class CosmologyChangeNotifier(Protocol):
    """Notifier interface for consumers that react to cosmology changes."""

    def notify_cosmology_changed(self) -> None:
        """Notify that the display cosmology parameters changed."""
        ...


class LineAnalysisHalfWidthReadPort(Protocol):
    """Read-only project state required to prepare an analysis half-width edit."""

    def analysis_line(self, line_id: str) -> AbsorptionLine | None:
        """Return a line by identifier."""
        ...

    def analysis_region(self, region_id: str) -> AbsorptionRegion | None:
        """Return a region by identifier."""
        ...

    def expand_analysis_multiplet_line_ids(self, seed_line_id: str) -> tuple[str, ...]:
        """Return stable linked line identifiers for the seed."""
        ...

    def analysis_component(self, component_id: str) -> AbsorberComponent | None:
        """Return an absorber component by identifier."""
        ...


class LineAnalysisHalfWidthTransactionPort(Protocol):
    """Atomic commit boundary for one prepared scientific range edit."""

    def execute_line_analysis_half_width_change(
        self, change: PreparedLineAnalysisHalfWidthChange
    ) -> None:
        """Commit project mutation, invalidation, and history as one operation."""
        ...


__all__ = [
    "CosmologyChangeNotifier",
    "LineAnalysisHalfWidthReadPort",
    "LineAnalysisHalfWidthTransactionPort",
]
