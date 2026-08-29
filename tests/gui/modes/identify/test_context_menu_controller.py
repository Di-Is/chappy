"""Tests for identify context menu controller."""

from __future__ import annotations

from chappy.gui.modes.identify import IdentifyContextMenuController, IdentifyContextMenuRequest
from chappy.gui.protocols.context_menu import ContextMenuToggleAction
from chappy.gui.protocols.intent_types import ToggleIdentifyPreviewLockIntent


def test_actions_for_request_builds_preview_lock_toggle_intents() -> None:
    """The preview lock menu action should expose checked and unchecked intents."""
    controller = IdentifyContextMenuController()

    actions = controller.actions_for_request(
        IdentifyContextMenuRequest(preview_lock_enabled=True, preview_lock_available=True)
    )

    preview_action = actions[0]

    assert isinstance(preview_action, ContextMenuToggleAction)
    assert preview_action.label == "Always show candidate overlay"
    assert preview_action.checked is True
    assert isinstance(preview_action.intent_when_checked, ToggleIdentifyPreviewLockIntent)
    assert isinstance(preview_action.intent_when_unchecked, ToggleIdentifyPreviewLockIntent)
    assert preview_action.intent_when_checked.enabled is True
    assert preview_action.intent_when_unchecked.enabled is False
