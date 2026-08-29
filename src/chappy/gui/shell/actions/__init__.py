"""Typed shell action vocabulary and dispatch helpers."""

from chappy.gui.shell.actions.dispatcher import ActionDispatcher
from chappy.gui.shell.actions.ids import ShellActionId
from chappy.gui.shell.actions.menu_bar_builder import MenuBarBuilder
from chappy.gui.shell.actions.registry import (
    ACTION_SOURCES,
    DEFAULT_ACTION_REGISTRY,
    MENU_SOURCES,
    ActionDefinition,
    ActionRegistry,
    ActionTextSource,
    MenuDefinition,
    MenuTextSource,
)
from chappy.gui.shell.actions.state_controller import ActionStateController

__all__ = [
    "ACTION_SOURCES",
    "DEFAULT_ACTION_REGISTRY",
    "MENU_SOURCES",
    "ActionDefinition",
    "ActionDispatcher",
    "ActionRegistry",
    "ActionStateController",
    "ActionTextSource",
    "MenuBarBuilder",
    "MenuDefinition",
    "MenuTextSource",
    "ShellActionId",
]
