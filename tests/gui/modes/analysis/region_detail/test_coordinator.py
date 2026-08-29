"""Tests for optimize mode coordinator."""

from __future__ import annotations

from collections.abc import Callable
from typing import Generic, TypeVar

from chappy.gui.modes.analysis.region_detail.coordinator import OptimizeModeCoordinator

T = TypeVar("T")


class _Signal0:
    """Small signal test double without Qt runtime state."""

    def __init__(self) -> None:
        self._callbacks: list[Callable[[], None]] = []

    def connect(self, callback: Callable[[], None]) -> None:
        """Store a zero-argument callback."""
        self._callbacks.append(callback)

    def emit(self) -> None:
        """Invoke connected callbacks."""
        for callback in self._callbacks:
            callback()


class _Signal1(Generic[T]):
    """Small one-argument signal test double without Qt runtime state."""

    def __init__(self) -> None:
        self._callbacks: list[Callable[[T], None]] = []

    def connect(self, callback: Callable[[T], None]) -> None:
        """Store a one-argument callback."""
        self._callbacks.append(callback)

    def emit(self, value: T) -> None:
        """Invoke connected callbacks."""
        for callback in self._callbacks:
            callback(value)


class _Editor:
    """Editor signal test double."""

    def __init__(self) -> None:
        self.fit_started = _Signal0()
        self.fit_completed = _Signal1[dict[str, bool]]()


class _ModeState:
    """Mode state signal test double."""

    def __init__(self) -> None:
        self.group_removed = _Signal1[str]()


class _Panel:
    """Coordinator panel handoff test double."""

    def __init__(self) -> None:
        self.fit_started_count = 0
        self.fit_completed_payloads: list[dict[str, bool]] = []
        self.removed_groups: list[str] = []

    def handle_editor_fit_started(self) -> None:
        """Record fit-start handoff."""
        self.fit_started_count += 1

    def handle_editor_fit_completed(self, results: dict[str, bool]) -> None:
        """Record fit-completed handoff."""
        self.fit_completed_payloads.append(results)

    def handle_mode_group_removed(self, group_name: str) -> None:
        """Record group-removed handoff."""
        self.removed_groups.append(group_name)


def test_connect_routes_editor_and_mode_state_signals() -> None:
    """Coordinator should route external signals to panel handoff methods."""
    editor = _Editor()
    mode_state = _ModeState()
    panel = _Panel()
    coordinator = OptimizeModeCoordinator(panel=panel, editor=editor, mode_state=mode_state)

    coordinator.connect()
    editor.fit_started.emit()
    editor.fit_completed.emit({"success": True})
    mode_state.group_removed.emit("region-1")

    assert panel.fit_started_count == 1
    assert panel.fit_completed_payloads == [{"success": True}]
    assert panel.removed_groups == ["region-1"]


def test_connect_is_idempotent() -> None:
    """Repeated coordinator connection should not duplicate signal handlers."""
    editor = _Editor()
    panel = _Panel()
    coordinator = OptimizeModeCoordinator(panel=panel, editor=editor)

    coordinator.connect()
    coordinator.connect()
    editor.fit_started.emit()

    assert panel.fit_started_count == 1
