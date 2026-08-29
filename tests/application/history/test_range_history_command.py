"""Tests for typed spectrum range history commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from chappy.application.history import (
    ChangeSet,
    HistoryApplyError,
    HistoryApplyErrorCode,
    HistoryCommandContext,
    RangeHistoryCommand,
    RangeSnapshot,
)
import pytest


@dataclass(slots=True)
class _RangePort:
    """Range history port test double."""

    calls: list[tuple[RangeSnapshot, Literal["history"]]] = field(default_factory=list)

    def apply_range(self, snapshot: RangeSnapshot, *, source: Literal["history"]) -> ChangeSet:
        """Record the applied snapshot."""
        self.calls.append((snapshot, source))
        return ChangeSet.empty()


def test_range_command_redo_and_undo_apply_after_and_before() -> None:
    """Range command should apply after snapshot on redo and before snapshot on undo."""
    port = _RangePort()
    context = HistoryCommandContext(range_port=port)
    before = RangeSnapshot(wavelength_range=(1000.0, 2000.0), flux_range=None)
    after = RangeSnapshot(wavelength_range=(1500.0, 2500.0), flux_range=(-1.0, 2.0))
    command = RangeHistoryCommand(before=before, after=after, qualifier="interactor")

    redo_result = command.redo(context)
    undo_result = command.undo(context)

    assert redo_result.success
    assert undo_result.success
    assert port.calls == [(after, "history"), (before, "history")]


def test_range_command_coalesces_first_before_and_latest_after() -> None:
    """Coalesced range command should keep the first before and latest after."""
    first = RangeHistoryCommand(
        before=RangeSnapshot(wavelength_range=(1000.0, 2000.0)),
        after=RangeSnapshot(wavelength_range=(1200.0, 2200.0)),
        qualifier="intent",
    )
    second = RangeHistoryCommand(
        before=RangeSnapshot(wavelength_range=(1200.0, 2200.0)),
        after=RangeSnapshot(wavelength_range=(1400.0, 2400.0)),
        qualifier="intent",
    )

    merged = first.coalesced_with(second)

    assert merged == RangeHistoryCommand(
        before=RangeSnapshot(wavelength_range=(1000.0, 2000.0)),
        after=RangeSnapshot(wavelength_range=(1400.0, 2400.0)),
        qualifier="intent",
    )


def test_range_command_reports_noop_for_equal_snapshots() -> None:
    """Equal before and after snapshots should be no-op."""
    snapshot = RangeSnapshot(wavelength_range=(1000.0, 2000.0), flux_range=(0.0, 1.0))
    command = RangeHistoryCommand(before=snapshot, after=snapshot)

    assert command.is_noop()


class _FailingRangePort:
    """Range history port that raises a configured apply error."""

    def __init__(self, error_code: HistoryApplyErrorCode) -> None:
        """Initialize the failing port."""
        self._error_code = error_code

    def apply_range(self, snapshot: RangeSnapshot, *, source: Literal["history"]) -> ChangeSet:
        """Raise the configured apply error."""
        _ = snapshot, source
        raise HistoryApplyError(self._error_code, self._error_code.value)


def test_range_command_target_not_found_returns_failed_result() -> None:
    """Stale history targets remain recoverable failed apply results."""
    context = HistoryCommandContext(
        range_port=_FailingRangePort(HistoryApplyErrorCode.TARGET_NOT_FOUND)
    )
    command = RangeHistoryCommand(
        before=RangeSnapshot(wavelength_range=(1000.0, 2000.0)),
        after=RangeSnapshot(wavelength_range=(1500.0, 2500.0)),
    )

    result = command.redo(context)

    assert not result.success
    assert result.error_code is HistoryApplyErrorCode.TARGET_NOT_FOUND


def test_range_command_invalid_state_propagates() -> None:
    """Internal history port failures are not downgraded to recoverable results."""
    context = HistoryCommandContext(
        range_port=_FailingRangePort(HistoryApplyErrorCode.INVALID_STATE)
    )
    command = RangeHistoryCommand(
        before=RangeSnapshot(wavelength_range=(1000.0, 2000.0)),
        after=RangeSnapshot(wavelength_range=(1500.0, 2500.0)),
    )

    with pytest.raises(HistoryApplyError, match="invalid_state"):
        command.redo(context)
