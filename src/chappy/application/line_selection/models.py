"""Result models for line selection use cases."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SelectionChange:
    """Outcome of a selection mutation.

    Attributes:
        selected_ids: Full set of user-selected line identifiers after the change
            (never includes locked existing identifiers).
        changed_line_ids: Identifiers whose aggregated selection state may have
            changed, including multiplet companions.
    """

    selected_ids: frozenset[str]
    changed_line_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class ProposedTieGroup:
    """A tie group explicitly proposed by a line-selection action."""

    line_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LineSelectionResult:
    """Completed line selection and declarative group proposals."""

    selected_ids: tuple[str, ...]
    proposed_tie_groups: tuple[ProposedTieGroup, ...] = ()
