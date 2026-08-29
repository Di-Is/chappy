"""Stateful, Qt-independent line selection session.

The session owns the user's in-progress selection set and encapsulates the
multiplet-aware rules previously embedded in the dialog: toggling any member of
a multiplet toggles the whole group, multiplets containing already-selected
(existing) lines cannot be deselected, and existing lines are never mutated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from chappy.application.line_selection.models import (
    LineSelectionResult,
    ProposedTieGroup,
    SelectionChange,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from chappy.application.line_selection.ports import MultipletCatalogPort
    from chappy.core.atomic_data import AtomicLine


class LineSelectionSession:
    """Track the working selection of atomic lines with multiplet semantics."""

    def __init__(
        self,
        catalog: MultipletCatalogPort,
        *,
        existing_ids: Iterable[str] | None = None,
        initial_ids: Iterable[str] | None = None,
    ) -> None:
        """Initialize the session.

        Args:
            catalog: Atomic-line catalog used to resolve lines and multiplets.
            existing_ids: Already-selected, locked line identifiers.
            initial_ids: Pre-selected identifiers; locked identifiers are removed.
        """
        self._catalog = catalog
        self._existing_ids: set[str] = set(existing_ids or ())
        self._selected_ids: set[str] = set(initial_ids or ())
        self._selected_ids.difference_update(self._existing_ids)
        self._explicit_multiplet_ids: set[str] = set()
        # The catalog is immutable for the session's lifetime, so multiplet
        # membership can be memoized; ``get_lines_by_multiplet`` is an O(N) scan
        # otherwise re-run for every aggregated-state query on each selection
        # change.
        self._multiplet_cache: dict[str, list[AtomicLine]] = {}

    @property
    def selected_ids(self) -> frozenset[str]:
        """Return the current user-selected identifiers."""
        return frozenset(self._selected_ids)

    @property
    def existing_ids(self) -> frozenset[str]:
        """Return the locked, already-selected identifiers."""
        return frozenset(self._existing_ids)

    def is_aggregated_selected(self, line: AtomicLine) -> bool:
        """Return whether the line (or any multiplet companion) is selected.

        Args:
            line: Line whose aggregated selection state is requested.

        Returns:
            ``True`` when the line, or any member of its multiplet, is selected
            or already exists.
        """
        if line.multiplet_id:
            return any(
                self._is_selected_or_existing(member.line_id)
                for member in self._members(line.multiplet_id)
            )
        return self._is_selected_or_existing(line.line_id)

    def toggle(self, line_id: str) -> SelectionChange:
        """Toggle selection for a line, propagating across its multiplet.

        Args:
            line_id: Identifier of the clicked line.

        Returns:
            The resulting selection change. Existing (locked) or unknown lines
            produce a no-op change.
        """
        line = self._catalog.get_line_by_id(line_id)
        if line is None or line_id in self._existing_ids:
            return self._no_change()
        if line.multiplet_id:
            return self._toggle_multiplet(line)
        self._set_selected(line_id, selected=not self._is_selected_or_existing(line_id))
        return SelectionChange(frozenset(self._selected_ids), frozenset({line_id}))

    def remove(self, line_id: str) -> SelectionChange:
        """Remove a line (and its selected multiplet companions) from selection.

        Args:
            line_id: Identifier to remove.

        Returns:
            The resulting selection change. Unknown or unselected lines produce a
            no-op change.
        """
        line = self._catalog.get_line_by_id(line_id)
        if line is None or line_id not in self._selected_ids:
            return self._no_change()

        if line.multiplet_id:
            to_clear = [
                member
                for member in self._members(line.multiplet_id)
                if member.line_id in self._selected_ids
                and member.line_id not in self._existing_ids
            ]
            if not to_clear:
                to_clear = [line]
        else:
            to_clear = [line]

        for member in to_clear:
            self._selected_ids.discard(member.line_id)
        if line.multiplet_id and not any(
            member.line_id in self._selected_ids for member in self._members(line.multiplet_id)
        ):
            self._explicit_multiplet_ids.discard(line.multiplet_id)
        changed = frozenset(member.line_id for member in to_clear)
        return SelectionChange(frozenset(self._selected_ids), changed)

    def clear(self) -> SelectionChange:
        """Clear all user-selected lines."""
        changed = frozenset(self._selected_ids)
        self._selected_ids.clear()
        self._explicit_multiplet_ids.clear()
        return SelectionChange(frozenset(), changed)

    def build_result(self) -> LineSelectionResult:
        """Build the selected line IDs and explicitly requested tie groups."""
        all_selected = self._selected_ids | self._existing_ids
        ordered_selected = tuple(line_id for line_id in self._ordered_line_ids(self._selected_ids))
        proposals: list[ProposedTieGroup] = []
        for multiplet_id in self._explicit_multiplet_ids:
            member_ids = tuple(
                line.line_id
                for line in self._ordered_lines(self._members(multiplet_id))
                if line.line_id in all_selected
            )
            if len(member_ids) >= 2:
                proposals.append(ProposedTieGroup(line_ids=member_ids))

        proposals.sort(key=lambda group: group.line_ids)
        return LineSelectionResult(
            selected_ids=ordered_selected, proposed_tie_groups=tuple(proposals)
        )

    def _toggle_multiplet(self, line: AtomicLine) -> SelectionChange:
        """Toggle every selectable member of the line's multiplet."""
        members = self._members(line.multiplet_id)
        changed = frozenset(member.line_id for member in members)

        if len(members) <= 1:
            currently = self._is_selected_or_existing(line.line_id)
            self._set_selected(line.line_id, selected=not currently)
            return SelectionChange(frozenset(self._selected_ids), changed)

        select = not self.is_aggregated_selected(line)
        has_existing = any(member.line_id in self._existing_ids for member in members)

        # A multiplet that already contains a locked line cannot be deselected;
        # attempting to do so re-selects all selectable members instead.
        target = True if (not select and has_existing) else select
        for member in members:
            if member.line_id in self._existing_ids:
                continue
            self._set_selected(member.line_id, selected=target)
        if target:
            self._explicit_multiplet_ids.add(line.multiplet_id)
        else:
            self._explicit_multiplet_ids.discard(line.multiplet_id)
        return SelectionChange(frozenset(self._selected_ids), changed)

    def _members(self, multiplet_id: str) -> list[AtomicLine]:
        """Return the multiplet's lines, memoizing the O(N) catalog scan."""
        cached = self._multiplet_cache.get(multiplet_id)
        if cached is None:
            cached = self._catalog.get_lines_by_multiplet(multiplet_id)
            self._multiplet_cache[multiplet_id] = cached
        return cached

    def _is_selected_or_existing(self, line_id: str) -> bool:
        """Return whether a line is user-selected or locked."""
        return line_id in self._selected_ids or line_id in self._existing_ids

    def _set_selected(self, line_id: str, *, selected: bool) -> None:
        """Add or remove a single line from the selection set."""
        if selected:
            self._selected_ids.add(line_id)
        else:
            self._selected_ids.discard(line_id)

    def _ordered_line_ids(self, line_ids: Iterable[str]) -> list[str]:
        """Return line identifiers in deterministic wavelength order."""
        lines = [
            line
            for line_id in line_ids
            if (line := self._catalog.get_line_by_id(line_id)) is not None
        ]
        return [line.line_id for line in self._ordered_lines(lines)]

    @staticmethod
    def _ordered_lines(lines: Iterable[AtomicLine]) -> list[AtomicLine]:
        """Sort atomic lines deterministically for result serialization."""
        return sorted(lines, key=lambda line: (line.wavelength_angstrom, line.line_id))

    def _no_change(self) -> SelectionChange:
        """Return a change that reflects the unchanged current selection."""
        return SelectionChange(frozenset(self._selected_ids), frozenset())
