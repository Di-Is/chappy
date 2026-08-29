"""Tests for required continuum production history wiring boundaries."""

from __future__ import annotations

import pytest

from chappy.core.components.continuum import ContinuumComponent
from chappy.gui.modes.continuum.history_adapter import ContinuumHistoryAdapter


def test_missing_recorder_rejects_atomic_scientific_mutation_scope() -> None:
    """Production mutations must not receive a silent no-op history scope."""
    adapter = ContinuumHistoryAdapter(recorder_provider=lambda: None)

    with pytest.raises(RuntimeError, match="require a connected history recorder"):
        adapter.atomic_recording()


def test_missing_recorder_rejects_component_command_recording() -> None:
    """Production component creation must not silently omit its command."""
    adapter = ContinuumHistoryAdapter(recorder_provider=lambda: None)

    with pytest.raises(RuntimeError, match="require a connected history recorder"):
        adapter.record_add_component(ContinuumComponent("Continuum 1"))
