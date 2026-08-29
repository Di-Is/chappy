"""Focused tests for ModeToolbarController."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import pytest

from chappy.core.editing_mode import EditingMode
from chappy.gui.shell.actions.ids import ShellActionId
from chappy.gui.shell.mode_toolbar_controller import ModeToolbarController


class _Signal:
    def __init__(self) -> None:
        self._callbacks: list[Callable[..., None]] = []

    def connect(self, callback: Callable[..., None]) -> None:
        self._callbacks.append(callback)

    def emit(self, *args: object) -> None:
        for callback in list(self._callbacks):
            callback(*args)


class _Action:
    def __init__(self) -> None:
        self.triggered = 0

    def trigger(self) -> None:
        self.triggered += 1


@dataclass
class _ContextBar:
    toolbar_action_triggered: _Signal = field(default_factory=_Signal)
    zoom_rect_toggled: _Signal = field(default_factory=_Signal)
    mode_switch_requested: _Signal = field(default_factory=_Signal)
    zoom_active: bool = False
    current_mode: EditingMode | None = None
    project_loaded: bool = False
    config: object | None = None

    def set_zoom_mode_active(self, active: bool) -> None:
        self.zoom_active = active

    def apply_config(self, config: object) -> None:
        self.config = config

    def set_current_mode(self, mode: EditingMode) -> None:
        self.current_mode = mode

    def set_project_loaded(self, loaded: bool) -> None:
        self.project_loaded = loaded


def test_mode_toolbar_controller_triggers_registered_toolbar_action() -> None:
    """Toolbar intent should trigger the registered shell action."""
    open_project = _Action()
    controller = ModeToolbarController(
        action_map_provider=lambda: {ShellActionId.OPEN_PROJECT: open_project},
        zoom_rect_toggle_callback=lambda _enabled: None,
    )

    controller.handle_toolbar_action(ShellActionId.OPEN_PROJECT)

    assert open_project.triggered == 1


def test_mode_toolbar_controller_rejects_unknown_mode_switch() -> None:
    """Only explicit mode-switch actions should be accepted."""
    controller = ModeToolbarController(
        action_map_provider=lambda: {}, zoom_rect_toggle_callback=lambda _enabled: None
    )

    with pytest.raises(ValueError, match="Unknown mode requested"):
        controller.handle_mode_switch_request(ShellActionId.OPEN_PROJECT)


def test_mode_toolbar_controller_updates_bound_context_bar_state() -> None:
    """Context-bar state should be driven by the toolbar owner."""
    context_bar = _ContextBar()
    zoom_toggles: list[bool] = []
    controller = ModeToolbarController(
        action_map_provider=lambda: {}, zoom_rect_toggle_callback=zoom_toggles.append
    )
    controller.bind_context_bar(context_bar)

    controller.set_zoom_button_checked(True)
    controller.apply_mode(mode=EditingMode.ANALYSIS, config=object(), current_project=None)
    context_bar.zoom_rect_toggled.emit(False)

    assert context_bar.zoom_active is True
    assert context_bar.current_mode == EditingMode.ANALYSIS
    assert context_bar.project_loaded is False
    assert zoom_toggles == [False]
