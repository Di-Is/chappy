"""Identify-mode context menu action provider."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject

from chappy.gui.protocols.context_menu import ContextMenuActionDescriptor, ContextMenuToggleAction
from chappy.gui.protocols.intent_types import ToggleIdentifyPreviewLockIntent
from chappy.presentation.identify import (
    IdentifyContextMenuAction,
    IdentifyContextMenuActionKind,
    IdentifyContextMenuMessages,
    IdentifyContextMenuState,
    build_identify_context_menu_actions,
)


@dataclass(frozen=True, slots=True)
class IdentifyContextMenuRequest:
    """State required to build identify context menu actions."""

    preview_lock_enabled: bool
    preview_lock_available: bool


class IdentifyContextMenuController(QObject):
    """Build identify-mode context menu action descriptors."""

    def actions_for_request(
        self, request: IdentifyContextMenuRequest
    ) -> tuple[ContextMenuActionDescriptor, ...]:
        """Build typed context menu action descriptors.

        Args:
            request: Identify context menu request state.

        Returns:
            Context menu descriptors consumed by the spectrum surface.
        """
        actions = build_identify_context_menu_actions(
            state=IdentifyContextMenuState(
                preview_lock_enabled=request.preview_lock_enabled,
                preview_lock_available=request.preview_lock_available,
            ),
            messages=IdentifyContextMenuMessages(
                always_show_candidate_overlay=self.tr("Always show candidate overlay")
            ),
        )
        return tuple(self._to_context_menu_action(action) for action in actions)

    def _to_context_menu_action(
        self, action: IdentifyContextMenuAction
    ) -> ContextMenuActionDescriptor:
        """Convert an identify action descriptor to a GUI context menu descriptor."""
        match action.kind:
            case IdentifyContextMenuActionKind.TOGGLE_PREVIEW_LOCK:
                return ContextMenuToggleAction(
                    label=action.label,
                    enabled=action.enabled,
                    checked=action.checked,
                    intent_when_checked=ToggleIdentifyPreviewLockIntent(enabled=True),
                    intent_when_unchecked=ToggleIdentifyPreviewLockIntent(enabled=False),
                )
