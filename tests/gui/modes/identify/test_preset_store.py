"""Tests for the identify preset-store Qt facade."""

from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from chappy.core.atomic_data import AtomicLine, AtomicLineData
from chappy.infrastructure.preset_store import PersistentPresetStore
from chappy.gui.modes.identify.presets.preset_store import IdentifyPresetStore

pytestmark = pytest.mark.usefixtures("qapp")


def _line(identifier: str, wavelength: float) -> AtomicLine:
    """Build a minimal atomic line."""
    return AtomicLine(
        line_identifier=identifier,
        species="C IV",
        wavelength_angstrom=wavelength,
        oscillator_strength=0.1,
        gamma_value=1.0,
        transition_name=identifier,
    )


def _facade(tmp_path: Path) -> tuple[IdentifyPresetStore, str]:
    """Build a facade backed by a temporary persistent store."""
    atomic_data = AtomicLineData([_line("a", 1548.2), _line("b", 1550.8)])
    store = PersistentPresetStore(
        atomic_data, storage_path=tmp_path / "presets.json", translate=lambda text: text
    )
    preset = store.create_custom_preset("Custom", line_ids=["a", "b"])
    return IdentifyPresetStore(store), preset.id


def test_add_replace_remove_tie_group_delegates_and_emits_once(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """Facade group operations emit one update after each successful mutation."""
    facade, preset_id = _facade(tmp_path)

    with qtbot.waitSignal(facade.preset_updated, timeout=1000) as added_signal:
        group = facade.add_tie_group(preset_id, ["a", "b"])
    assert added_signal.args == [preset_id]

    with qtbot.waitSignal(facade.preset_updated, timeout=1000) as replaced_signal:
        replacement = facade.replace_tie_group_members(preset_id, group.uid, ["a", "b"])
    assert replacement.uid == group.uid
    assert replaced_signal.args == [preset_id]

    with qtbot.waitSignal(facade.preset_updated, timeout=1000) as removed_signal:
        facade.remove_tie_group(preset_id, group.uid)
    assert removed_signal.args == [preset_id]


def test_facade_does_not_emit_when_underlying_group_operation_fails(tmp_path: Path) -> None:
    """Underlying validation errors must not produce a false update signal."""
    facade, preset_id = _facade(tmp_path)
    emitted: list[str] = []
    facade.preset_updated.connect(emitted.append)

    with pytest.raises(ValueError):
        facade.add_tie_group(preset_id, ["a"])

    assert emitted == []
