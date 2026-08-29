"""Context menu rendering controller for spectrum interactions."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint

from chappy.gui.protocols.context_menu import (
    ContextMenuActionDescriptor,
    ContextMenuActionIntent,
    ContextMenuToggleAction,
    ContextMenuTriggerAction,
)
from chappy.gui.theme import create_styled_menu

if TYPE_CHECKING:
    from PySide6.QtCore import QObject
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QMenu, QWidget

    from chappy.gui.protocols.intent_types import ShowContextMenuIntent

type ContextMenuActionProvider = Callable[
    ["ShowContextMenuIntent"], tuple[ContextMenuActionDescriptor, ...]
]
type SharedContextMenuActionProvider = Callable[[], tuple["QAction", ...]]


def _no_shared_actions() -> tuple[QAction, ...]:
    """Return no shared actions when the shell has not connected a provider."""
    return ()


class SpectrumContextMenuController:
    """Render context menus for spectrum interactions."""

    def __init__(
        self,
        *,
        view_provider: Callable[[], QWidget],
        action_provider: ContextMenuActionProvider,
        intent_handler: Callable[[ContextMenuActionIntent], None],
        parent: QObject | None = None,
    ) -> None:
        """Initialize the controller with renderer dependencies."""
        del parent
        self._view_provider = view_provider
        self._action_provider = action_provider
        self._intent_handler = intent_handler
        self._shared_action_provider: SharedContextMenuActionProvider = _no_shared_actions

    def set_action_provider(self, provider: ContextMenuActionProvider) -> None:
        """Set the action provider used for future menu requests."""
        self._action_provider = provider

    def set_shared_actions(self, provider: SharedContextMenuActionProvider) -> None:
        """Set the provider of mode-independent actions appended to every menu."""
        self._shared_action_provider = provider

    def show(self, intent: ShowContextMenuIntent) -> None:
        """Display a context menu for a show-context-menu intent."""
        action_descriptors = self._action_provider(intent)
        shared_actions = self._shared_action_provider()
        if not action_descriptors and not shared_actions:
            return
        view = self._view_provider()
        menu = create_styled_menu(view)
        self._add_actions(menu, action_descriptors)
        if shared_actions:
            if action_descriptors:
                menu.addSeparator()
            for shared_action in shared_actions:
                menu.addAction(shared_action)
        menu.exec(QPoint(intent.global_x, intent.global_y))

    def _add_actions(
        self, menu: QMenu, action_descriptors: tuple[ContextMenuActionDescriptor, ...]
    ) -> None:
        """Add action descriptors from the active mode provider."""
        for index, action_descriptor in enumerate(action_descriptors):
            if index > 0:
                menu.addSeparator()
            self._add_action(menu, action_descriptor)

    def _add_action(self, menu: QMenu, action_descriptor: ContextMenuActionDescriptor) -> None:
        """Render a typed action descriptor into a menu action."""
        action = menu.addAction(action_descriptor.label)
        action.setEnabled(action_descriptor.enabled)
        if action_descriptor.tooltip is not None:
            action.setToolTip(action_descriptor.tooltip)

        if isinstance(action_descriptor, ContextMenuTriggerAction):
            if action_descriptor.intent is not None:
                action.triggered.connect(
                    lambda _checked=False, descriptor=action_descriptor: self._intent_handler(
                        descriptor.intent
                    )
                )
            return

        if isinstance(action_descriptor, ContextMenuToggleAction):
            action.setCheckable(True)
            action.setChecked(action_descriptor.checked)
            action.toggled.connect(
                lambda checked, descriptor=action_descriptor: self._intent_handler(
                    descriptor.intent_when_checked if checked else descriptor.intent_when_unchecked
                )
            )
