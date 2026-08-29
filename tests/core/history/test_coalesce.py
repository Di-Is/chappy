"""Tests for CoalesceBuffer class."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self

import pytest

from chappy.core.history import CoalesceBuffer, HistoryEvent, OperationId


@dataclass(frozen=True, slots=True)
class _TestCommand:
    """Typed command for coalesce tests."""

    before: int
    after: int
    op_id: OperationId = OperationId.DRAW_RANGE_CHANGE
    qualifier: str | None = None

    @property
    def operation_id(self) -> OperationId:
        """Return the test operation ID."""
        return self.op_id

    def is_noop(self) -> bool:
        """Return whether before and after are equal."""
        return self.before == self.after

    def coalesced_with(self, next_command: Self) -> Self | None:
        """Merge by preserving the first before value."""
        if not isinstance(next_command, _TestCommand):
            return None
        if (
            self.operation_id != next_command.operation_id
            or self.qualifier != next_command.qualifier
        ):
            return None
        return _TestCommand(
            before=self.before,
            after=next_command.after,
            op_id=self.operation_id,
            qualifier=self.qualifier,
        )


def create_event(
    value: int = 1, prev_value: int = 0, *, qualifier: str | None = None
) -> HistoryEvent:
    """Helper to create test events.

    Args:
        value: The "after" value.
        prev_value: The "before" value.
        qualifier: Optional qualifier.

    Returns:
        A HistoryEvent for testing.
    """
    return HistoryEvent(command=_TestCommand(before=prev_value, after=value, qualifier=qualifier))


class TestCoalesceBufferBasic:
    """Basic coalesce buffer tests."""

    def test_empty_buffer(self) -> None:
        """Test empty buffer state."""
        buffer = CoalesceBuffer()

        assert not buffer.has_pending
        assert buffer.pending_event is None

    def test_start(self) -> None:
        """Test starting a coalesce sequence."""
        buffer = CoalesceBuffer()
        event = create_event()

        buffer.start(event)

        assert buffer.has_pending
        assert buffer.pending_event == event

    def test_commit(self) -> None:
        """Test committing a pending event."""
        buffer = CoalesceBuffer()
        event = create_event()

        buffer.start(event)
        result = buffer.commit()

        assert result == event
        assert not buffer.has_pending
        assert buffer.pending_event is None

    def test_commit_empty(self) -> None:
        """Test committing an empty buffer."""
        buffer = CoalesceBuffer()

        result = buffer.commit()

        assert result is None


class TestCoalesceBufferMerge:
    """Tests for coalesce merge logic."""

    def test_coalesce_same_operation(self) -> None:
        """Test coalescing same operation type."""
        time_value = 0.0

        def mock_time() -> float:
            return time_value

        buffer = CoalesceBuffer(window_ms=500, time_provider=mock_time)

        event1 = create_event(value=1, prev_value=0, qualifier="nav")
        event2 = create_event(value=2, prev_value=1, qualifier="nav")

        buffer.start(event1)

        # Within window
        time_value = 0.1
        result = buffer.try_coalesce(event2)

        assert result is not None
        assert isinstance(result.command, _TestCommand)
        assert result.command.before == 0
        assert result.command.after == 2

    def test_coalesce_expired_window(self) -> None:
        """Test that expired window prevents coalesce."""
        time_value = 0.0

        def mock_time() -> float:
            return time_value

        buffer = CoalesceBuffer(window_ms=500, time_provider=mock_time)

        event1 = create_event(value=1, prev_value=0, qualifier="nav")
        event2 = create_event(value=2, prev_value=1, qualifier="nav")

        buffer.start(event1)

        # After window (600ms)
        time_value = 0.6
        result = buffer.try_coalesce(event2)

        assert result is None

    def test_coalesce_different_operation_id(self) -> None:
        """Test that different operation_id prevents coalesce."""
        buffer = CoalesceBuffer(window_ms=500)

        event1 = create_event(value=1, prev_value=0)
        event2 = HistoryEvent(
            command=_TestCommand(before=1, after=2, op_id=OperationId.CONT_MOVE_POINT)
        )

        buffer.start(event1)
        result = buffer.try_coalesce(event2)

        assert result is None

    def test_coalesce_different_qualifier(self) -> None:
        """Test that different qualifier prevents coalesce."""
        buffer = CoalesceBuffer(window_ms=500)

        event1 = create_event(value=1, prev_value=0, qualifier="nav")
        event2 = create_event(value=2, prev_value=1, qualifier="manual")

        buffer.start(event1)
        result = buffer.try_coalesce(event2)

        assert result is None

    def test_coalesce_empty_buffer(self) -> None:
        """Test coalesce attempt on empty buffer."""
        buffer = CoalesceBuffer(window_ms=500)
        event = create_event()

        result = buffer.try_coalesce(event)

        assert result is None


class TestCoalesceBufferExpiration:
    """Tests for window expiration."""

    def test_is_expired_empty(self) -> None:
        """Test is_expired on empty buffer."""
        buffer = CoalesceBuffer(window_ms=500)

        assert buffer.is_expired()

    def test_is_expired_within_window(self) -> None:
        """Test is_expired within window."""
        time_value = 0.0

        def mock_time() -> float:
            return time_value

        buffer = CoalesceBuffer(window_ms=500, time_provider=mock_time)
        event = create_event()

        buffer.start(event)

        # Within window
        time_value = 0.1
        assert not buffer.is_expired()

    def test_is_expired_after_window(self) -> None:
        """Test is_expired after window."""
        time_value = 0.0

        def mock_time() -> float:
            return time_value

        buffer = CoalesceBuffer(window_ms=500, time_provider=mock_time)
        event = create_event()

        buffer.start(event)

        # After window
        time_value = 0.6
        assert buffer.is_expired()


class TestCoalesceBufferChain:
    """Tests for chained coalesce operations."""

    def test_multiple_coalesce(self) -> None:
        """Test multiple consecutive coalesce operations."""
        time_value = 0.0

        def mock_time() -> float:
            return time_value

        buffer = CoalesceBuffer(window_ms=500, time_provider=mock_time)

        # Initial event: 0 -> 1
        event1 = create_event(value=1, prev_value=0, qualifier="nav")
        buffer.start(event1)

        # Second event: 1 -> 2 (100ms later)
        time_value = 0.1
        event2 = create_event(value=2, prev_value=1, qualifier="nav")
        buffer.try_coalesce(event2)

        # Third event: 2 -> 3 (200ms later)
        time_value = 0.2
        event3 = create_event(value=3, prev_value=2, qualifier="nav")
        result = buffer.try_coalesce(event3)

        # Should have merged: 0 -> 3
        assert result is not None
        assert isinstance(result.command, _TestCommand)
        assert result.command.before == 0
        assert result.command.after == 3

    def test_coalesce_preserves_created_at(self) -> None:
        """Test that coalesce preserves original created_at."""
        buffer = CoalesceBuffer(window_ms=500)

        event1 = create_event(value=1, prev_value=0, qualifier="nav")
        original_time = event1.created_at

        buffer.start(event1)
        event2 = create_event(value=2, prev_value=1, qualifier="nav")
        result = buffer.try_coalesce(event2)

        assert result is not None
        assert result.created_at == original_time
