"""Session-scoped display label allocator for parameter tie sets."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

_ALPHABET_SIZE = 26


def _label_for_index(index: int) -> str:
    """Return a spreadsheet-style label (A, B, ..., Z, AA, AB, ...) for a 0-based index."""
    letters: list[str] = []
    remaining = index
    while True:
        remaining, remainder = divmod(remaining, _ALPHABET_SIZE)
        letters.append(chr(ord("A") + remainder))
        if remaining == 0:
            break
        remaining -= 1
    return "".join(reversed(letters))


class OptimizeTieLabelAllocator:
    """Assign session-scoped, non-persisted display labels to tie sets.

    Labels are assigned in first-seen order (A, B, ..., Z, AA, ...) and stay
    stable for the lifetime of the loaded project. Call ``reset`` when the
    active project changes or is cleared.
    """

    def __init__(self) -> None:
        """Initialize the allocator with no assigned labels."""
        self._labels: dict[str, str] = {}
        self._indices: dict[str, int] = {}
        self._next_index = 0

    def reset(self) -> None:
        """Clear all assigned labels."""
        self._labels.clear()
        self._indices.clear()
        self._next_index = 0

    def assign_all(self, uids: Iterable[str]) -> None:
        """Assign labels to any tie set uids not yet seen, in iteration order.

        Args:
            uids: Tie set uids in model load/creation order.
        """
        for uid in uids:
            self.label_for(uid)

    def label_for(self, uid: str) -> str:
        """Return the display label for a tie set uid, assigning one if new."""
        label = self._labels.get(uid)
        if label is not None:
            return label
        label = _label_for_index(self._next_index)
        self._labels[uid] = label
        self._indices[uid] = self._next_index
        self._next_index += 1
        return label

    def index_for(self, uid: str) -> int:
        """Return the 0-based assignment index for a tie set uid, assigning one if new."""
        self.label_for(uid)
        return self._indices[uid]
