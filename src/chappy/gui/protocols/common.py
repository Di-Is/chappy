"""Common Protocol definitions for GUI module.

This module consolidates frequently used Protocol definitions to avoid duplication
across the GUI module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from PySide6.QtCore import QPoint, QPointF, QSettings

    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.modes.continuum.editor import ContinuumEditor
    from chappy.gui.modes.mode_state_store import ModeStateStore
    from chappy.gui.shell.menu_action_factory import MenuActionFactory
    from chappy.gui.shell.mode_shell_coordinator import ModeShellCoordinator
    from chappy.gui.shell.view_stack import ViewStack


@runtime_checkable
class ViewWithSettings(Protocol):
    """Protocol for views with settings."""

    settings: QSettings


@runtime_checkable
class MouseEvent(Protocol):
    """Protocol for mouse event objects."""

    def button(self) -> int:
        """Return the mouse button associated with the event."""
        ...

    def modifiers(self) -> int:
        """Return the keyboard modifiers active during the event."""
        ...

    def position(self) -> QPointF:
        """Return the event position in floating-point coordinates."""
        ...

    def pos(self) -> QPoint:
        """Return the event position in integer coordinates."""
        ...


@runtime_checkable
class MainWindowShellPort(Protocol):
    """Protocol for main window shell composition state."""

    continuum_editor: ContinuumEditor | None
    current_project: SpectroscopyProject | None
    view_stack: ViewStack | None
    mode_state_store: ModeStateStore | None
    mode_shell_coordinator: ModeShellCoordinator | None
    action_factory: MenuActionFactory | None
