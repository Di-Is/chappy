"""Tests for CommandHistory class."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Event, Thread
from typing import Self

import pytest

from chappy.core.history import (
    CommandHistory,
    HistoryEvent,
    HistoryOwnerThreadError,
    HistoryState,
    OperationId,
)


@dataclass(frozen=True, slots=True)
class _TestCommand:
    """Typed command for command history tests."""

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


class MockApplier:
    """Mock applier for testing."""

    def __init__(self, *, should_fail: bool = False) -> None:
        """Initialize mock applier.

        Args:
            should_fail: If True, apply_history_event returns False.
        """
        self.applied_events: list[tuple[HistoryEvent, bool]] = []
        self.should_fail = should_fail

    def apply_history_event(self, event: HistoryEvent, *, is_undo: bool) -> bool:
        """Record and optionally fail the application.

        Args:
            event: The event to apply.
            is_undo: Whether this is an undo operation.

        Returns:
            False if should_fail is True, otherwise True.
        """
        self.applied_events.append((event, is_undo))
        return not self.should_fail


class MockApplierWithException:
    """Mock applier that raises an exception."""

    def apply_history_event(self, event: HistoryEvent, *, is_undo: bool) -> bool:
        """Raise an exception.

        Args:
            event: The event to apply.
            is_undo: Whether this is an undo operation.

        Raises:
            RuntimeError: Always raises.
        """
        raise RuntimeError("Test exception")


class ReentrantApplier:
    """Attempt one nested history transition during the outer application."""

    def __init__(self, nested_transition: Callable[[], object]) -> None:
        """Store the nested transition attempted by the first application."""
        self._nested_transition = nested_transition
        self.applied_events: list[tuple[HistoryEvent, bool]] = []
        self.nested_errors: list[RuntimeError] = []

    def apply_history_event(self, event: HistoryEvent, *, is_undo: bool) -> bool:
        """Apply once and capture the expected nested-transition rejection."""
        first_application = not self.applied_events
        self.applied_events.append((event, is_undo))
        if first_application:
            try:
                self._nested_transition()
            except RuntimeError as error:
                self.nested_errors.append(error)
        return True


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


class TestCommandHistoryBasic:
    """Basic stack operation tests."""

    def test_push_and_undo(self) -> None:
        """Test basic push and undo."""
        history = CommandHistory()
        applier = MockApplier()
        history.set_applier(applier)

        event = create_event(value=2, prev_value=1)
        history.push(event)

        assert history.can_undo
        assert not history.can_redo

        result = history.undo()

        assert result.success
        assert not history.can_undo
        assert history.can_redo
        assert len(applier.applied_events) == 1
        assert applier.applied_events[0][1] is True  # is_undo

    def test_undo_and_redo(self) -> None:
        """Test undo followed by redo."""
        history = CommandHistory()
        applier = MockApplier()
        history.set_applier(applier)

        event = create_event(value=2, prev_value=1)
        history.push(event)

        # Undo
        undo_result = history.undo()
        assert undo_result.success
        assert history.can_redo

        # Redo
        redo_result = history.redo()
        assert redo_result.success
        assert history.can_undo
        assert not history.can_redo

        # Verify both operations were applied
        assert len(applier.applied_events) == 2
        assert applier.applied_events[0][1] is True  # undo
        assert applier.applied_events[1][1] is False  # redo

    def test_redo_clears_on_new_push(self) -> None:
        """Test that new push clears redo stack (HIS.01.01.G01.S04)."""
        history = CommandHistory()
        applier = MockApplier()
        history.set_applier(applier)

        event1 = create_event(value=1, prev_value=0)
        event2 = create_event(value=2, prev_value=1)

        history.push(event1)
        history.undo()
        assert history.can_redo

        # New push should clear redo
        history.push(event2)
        assert not history.can_redo

    def test_max_history_limit(self) -> None:
        """Test maximum history limit (HIS.01.01.G02.S01)."""
        history = CommandHistory(max_history=3)

        for i in range(5):
            event = create_event(value=i + 1, prev_value=i)
            history.push(event)

        state = history.get_state()
        assert state.undo_count == 3

    def test_empty_stack_undo(self) -> None:
        """Test undo on empty stack returns failure."""
        history = CommandHistory()
        applier = MockApplier()
        history.set_applier(applier)

        result = history.undo()

        assert not result.success
        assert result.error_reason == "Nothing to undo"
        assert len(applier.applied_events) == 0

    def test_empty_stack_redo(self) -> None:
        """Test redo on empty stack returns failure."""
        history = CommandHistory()
        applier = MockApplier()
        history.set_applier(applier)

        result = history.redo()

        assert not result.success
        assert result.error_reason == "Nothing to redo"
        assert len(applier.applied_events) == 0

    def test_clear(self) -> None:
        """Test clear clears both stacks (HIS.01.01.G01.S05)."""
        history = CommandHistory()
        applier = MockApplier()
        history.set_applier(applier)

        event1 = create_event(value=1, prev_value=0)
        event2 = create_event(value=2, prev_value=1)

        history.push(event1)
        history.push(event2)
        history.undo()

        assert history.can_undo
        assert history.can_redo

        history.clear()

        assert not history.can_undo
        assert not history.can_redo


class TestCommandHistoryNoop:
    """Tests for no-op detection."""

    def test_noop_skipped(self) -> None:
        """Test that before==after events are skipped."""
        history = CommandHistory()

        event = create_event(value=1, prev_value=1)

        result = history.push(event)

        assert result is False
        assert not history.can_undo

    def test_different_values_recorded(self) -> None:
        """Test that different payload values are recorded."""
        history = CommandHistory()

        event = create_event(value=2, prev_value=1)
        result = history.push(event)

        assert result is True
        assert history.can_undo


class TestCommandHistorySuppression:
    """Tests for recording suppression."""

    def test_suppress_recording(self) -> None:
        """Test that suppression prevents recording."""
        history = CommandHistory()

        event = create_event(value=1, prev_value=0)

        with history.suppress_recording():
            result = history.push(event)
            assert result is False

        assert not history.can_undo

    def test_suppress_recording_nested(self) -> None:
        """Test that nested suppression works correctly."""
        history = CommandHistory()

        event1 = create_event(value=1, prev_value=0)
        event2 = create_event(value=2, prev_value=1)

        with history.suppress_recording():
            assert history.is_suppressed
            with history.suppress_recording():
                assert history.is_suppressed
                result1 = history.push(event1)
            # Still suppressed (outer context)
            assert history.is_suppressed
            result2 = history.push(event2)

        # No longer suppressed
        assert not history.is_suppressed

        assert result1 is False
        assert result2 is False
        assert not history.can_undo


class TestCommandHistoryFailure:
    """Tests for apply failure handling."""

    def test_undo_failure_keeps_stack(self) -> None:
        """Test undo failure keeps stack unchanged (HIS.01.05.G01.S07)."""
        history = CommandHistory()
        applier = MockApplier(should_fail=True)
        history.set_applier(applier)

        event = create_event(value=1, prev_value=0)
        history.push(event)

        result = history.undo()

        assert not result.success
        assert history.can_undo  # Stack unchanged
        assert not history.can_redo

    def test_pending_coalesce_undo_failure_restores_pending_sequence(self) -> None:
        """A failed Undo must preserve the pending event for later coalescing."""
        history = CommandHistory(coalesce_window_ms=500)
        applier = MockApplier(should_fail=True)
        history.set_applier(applier)
        history.push(create_event(value=1, prev_value=0, qualifier="nav"), coalesce=True)
        before = history.get_state()

        result = history.undo()

        assert not result.success
        assert history.get_state() == before

        applier.should_fail = False
        history.push(create_event(value=2, prev_value=1, qualifier="nav"), coalesce=True)
        assert history.get_state().undo_count == 1
        assert history.undo().success
        applied_event, is_undo = applier.applied_events[-1]
        assert is_undo
        assert isinstance(applied_event.command, _TestCommand)
        assert applied_event.command.before == 0
        assert applied_event.command.after == 2

    def test_pending_coalesce_undo_exception_restores_pending_sequence(self) -> None:
        """An exceptional Undo must restore the exact pending coalesce state."""
        history = CommandHistory(coalesce_window_ms=500)
        history.set_applier(MockApplierWithException())
        history.push(create_event(value=1, prev_value=0, qualifier="nav"), coalesce=True)
        before = history.get_state()

        with pytest.raises(RuntimeError, match="Test exception"):
            history.undo()

        assert history.get_state() == before

        applier = MockApplier()
        history.set_applier(applier)
        history.push(create_event(value=2, prev_value=1, qualifier="nav"), coalesce=True)
        assert history.undo().success
        applied_event, is_undo = applier.applied_events[-1]
        assert is_undo
        assert isinstance(applied_event.command, _TestCommand)
        assert applied_event.command.before == 0
        assert applied_event.command.after == 2

    def test_redo_failure_keeps_stack(self) -> None:
        """Test redo failure keeps stack unchanged."""
        history = CommandHistory()
        applier = MockApplier()
        history.set_applier(applier)

        event = create_event(value=1, prev_value=0)
        history.push(event)
        history.undo()
        before = history.get_state()

        # Now make applier fail
        applier.should_fail = True
        result = history.redo()

        assert not result.success
        assert history.get_state() == before

        applier.should_fail = False
        assert history.redo().success
        assert [is_undo for _event, is_undo in applier.applied_events] == [True, False, False]

    def test_redo_exception_propagates_and_keeps_stack(self) -> None:
        """An exceptional Redo must leave the event available for one retry."""
        history = CommandHistory()
        applier = MockApplier()
        history.set_applier(applier)
        history.push(create_event(value=1, prev_value=0))
        assert history.undo().success
        before = history.get_state()
        history.set_applier(MockApplierWithException())

        with pytest.raises(RuntimeError, match="Test exception"):
            history.redo()

        assert history.get_state() == before

        history.set_applier(applier)
        assert history.redo().success
        assert [is_undo for _event, is_undo in applier.applied_events] == [True, False]

    def test_exception_propagates_and_keeps_stack(self) -> None:
        """Test that applier exceptions propagate and keep stack unchanged."""
        history = CommandHistory()
        applier = MockApplierWithException()
        history.set_applier(applier)

        event = create_event(value=1, prev_value=0)
        history.push(event)

        with pytest.raises(RuntimeError, match="Test exception"):
            history.undo()

        assert history.can_undo  # Stack unchanged

    def test_no_applier_raises_and_keeps_stack(self) -> None:
        """Test that undo without applier fails fast and keeps stack unchanged."""
        history = CommandHistory()
        # No applier set

        event = create_event(value=1, prev_value=0)
        history.push(event)

        with pytest.raises(RuntimeError, match="History applier is required"):
            history.undo()

        assert history.can_undo  # Stack unchanged


class TestCommandHistoryTransitionGuard:
    """Tests for fail-fast Undo/Redo/Clear transition serialization."""

    @staticmethod
    def _history_with_undo_and_redo() -> CommandHistory:
        """Return history with one event on each stack."""
        history = CommandHistory()
        history.set_applier(MockApplier())
        history.push(create_event(value=1, prev_value=0))
        history.push(create_event(value=2, prev_value=1))
        assert history.undo().success
        state = history.get_state()
        assert state.undo_count == 1
        assert state.redo_count == 1
        return history

    def test_undo_rejects_reentrant_undo_before_second_apply(self) -> None:
        """A nested Undo must not apply the outer event twice."""
        history = CommandHistory()
        history.push(create_event(value=1, prev_value=0))
        applier = ReentrantApplier(history.undo)
        history.set_applier(applier)

        result = history.undo()

        assert result.success
        assert [is_undo for _event, is_undo in applier.applied_events] == [True]
        assert len(applier.nested_errors) == 1
        assert "history stack transition is already active" in str(applier.nested_errors[0])
        assert history.get_state().redo_count == 1

    def test_undo_rejects_reentrant_redo_before_second_apply(self) -> None:
        """A nested Redo must not interleave with an active Undo."""
        history = self._history_with_undo_and_redo()
        applier = ReentrantApplier(history.redo)
        history.set_applier(applier)

        result = history.undo()

        assert result.success
        assert [is_undo for _event, is_undo in applier.applied_events] == [True]
        assert len(applier.nested_errors) == 1
        assert history.get_state().undo_count == 0
        assert history.get_state().redo_count == 2

    def test_redo_rejects_reentrant_undo_before_second_apply(self) -> None:
        """A nested Undo must not interleave with an active Redo."""
        history = self._history_with_undo_and_redo()
        applier = ReentrantApplier(history.undo)
        history.set_applier(applier)

        result = history.redo()

        assert result.success
        assert [is_undo for _event, is_undo in applier.applied_events] == [False]
        assert len(applier.nested_errors) == 1
        assert history.get_state().undo_count == 2
        assert history.get_state().redo_count == 0

    def test_clear_rejects_reentrant_call_and_succeeds_after_apply(self) -> None:
        """Clear must not split applied science from its active history entry."""
        history = CommandHistory()
        history.push(create_event(value=1, prev_value=0))
        applier = ReentrantApplier(history.clear)
        history.set_applier(applier)

        assert history.undo().success
        assert len(applier.applied_events) == 1
        assert len(applier.nested_errors) == 1
        assert history.get_state().redo_count == 1

        history.clear()

        assert history.get_state().undo_count == 0
        assert history.get_state().redo_count == 0

    def test_applier_exception_releases_guard_for_retry(self) -> None:
        """An exceptional application must release the transition guard."""
        history = CommandHistory()
        history.push(create_event(value=1, prev_value=0))
        history.set_applier(MockApplierWithException())

        with pytest.raises(RuntimeError, match="Test exception"):
            history.undo()

        applier = MockApplier()
        history.set_applier(applier)
        assert history.undo().success
        assert len(applier.applied_events) == 1

    @pytest.mark.parametrize("competing_operation", ("push", "atomic_recording"))
    def test_blocked_undo_rejects_non_owner_stack_mutation(self, competing_operation: str) -> None:
        """Concurrent recording cannot split committed science from its stack transfer."""
        history = CommandHistory()
        history.push(create_event(value=1, prev_value=0))
        application_started = Event()
        competing_finished = Event()
        applied_events: list[tuple[HistoryEvent, bool]] = []
        worker_errors: list[Exception] = []

        def compete_with_undo() -> None:
            if not application_started.wait(timeout=5):
                worker_errors.append(RuntimeError("Timed out waiting for history application"))
                competing_finished.set()
                return
            try:
                if competing_operation == "push":
                    history.push(create_event(value=2, prev_value=1))
                else:
                    with history.atomic_recording():
                        pass
            except Exception as error:  # pragma: no cover - asserted in owner thread
                worker_errors.append(error)
            finally:
                competing_finished.set()

        class BlockingApplier:
            def apply_history_event(self, event: HistoryEvent, *, is_undo: bool) -> bool:
                applied_events.append((event, is_undo))
                application_started.set()
                if not competing_finished.wait(timeout=5):
                    raise RuntimeError("Timed out waiting for competing history mutation")
                return True

        history.set_applier(BlockingApplier())
        worker = Thread(target=compete_with_undo, name="history-owner-contract-test")
        worker.start()
        try:
            result = history.undo()
        finally:
            worker.join(timeout=5)

        assert not worker.is_alive()
        assert result.success
        assert len(applied_events) == 1
        assert len(worker_errors) == 1
        assert isinstance(worker_errors[0], HistoryOwnerThreadError)
        assert history.get_state().redo_count == 1

    def test_non_owner_query_is_a_typed_contract_violation(self) -> None:
        """History snapshots cannot be read concurrently with owner-thread mutations."""
        history = CommandHistory()
        worker_errors: list[Exception] = []

        def query() -> None:
            try:
                history.get_state()
            except Exception as error:  # pragma: no cover - asserted in owner thread
                worker_errors.append(error)

        worker = Thread(target=query, name="history-non-owner-query")
        worker.start()
        worker.join(timeout=5)

        assert not worker.is_alive()
        assert len(worker_errors) == 1
        assert isinstance(worker_errors[0], HistoryOwnerThreadError)


class TestCommandHistorySubscription:
    """Tests for state change subscription."""

    def test_subscribe_and_notify(self) -> None:
        """Test that subscribers are notified on state change."""
        history = CommandHistory()
        notifications: list[HistoryState] = []

        def callback(state: HistoryState) -> None:
            notifications.append(state)

        history.subscribe(callback)

        event = create_event(value=1, prev_value=0)
        history.push(event)

        assert len(notifications) == 1
        assert notifications[0].can_undo is True

    def test_unsubscribe(self) -> None:
        """Test that unsubscribed callbacks are not called."""
        history = CommandHistory()
        notifications: list[HistoryState] = []

        def callback(state: HistoryState) -> None:
            notifications.append(state)

        history.subscribe(callback)
        history.unsubscribe(callback)

        event = create_event(value=1, prev_value=0)
        history.push(event)

        assert len(notifications) == 0

    def test_unsubscribe_missing_callback_raises(self) -> None:
        """Test unsubscribing an unknown callback fails fast."""
        history = CommandHistory()

        def callback(state: HistoryState) -> None:
            pass

        with pytest.raises(ValueError):
            history.unsubscribe(callback)

    def test_multiple_subscribers(self) -> None:
        """Test multiple subscribers all receive notifications."""
        history = CommandHistory()
        notifications1: list[HistoryState] = []
        notifications2: list[HistoryState] = []

        def callback1(state: HistoryState) -> None:
            notifications1.append(state)

        def callback2(state: HistoryState) -> None:
            notifications2.append(state)

        history.subscribe(callback1)
        history.subscribe(callback2)

        event = create_event(value=1, prev_value=0)
        history.push(event)

        assert len(notifications1) == 1
        assert len(notifications2) == 1

    def test_callback_exception_propagates(self) -> None:
        """Test that subscriber exceptions are not hidden."""
        history = CommandHistory()
        notifications: list[HistoryState] = []

        def bad_callback(state: HistoryState) -> None:
            raise RuntimeError("Callback error")

        def good_callback(state: HistoryState) -> None:
            notifications.append(state)

        history.subscribe(bad_callback)
        history.subscribe(good_callback)

        event = create_event(value=1, prev_value=0)
        with pytest.raises(RuntimeError, match="Callback error"):
            history.push(event)

        assert len(notifications) == 0

    def test_successful_undo_redo_isolates_each_subscriber_failure(self) -> None:
        """Committed Undo/Redo must survive one failed state observer."""
        history = CommandHistory()
        applier = MockApplier()
        history.set_applier(applier)
        history.push(create_event(value=1, prev_value=0))
        bad_calls: list[HistoryState] = []
        first_notifications: list[HistoryState] = []
        second_notifications: list[HistoryState] = []

        def fail(state: HistoryState) -> None:
            bad_calls.append(state)
            raise RuntimeError("observer failed")

        history.subscribe(fail)
        history.subscribe(first_notifications.append)
        history.subscribe(second_notifications.append)

        assert history.undo().success
        undo_state = history.get_state()
        assert bad_calls == [undo_state]
        assert first_notifications == [undo_state]
        assert second_notifications == [undo_state]
        assert len(applier.applied_events) == 1

        empty_undo = history.undo()
        assert not empty_undo.success
        assert len(applier.applied_events) == 1

        assert history.redo().success
        redo_state = history.get_state()
        assert bad_calls == [undo_state, redo_state]
        assert first_notifications == [undo_state, redo_state]
        assert second_notifications == [undo_state, redo_state]
        assert len(applier.applied_events) == 2

    def test_failed_undo_isolates_observers_after_exact_restore(self) -> None:
        """Failure observers must see the restored state without breaking retry."""
        history = CommandHistory()
        applier = MockApplier(should_fail=True)
        history.set_applier(applier)
        history.push(create_event(value=1, prev_value=0))
        before = history.get_state()
        notifications: list[HistoryState] = []

        def fail(_state: HistoryState) -> None:
            raise RuntimeError("observer failed")

        history.subscribe(fail)
        history.subscribe(notifications.append)

        result = history.undo()

        assert not result.success
        assert history.get_state() == before
        assert notifications == [before]

        applier.should_fail = False
        assert history.undo().success
        assert len(applier.applied_events) == 2

    def test_exceptional_redo_preserves_original_error_and_notifies_all(self) -> None:
        """Observer failures must not replace the applier error after restore."""
        history = CommandHistory()
        history.set_applier(MockApplier())
        history.push(create_event(value=1, prev_value=0))
        assert history.undo().success
        before = history.get_state()
        history.set_applier(MockApplierWithException())
        notifications: list[HistoryState] = []

        def fail(_state: HistoryState) -> None:
            raise ValueError("observer failed")

        history.subscribe(fail)
        history.subscribe(notifications.append)

        with pytest.raises(RuntimeError, match="Test exception"):
            history.redo()

        assert history.get_state() == before
        assert notifications == [before]


class TestCommandHistoryState:
    """Tests for state query."""

    def test_get_state_empty(self) -> None:
        """Test get_state on empty history."""
        history = CommandHistory()
        state = history.get_state()

        assert not state.can_undo
        assert not state.can_redo
        assert state.undo_count == 0
        assert state.redo_count == 0
        assert state.next_undo_operation_id is None
        assert state.next_redo_operation_id is None

    def test_get_state_with_events(self) -> None:
        """Test get_state with events in stack."""
        history = CommandHistory()
        applier = MockApplier()
        history.set_applier(applier)

        event1 = create_event(value=1, prev_value=0)
        event2 = create_event(value=2, prev_value=1)

        history.push(event1)
        history.push(event2)

        state = history.get_state()
        assert state.can_undo
        assert not state.can_redo
        assert state.undo_count == 2
        assert state.next_undo_operation_id == "draw.range_change"

        # Undo one
        history.undo()

        state = history.get_state()
        assert state.can_undo
        assert state.can_redo
        assert state.undo_count == 1
        assert state.redo_count == 1
        assert state.next_undo_operation_id == "draw.range_change"
        assert state.next_redo_operation_id == "draw.range_change"


class TestHistoryEventProperties:
    """Tests for HistoryEvent properties."""

    def test_full_operation_id_without_qualifier(self) -> None:
        """Test full_operation_id without qualifier."""
        event = create_event()

        assert event.full_operation_id == "draw.range_change"

    def test_full_operation_id_with_qualifier(self) -> None:
        """Test full_operation_id with qualifier."""
        event = create_event(qualifier="nav")

        assert event.full_operation_id == "draw.range_change.nav"

    def test_coalesced_with(self) -> None:
        """Test coalesced_with creates new event with merged command."""
        original = create_event(value=1, prev_value=0, qualifier="nav")
        next_event = create_event(value=2, prev_value=1, qualifier="nav")

        updated = original.coalesced_with(next_event)

        assert updated is not None
        assert isinstance(updated.command, _TestCommand)
        assert updated.command.before == 0
        assert updated.command.after == 2
        assert updated.created_at == original.created_at
        assert updated.operation_id == original.operation_id


class TestCommandHistoryCoalesce:
    """Tests for coalesce functionality."""

    def test_coalesce_within_window(self) -> None:
        """Test that consecutive operations within window are coalesced."""
        current_time = 0.0
        time_calls: list[float] = []

        def mock_time() -> float:
            if time_calls:
                return time_calls[-1]
            return current_time

        history = CommandHistory(coalesce_window_ms=500, time_provider=mock_time)

        event1 = create_event(value=1, prev_value=0, qualifier="nav")
        event2 = create_event(value=2, prev_value=1, qualifier="nav")

        time_calls.append(0.0)
        history.push(event1, coalesce=True)

        # 100ms later
        time_calls.append(0.1)
        history.push(event2, coalesce=True)

        state = history.get_state()
        # Should be coalesced into 1 entry
        assert state.undo_count == 1

    def test_coalesce_expires_after_window(self) -> None:
        """Test that operations after window are not coalesced."""
        current_time = 0.0
        time_calls: list[float] = []

        def mock_time() -> float:
            if time_calls:
                return time_calls[-1]
            return current_time

        history = CommandHistory(coalesce_window_ms=500, time_provider=mock_time)

        event1 = create_event(value=1, prev_value=0, qualifier="nav")
        event2 = create_event(value=2, prev_value=1, qualifier="nav")

        time_calls.append(0.0)
        history.push(event1, coalesce=True)

        # 600ms later (window expired)
        time_calls.append(0.6)
        history.push(event2, coalesce=True)

        state = history.get_state()
        # Should be 2 separate entries
        assert state.undo_count == 2

    def test_coalesce_different_operation_not_merged(self) -> None:
        """Test that different operation types are not coalesced."""
        history = CommandHistory(coalesce_window_ms=500)

        event1 = create_event(value=1, prev_value=0, qualifier="nav")
        event2 = HistoryEvent(
            command=_TestCommand(before=1, after=2, op_id=OperationId.CONT_MOVE_POINT)
        )

        history.push(event1, coalesce=True)
        history.push(event2, coalesce=True)

        state = history.get_state()
        assert state.undo_count == 2

    def test_coalesce_different_qualifier_not_merged(self) -> None:
        """Test that different qualifiers are not coalesced."""
        history = CommandHistory(coalesce_window_ms=500)

        event1 = create_event(value=1, prev_value=0, qualifier="nav")
        event2 = create_event(value=2, prev_value=1, qualifier="manual")

        history.push(event1, coalesce=True)
        history.push(event2, coalesce=True)

        state = history.get_state()
        assert state.undo_count == 2

    def test_coalesce_preserves_original_inverse(self) -> None:
        """Test that coalesce preserves the original before state."""
        current_time = 0.0
        time_calls: list[float] = []

        def mock_time() -> float:
            if time_calls:
                return time_calls[-1]
            return current_time

        history = CommandHistory(coalesce_window_ms=500, time_provider=mock_time)
        applier = MockApplier()
        history.set_applier(applier)

        # First event: 0 -> 1
        event1 = create_event(value=1, prev_value=0, qualifier="nav")
        time_calls.append(0.0)
        history.push(event1, coalesce=True)

        # Second event: 1 -> 2 (coalesced)
        event2 = create_event(value=2, prev_value=1, qualifier="nav")
        time_calls.append(0.1)
        history.push(event2, coalesce=True)

        # Third event: 2 -> 3 (coalesced)
        event3 = create_event(value=3, prev_value=2, qualifier="nav")
        time_calls.append(0.2)
        history.push(event3, coalesce=True)

        # After undo, should go back to original state (0)
        result = history.undo()
        assert result.success

        applied_event, is_undo = applier.applied_events[0]
        assert is_undo is True
        assert isinstance(applied_event.command, _TestCommand)
        assert applied_event.command.before == 0
        assert applied_event.command.after == 3

    def test_non_coalesce_commits_pending(self) -> None:
        """Test that non-coalesce push commits pending coalesce."""
        history = CommandHistory(coalesce_window_ms=500)

        event1 = create_event(value=1, prev_value=0, qualifier="nav")
        event2 = create_event(value=2, prev_value=1)  # No coalesce

        history.push(event1, coalesce=True)
        history.push(event2, coalesce=False)

        state = history.get_state()
        assert state.undo_count == 2

    def test_coalesce_to_noop_removes_entry(self) -> None:
        """Test that coalescing to a no-op removes the entry from history."""
        current_time = 0.0
        time_calls: list[float] = []

        def mock_time() -> float:
            if time_calls:
                return time_calls[-1]
            return current_time

        history = CommandHistory(coalesce_window_ms=500, time_provider=mock_time)

        # First event: 0 -> 1
        event1 = create_event(value=1, prev_value=0, qualifier="nav")
        time_calls.append(0.0)
        history.push(event1, coalesce=True)

        state = history.get_state()
        assert state.undo_count == 1

        # Second event: 1 -> 0 (returns to original state within coalesce window)
        event2 = create_event(value=0, prev_value=1, qualifier="nav")
        time_calls.append(0.1)
        result = history.push(event2, coalesce=True)

        # Should return False because merged result is a no-op
        assert result is False

        # History should be empty (no-op removed)
        state = history.get_state()
        assert state.undo_count == 0
        assert not state.can_undo

    def test_coalesce_clears_redo_on_merge(self) -> None:
        """Test that coalesce merge clears redo stack."""
        current_time = 0.0
        time_calls: list[float] = []

        def mock_time() -> float:
            if time_calls:
                return time_calls[-1]
            return current_time

        history = CommandHistory(coalesce_window_ms=500, time_provider=mock_time)
        applier = MockApplier()
        history.set_applier(applier)

        # Push and undo to create redo entry
        event1 = create_event(value=1, prev_value=0)
        history.push(event1)
        history.undo()

        assert history.can_redo

        # Now push with coalesce - should clear redo
        event2 = create_event(value=2, prev_value=0, qualifier="nav")
        time_calls.append(0.0)
        history.push(event2, coalesce=True)

        # Redo should be cleared
        assert not history.can_redo
        # Push another coalescing event - merge should also clear redo
        history.undo()
        assert history.can_redo

        event3 = create_event(value=3, prev_value=2, qualifier="nav")
        time_calls.append(0.1)
        history.push(event3, coalesce=True)

        # Redo should be cleared by merge
        assert not history.can_redo


def test_atomic_recording_restores_preexisting_redo_stack() -> None:
    """An aborted compound record must preserve a real pre-existing Redo path."""
    history = CommandHistory()
    applier = MockApplier()
    history.set_applier(applier)
    history.push(create_event(value=1, prev_value=0))
    assert history.undo().success
    assert history.get_state().redo_count == 1
    before = history.get_state()

    with pytest.raises(RuntimeError, match="recording failed"):
        with history.atomic_recording():
            history.push(create_event(value=2, prev_value=0))
            raise RuntimeError("recording failed")

    assert history.get_state() == before


def test_atomic_recording_restores_pending_coalesce_state() -> None:
    """An aborted compound record must preserve the pending coalescing event."""
    history = CommandHistory()
    history.push(create_event(value=2, prev_value=0, qualifier="nav"), coalesce=True)
    before = history.get_state()

    with pytest.raises(RuntimeError, match="recording failed"):
        with history.atomic_recording():
            history.push(create_event(value=3, prev_value=2))
            raise RuntimeError("recording failed")

    assert history.get_state() == before


def test_atomic_recording_notifies_only_after_successful_commit() -> None:
    """Observers must never see a stack state that an atomic scope rolls back."""
    history = CommandHistory()
    notifications: list[HistoryState] = []
    history.subscribe(notifications.append)

    with pytest.raises(RuntimeError, match="recording failed"):
        with history.atomic_recording():
            history.push(create_event(value=1, prev_value=0))
            assert notifications == []
            raise RuntimeError("recording failed")

    assert notifications == []
    assert history.get_state().undo_count == 0

    with history.atomic_recording():
        history.push(create_event(value=2, prev_value=0))
        assert notifications == []

    assert notifications == [history.get_state()]


def test_atomic_recording_commits_even_when_one_observer_fails() -> None:
    """A post-commit observer failure must not roll back a scientific history entry."""
    history = CommandHistory()
    notifications: list[HistoryState] = []

    def fail(_state: HistoryState) -> None:
        raise RuntimeError("observer failed")

    history.subscribe(fail)
    history.subscribe(notifications.append)

    with history.atomic_recording():
        history.push(create_event(value=1, prev_value=0))

    assert history.get_state().undo_count == 1
    assert notifications == [history.get_state()]


def test_failed_undo_restores_deferred_notification_state() -> None:
    """A failed Undo must preserve a surrounding atomic scope's pending notice."""
    history = CommandHistory()
    history.set_applier(MockApplier(should_fail=True))
    notifications: list[HistoryState] = []
    history.subscribe(notifications.append)

    with history.atomic_recording():
        history.push(create_event(value=1, prev_value=0, qualifier="nav"), coalesce=True)
        before_undo = history.get_state()

        result = history.undo()

        assert not result.success
        assert history.get_state() == before_undo
        assert notifications == []

    assert notifications == [before_undo]


