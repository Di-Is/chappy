"""Tests for identify context menu presentation helpers."""

from __future__ import annotations

from chappy.presentation.identify import (
    IdentifyContextMenuActionKind,
    IdentifyContextMenuMessages,
    IdentifyContextMenuState,
    build_identify_context_menu_actions,
)


def test_build_identify_context_menu_actions_disables_unavailable_preview_lock() -> None:
    """The preview lock descriptor should expose availability and checked state."""
    actions = build_identify_context_menu_actions(
        state=IdentifyContextMenuState(preview_lock_enabled=False, preview_lock_available=False),
        messages=IdentifyContextMenuMessages(
            always_show_candidate_overlay="Always show candidate overlay"
        ),
    )

    preview_action = actions[0]

    assert preview_action.kind is IdentifyContextMenuActionKind.TOGGLE_PREVIEW_LOCK
    assert preview_action.label == "Always show candidate overlay"
    assert preview_action.checkable is True
    assert preview_action.enabled is False
    assert preview_action.checked is False
