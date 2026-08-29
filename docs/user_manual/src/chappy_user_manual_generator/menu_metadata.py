"""Documentation-side metadata for main-window menu actions.

The runtime menu structure (menus, ordering, labels, status tips) lives in
``chappy.gui.shell.actions.registry``. This module only adds the
documentation-specific attributes that the runtime does not need:
which editing modes an action applies to and which dialogs it opens.
``MENU_ORDER`` is derived directly from the runtime registry so the manual
always follows the real menu-bar order.
"""

from __future__ import annotations

from dataclasses import dataclass

from chappy.core.editing_mode import EditingMode
from chappy.gui.shell.actions.ids import ShellActionId
from chappy.gui.shell.actions.registry import DEFAULT_ACTION_REGISTRY

_START = EditingMode.START.value
_IDENTIFY = EditingMode.IDENTIFY.value
_ANALYSIS = EditingMode.ANALYSIS.value
_CONTINUUM = EditingMode.CONTINUUM.value

_PROJECT_MODES = (_IDENTIFY, _ANALYSIS, _CONTINUUM)

# Menu order mirrors the runtime menu bar.
MENU_ORDER: tuple[str, ...] = tuple(menu.name for menu in DEFAULT_ACTION_REGISTRY.menus)


@dataclass(frozen=True)
class MenuActionMetadata:
    """Documentation metadata for one menu action."""

    key: ShellActionId
    modes: tuple[str, ...] = ()
    dialog_slug: str | None = None
    extra_dialog_slugs: tuple[str, ...] = ()


_METADATA: tuple[MenuActionMetadata, ...] = (
    # File menu
    MenuActionMetadata(
        ShellActionId.OPEN_OBSERVATION_DATA,
        modes=(_START, _ANALYSIS),
        dialog_slug="open_observation_data",
    ),
    MenuActionMetadata(ShellActionId.OPEN_PROJECT, modes=(_START, _ANALYSIS)),
    MenuActionMetadata(ShellActionId.SAVE_PROJECT, modes=_PROJECT_MODES),
    MenuActionMetadata(ShellActionId.SAVE_PROJECT_AS, modes=_PROJECT_MODES),
    MenuActionMetadata(
        ShellActionId.CLOSE_PROJECT, modes=_PROJECT_MODES, dialog_slug="close_project"
    ),
    # View menu
    MenuActionMetadata(ShellActionId.ZOOM_IN, modes=_PROJECT_MODES),
    MenuActionMetadata(ShellActionId.ZOOM_OUT, modes=_PROJECT_MODES),
    MenuActionMetadata(ShellActionId.RESET_VIEW, modes=_PROJECT_MODES),
    MenuActionMetadata(ShellActionId.AUTO_ADJUST_FLUX, modes=_PROJECT_MODES),
    # Mode menu
    MenuActionMetadata(ShellActionId.IDENTIFY_MODE, modes=(_IDENTIFY,)),
    MenuActionMetadata(ShellActionId.ANALYSIS_MODE, modes=(_ANALYSIS,)),
    MenuActionMetadata(ShellActionId.CONTINUUM_MODE, modes=(_CONTINUUM,)),
    # Settings menu
    MenuActionMetadata(ShellActionId.OPEN_LINE_DATABASE_FOLDER, modes=(_IDENTIFY, _ANALYSIS)),
    MenuActionMetadata(
        ShellActionId.RESOLUTION_SETTINGS, modes=(_ANALYSIS,), dialog_slug="resolution_settings"
    ),
    MenuActionMetadata(
        ShellActionId.COSMOLOGY_SETTINGS, modes=(_ANALYSIS,), dialog_slug="cosmology_settings"
    ),
    MenuActionMetadata(ShellActionId.LANGUAGE_SETTINGS, dialog_slug="language_settings"),
    MenuActionMetadata(
        ShellActionId.PRESET_MANAGEMENT,
        modes=(_IDENTIFY,),
        dialog_slug="preset_management",
        extra_dialog_slugs=("line_selection",),
    ),
)


def menu_action_metadata() -> dict[str, MenuActionMetadata]:
    """Return menu action metadata keyed by action name.

    Returns:
        Mapping of action names (``ShellActionId`` values) to immutable
        documentation metadata.
    """
    return {str(meta.key): meta for meta in _METADATA}


def _validate_menu_metadata() -> None:
    """Fail fast when metadata drifts from the runtime menu registry."""
    menu_action_ids = {
        entry
        for menu in DEFAULT_ACTION_REGISTRY.menus
        for entry in menu.entries
        if entry is not None
    }
    seen: set[ShellActionId] = set()
    for meta in _METADATA:
        if meta.key in seen:
            msg = f"Duplicate menu action metadata: {meta.key}"
            raise ValueError(msg)
        seen.add(meta.key)
        if meta.key not in menu_action_ids:
            msg = f"Menu metadata refers to an action outside the menu bar: {meta.key}"
            raise ValueError(msg)


_validate_menu_metadata()