def test_nested_atomic_recording_success_notifies_once_at_outer_commit() -> None:
    """Nested successful scopes must publish only their final outer state."""
    history = CommandHistory()
    notifications: list[HistoryState] = []
    history.subscribe(notifications.append)

    with history.atomic_recording():
        history.push(create_event(value=1, prev_value=0))
        with history.atomic_recording():
            history.push(create_event(value=2, prev_value=1))
        assert notifications == []

    assert history.get_state().undo_count == 2
    assert notifications == [history.get_state()]


def test_nested_atomic_recording_inner_rollback_can_be_caught_by_outer() -> None:
    """A caught inner failure must restore only the inner recording snapshot."""
    history = CommandHistory()
    notifications: list[HistoryState] = []
    history.subscribe(notifications.append)

    with history.atomic_recording():
        history.push(create_event(value=1, prev_value=0))
        try:
            with history.atomic_recording():
                history.push(create_event(value=2, prev_value=1))
                raise RuntimeError("inner recording failed")
        except RuntimeError as error:
            assert str(error) == "inner recording failed"
        assert history.get_state().undo_count == 1
        history.push(create_event(value=3, prev_value=1))

    assert history.get_state().undo_count == 2
    assert notifications == [history.get_state()]


def test_nested_atomic_recording_outer_rollback_restores_pre_nested_state() -> None:
    """An outer failure must discard a previously successful inner scope."""
    history = CommandHistory()
    applier = MockApplier()
    history.set_applier(applier)
    history.push(create_event(value=1, prev_value=0))
    assert history.undo().success
    before = history.get_state()
    notifications: list[HistoryState] = []
    history.subscribe(notifications.append)

    with pytest.raises(RuntimeError, match="outer recording failed"):
        with history.atomic_recording():
            history.push(create_event(value=2, prev_value=0))
            with history.atomic_recording():
                history.push(create_event(value=3, prev_value=2))
            raise RuntimeError("outer recording failed")

    assert history.get_state() == before
    assert notifications == []
