"""Qt-free identify context menu presentation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class IdentifyContextMenuActionKind(StrEnum):
    """Identify context menu action kind."""

    TOGGLE_PREVIEW_LOCK = "toggle-preview-lock"


@dataclass(frozen=True, slots=True)
class IdentifyContextMenuMessages:
    """Labels used by identify context menu actions."""

    always_show_candidate_overlay: str


@dataclass(frozen=True, slots=True)
class IdentifyContextMenuState:
    """State required to build identify context menu actions."""

    preview_lock_enabled: bool
    preview_lock_available: bool


@dataclass(frozen=True, slots=True)
class IdentifyContextMenuAction:
    """Qt-free identify context menu action descriptor."""

    label: str
    kind: IdentifyContextMenuActionKind
    enabled: bool = True
    checkable: bool = False
    checked: bool = False
    preview_lock_enabled: bool | None = None


def build_identify_context_menu_actions(
    *, state: IdentifyContextMenuState, messages: IdentifyContextMenuMessages
) -> tuple[IdentifyContextMenuAction, ...]:
    """Build identify context menu action descriptors.

    Args:
        state: Identify context menu state.
        messages: Labels for actions.

    Returns:
        Context menu action descriptors.
    """
    return (
        IdentifyContextMenuAction(
            label=messages.always_show_candidate_overlay,
            kind=IdentifyContextMenuActionKind.TOGGLE_PREVIEW_LOCK,
            enabled=state.preview_lock_available,
            checkable=True,
            checked=state.preview_lock_enabled,
            preview_lock_enabled=not state.preview_lock_enabled,
        ),
    )
