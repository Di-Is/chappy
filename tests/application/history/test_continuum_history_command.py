"""Tests for typed continuum history commands."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from chappy.application.history import (
    ChangeSet,
    ContinuumAddComponentCommand,
    ContinuumAddPointCommand,
    ContinuumComponentSnapshot,
    ContinuumDeletePointCommand,
    ContinuumMovePointCommand,
    ContinuumPointSnapshot,
    ContinuumResetCommand,
    HistoryCommandContext,
)


@dataclass(slots=True)
class _ContinuumPort:
    """Continuum history port test double."""

    added_components: list[tuple[ContinuumComponentSnapshot, int]] = field(default_factory=list)
    removed_components: list[str] = field(default_factory=list)
    replaced: list[tuple[str, tuple[ContinuumPointSnapshot, ...]]] = field(default_factory=list)

    def add_continuum_component(
        self, snapshot: ContinuumComponentSnapshot, *, index: int
    ) -> ChangeSet:
        """Record a recreated continuum component."""
        self.added_components.append((snapshot, index))
        return ChangeSet(changed_continuum_ids=(snapshot.component_id,))

    def remove_continuum_component(self, continuum_id: str) -> ChangeSet:
        """Record a removed continuum component."""
        self.removed_components.append(continuum_id)
        return ChangeSet(changed_continuum_ids=(continuum_id,))

    def replace_continuum_points(
        self, continuum_id: str, points: tuple[ContinuumPointSnapshot, ...]
    ) -> ChangeSet:
        """Record replaced points."""
        self.replaced.append((continuum_id, points))
        return ChangeSet(changed_continuum_ids=(continuum_id,))


def _point(wavelength: float, flux: float) -> ContinuumPointSnapshot:
    """Create one continuum point snapshot."""
    return ContinuumPointSnapshot(wavelength=wavelength, flux=flux)


def test_continuum_add_component_command_redo_and_undo_component() -> None:
    """Component-add history should recreate and remove one stable component."""
    port = _ContinuumPort()
    context = HistoryCommandContext(continuum_port=port)
    snapshot = ContinuumComponentSnapshot(
        component_id="continuum-1",
        name="Continuum 1",
        enabled=True,
        is_shared_with_absorption=True,
        points=(_point(1215.67, 1.0),),
    )
    command = ContinuumAddComponentCommand(snapshot=snapshot, component_index=2)

    assert command.redo(context).success
    assert command.undo(context).success

    assert port.added_components == [(snapshot, 2)]
    assert port.removed_components == [snapshot.component_id]


def test_continuum_add_command_redo_adds_and_undo_removes_point() -> None:
    """Add command should add on redo and remove on undo."""
    port = _ContinuumPort()
    context = HistoryCommandContext(continuum_port=port)
    before = (_point(1200.0, 1.0),)
    after = (*before, _point(1215.67, 1.02))
    command = ContinuumAddPointCommand(continuum_id="cont-1", before=before, after=after)

    assert command.redo(context).success
    assert command.undo(context).success

    assert port.replaced == [("cont-1", after), ("cont-1", before)]


def test_continuum_delete_command_redo_removes_and_undo_adds_point() -> None:
    """Delete command should remove on redo and add on undo."""
    port = _ContinuumPort()
    context = HistoryCommandContext(continuum_port=port)
    before = (_point(1200.0, 1.0), _point(1300.0, 0.98))
    after = before[:1]
    command = ContinuumDeletePointCommand(continuum_id="cont-1", before=before, after=after)

    assert command.redo(context).success
    assert command.undo(context).success

    assert port.replaced == [("cont-1", after), ("cont-1", before)]


def test_continuum_move_command_redo_and_undo_swap_positions() -> None:
    """Move command should apply after on redo and before on undo."""
    port = _ContinuumPort()
    context = HistoryCommandContext(continuum_port=port)
    before = (_point(1400.0, 1.0),)
    after = (_point(1410.0, 1.1),)
    command = ContinuumMovePointCommand(continuum_id="cont-1", before=before, after=after)

    assert command.redo(context).success
    assert command.undo(context).success

    assert port.replaced == [("cont-1", after), ("cont-1", before)]


def test_continuum_reset_command_redo_and_undo_replace_points() -> None:
    """Reset command should replace with after on redo and before on undo."""
    port = _ContinuumPort()
    context = HistoryCommandContext(continuum_port=port)
    before = (_point(1000.0, 1.0), _point(1100.0, 1.0), _point(1200.0, 1.0))
    after = (_point(1000.0, 0.9), _point(1100.0, 1.1), _point(1200.0, 0.95))
    command = ContinuumResetCommand(continuum_id="cont-1", before=before, after=after)

    assert command.redo(context).success
    assert command.undo(context).success

    assert port.replaced == [("cont-1", after), ("cont-1", before)]


def test_continuum_commands_fail_fast_without_port() -> None:
    """Continuum command should fail fast when no port is configured."""
    points = (_point(1215.67, 1.0),)
    command = ContinuumAddPointCommand(continuum_id="cont-1", before=(), after=points)

    with pytest.raises(RuntimeError, match="Continuum history port is required"):
        command.redo(HistoryCommandContext())


def test_continuum_move_and_reset_noop_detection() -> None:
    """Move and reset commands should report equal snapshots as no-op."""
    point = _point(1215.67, 1.0)
    move_command = ContinuumMovePointCommand(
        continuum_id="cont-1", before=(point,), after=(point,)
    )
    reset_command = ContinuumResetCommand(continuum_id="cont-1", before=(point,), after=(point,))

    assert move_command.is_noop()
    assert reset_command.is_noop()
