"""Tests for shared typed history command models."""

from __future__ import annotations

import pytest

from chappy.application.history import HistoryCommandContext
from chappy.application.history.range_commands import RangeHistoryCommand
from chappy.application.history.ports import RangeSnapshot


def test_required_port_absence_fails_fast() -> None:
    """Command should fail fast when the required port is absent."""
    command = RangeHistoryCommand(
        before=RangeSnapshot(wavelength_range=(1.0, 2.0)),
        after=RangeSnapshot(wavelength_range=(2.0, 3.0)),
    )

    with pytest.raises(RuntimeError, match="Range history port is required"):
        command.redo(HistoryCommandContext())
