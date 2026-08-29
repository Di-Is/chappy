"""Tests for typed range history command application through HistoryApplyUseCase."""

from __future__ import annotations

from chappy.application.history import (
    HistoryApplyError,
    HistoryApplyErrorCode,
    RangeHistoryCommand,
    RangeSnapshot,
)
from chappy.core.history import CommandHistory, HistoryEvent
import pytest

from history_apply_fakes import FakeRangeHistoryPort, build_usecase


def test_typed_range_command_applies_through_range_port() -> None:
    """Undo and redo should route typed range snapshots to the range port."""
    history = CommandHistory()
    range_port = FakeRangeHistoryPort()
    usecase = build_usecase(project_provider=lambda: None, range_port=range_port)
    history.set_applier(usecase)
    event = HistoryEvent(
        command=RangeHistoryCommand(
            before=RangeSnapshot(wavelength_range=(1000.0, 2000.0), flux_range=None),
            after=RangeSnapshot(wavelength_range=(1500.0, 2500.0), flux_range=(-1.0, 2.0)),
            qualifier="intent",
        )
    )

    assert history.push(event)
    assert history.undo().success
    assert history.redo().success

    assert range_port.calls == [
        (RangeSnapshot(wavelength_range=(1000.0, 2000.0), flux_range=None), "history"),
        (RangeSnapshot(wavelength_range=(1500.0, 2500.0), flux_range=(-1.0, 2.0)), "history"),
    ]


def test_typed_range_apply_failure_keeps_history_stack() -> None:
    """A failing range port should fail range undo without advancing history."""
    history = CommandHistory()
    range_port = FakeRangeHistoryPort(
        error=HistoryApplyError(HistoryApplyErrorCode.TARGET_NOT_FOUND, "target_not_found")
    )
    usecase = build_usecase(project_provider=lambda: None, range_port=range_port)
    history.set_applier(usecase)
    event = HistoryEvent(
        command=RangeHistoryCommand(
            before=RangeSnapshot(wavelength_range=(1000.0, 2000.0), flux_range=None),
            after=RangeSnapshot(wavelength_range=(1500.0, 2500.0), flux_range=(-1.0, 2.0)),
            qualifier="intent",
        )
    )

    assert history.push(event)
    with pytest.raises(HistoryApplyError, match="target_not_found"):
        history.undo()

    assert history.can_undo
    assert not history.can_redo
