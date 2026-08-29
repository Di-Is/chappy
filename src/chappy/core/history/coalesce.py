"""Coalesce buffer for continuous operations.

This module provides the CoalesceBuffer class that aggregates consecutive
operations of the same type within a time window into a single history entry.
This prevents undo/redo noise from high-frequency operations like wheel zoom.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from .history_event import HistoryEvent

# Default coalesce window in milliseconds
DEFAULT_COALESCE_WINDOW_MS = 500


@dataclass(frozen=True, slots=True)
class CoalesceBufferSnapshot:
    """Internal restorable state used by an atomic history mutation."""

    pending: HistoryEvent | None
    last_update_time: float | None


class CoalesceBuffer:
    """Buffer for coalescing consecutive operations.

    Aggregates consecutive operations of the same type (same operation_id
    and qualifier) within a time window into a single history entry.

    Merge rule:
        - The pending command decides how typed snapshots are merged.

    Commit conditions:
        - Time window (500ms default) elapsed since last update
        - Different operation type started
        - Explicit commit() call

    Args:
        window_ms: Coalesce window in milliseconds.
        time_provider: Function returning current time in seconds.
            Defaults to time.monotonic for reliable elapsed time measurement.
    """

    def __init__(
        self,
        *,
        window_ms: int = DEFAULT_COALESCE_WINDOW_MS,
        time_provider: Callable[[], float] | None = None,
    ) -> None:
        """Initialize coalesce buffer.

        Args:
            window_ms: Coalesce window in milliseconds.
            time_provider: Function returning current time in seconds (for testing).
        """
        self._window_seconds = window_ms / 1000.0
        self._time_provider = time_provider or time.monotonic

        self._pending: HistoryEvent | None = None
        self._last_update_time: float | None = None

    @property
    def has_pending(self) -> bool:
        """Return whether there is a pending event."""
        return self._pending is not None

    @property
    def pending_event(self) -> HistoryEvent | None:
        """Return the pending event without committing."""
        return self._pending

    def start(self, event: HistoryEvent) -> None:
        """Start a new coalesce sequence.

        Any existing pending event should be committed before calling this.

        Args:
            event: The first event in the coalesce sequence.
        """
        self._pending = event
        self._last_update_time = self._time_provider()

    def try_coalesce(self, event: HistoryEvent) -> HistoryEvent | None:
        """Try to coalesce a new event with the pending event.

        If coalesce is successful, returns the merged event.
        If coalesce fails (different operation, window expired), returns None.

        Args:
            event: The new event to try coalescing.

        Returns:
            Merged event if coalesced, None otherwise.
        """
        if self._pending is None:
            return None

        current_time = self._time_provider()

        # Check time window
        if self._last_update_time is not None:
            elapsed = current_time - self._last_update_time
            if elapsed > self._window_seconds:
                # Window expired, don't coalesce
                return None

        # Check operation_id and qualifier match
        if (
            self._pending.operation_id != event.operation_id
            or self._pending.qualifier != event.qualifier
        ):
            # Different operation type, don't coalesce
            return None

        merged = self._pending.coalesced_with(event)
        if merged is None:
            return None
        self._pending = merged
        self._last_update_time = current_time

        return merged

    def commit(self) -> HistoryEvent | None:
        """Commit and return the pending event.

        After commit, the buffer is cleared.

        Returns:
            The pending event, or None if buffer was empty.
        """
        result = self._pending
        self._pending = None
        self._last_update_time = None
        return result

    def snapshot(self) -> CoalesceBufferSnapshot:
        """Capture pending coalescing state without committing it."""
        return CoalesceBufferSnapshot(
            pending=self._pending, last_update_time=self._last_update_time
        )

    def restore(self, snapshot: CoalesceBufferSnapshot) -> None:
        """Restore pending coalescing state after an aborted history mutation."""
        self._pending = snapshot.pending
        self._last_update_time = snapshot.last_update_time

    def is_expired(self) -> bool:
        """Check if the pending event's time window has expired.

        Returns:
            True if window expired or no pending event, False otherwise.
        """
        if self._pending is None or self._last_update_time is None:
            return True

        elapsed = self._time_provider() - self._last_update_time
        return elapsed > self._window_seconds
