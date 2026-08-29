"""Centralized shortcut definitions for runtime UI and documentation."""

import re
import sys
from dataclasses import dataclass
from enum import Enum, auto

from PySide6.QtGui import QKeySequence

from chappy.gui.shell.actions.ids import ShellActionId


class ShortcutPlatform(Enum):
    """Platform families whose user-facing modifier names differ."""

    MACOS = auto()
    WINDOWS_LINUX = auto()


def current_shortcut_platform() -> ShortcutPlatform:
    """Return the platform family used for runtime shortcut labels."""
    if sys.platform == "darwin":
        return ShortcutPlatform.MACOS
    return ShortcutPlatform.WINDOWS_LINUX


@dataclass(frozen=True)
class ShortcutDef:
    """Shortcut definition with cross-platform display support.

    Attributes:
        key: The shortcut key (StandardKey enum or string like "Ctrl+Z").
        mac: Display string for macOS (e.g., "Cmd+Z").
        win: Display string for Windows/Linux (e.g., "Ctrl+Z").
    """

    key: QKeySequence.StandardKey | str | None
    mac: str
    win: str

    @property
    def display(self) -> str:
        """Return cross-platform display string.

        Examples:
            - "Cmd/Ctrl+Z" for standard Ctrl/Cmd shortcuts
            - "Cmd+Shift+Z / Ctrl+Y" for Redo (different on each platform)
            - "F5" for function keys (same on all platforms)
        """
        if not self.mac or not self.win:
            return self.mac or self.win or ""
        # Same on both platforms (e.g., F5, V, Del)
        if self.mac == self.win:
            return self.mac
        # Redo-like case: completely different shortcuts
        if self.mac != self.win.replace("Ctrl", "Cmd"):
            return f"{self.mac} / {self.win}"
        # Standard case: Cmd/Ctrl form
        return self.win.replace("Ctrl", "Cmd/Ctrl")

    def display_for(self, platform: ShortcutPlatform) -> str:
        """Return the shortcut label for one runtime platform."""
        if platform is ShortcutPlatform.MACOS:
            return self.mac
        return self.win


# Action key -> Shortcut definition
SHORTCUTS: dict[ShellActionId, ShortcutDef] = {
    # File menu
    ShellActionId.OPEN_OBSERVATION_DATA: ShortcutDef(
        "Ctrl+Shift+O", "Cmd+Shift+O", "Ctrl+Shift+O"
    ),
    ShellActionId.OPEN_PROJECT: ShortcutDef(QKeySequence.StandardKey.Open, "Cmd+O", "Ctrl+O"),
    ShellActionId.SAVE_PROJECT: ShortcutDef(QKeySequence.StandardKey.Save, "Cmd+S", "Ctrl+S"),
    ShellActionId.SAVE_PROJECT_AS: ShortcutDef(
        QKeySequence.StandardKey.SaveAs, "Cmd+Shift+S", "Ctrl+Shift+S"
    ),
    ShellActionId.CLOSE_PROJECT: ShortcutDef(QKeySequence.StandardKey.Close, "Cmd+W", "Ctrl+W"),
    ShellActionId.QUIT: ShortcutDef(QKeySequence.StandardKey.Quit, "Cmd+Q", "Ctrl+Q"),
    # Edit menu
    ShellActionId.UNDO: ShortcutDef(QKeySequence.StandardKey.Undo, "Cmd+Z", "Ctrl+Z"),
    ShellActionId.REDO: ShortcutDef(QKeySequence.StandardKey.Redo, "Cmd+Shift+Z", "Ctrl+Y"),
    ShellActionId.COPY: ShortcutDef(QKeySequence.StandardKey.Copy, "Cmd+C", "Ctrl+C"),
    ShellActionId.PASTE: ShortcutDef(QKeySequence.StandardKey.Paste, "Cmd+V", "Ctrl+V"),
    ShellActionId.DELETE: ShortcutDef(QKeySequence.StandardKey.Delete, "Del", "Del"),
    # View menu
    ShellActionId.ZOOM_IN: ShortcutDef(None, "Cmd++, Cmd+=", "Ctrl++, Ctrl+="),
    ShellActionId.ZOOM_OUT: ShortcutDef(None, "Cmd+-", "Ctrl+-"),
    ShellActionId.RESET_VIEW: ShortcutDef("Ctrl+R", "Cmd+R", "Ctrl+R"),
    ShellActionId.AUTO_ADJUST_FLUX: ShortcutDef("Ctrl+A", "Cmd+A", "Ctrl+A"),
    ShellActionId.TOGGLE_VELOCITY_PLOT_IDENTIFY: ShortcutDef("V", "V", "V"),
    ShellActionId.TOGGLE_VELOCITY_PLOT_ANALYSIS: ShortcutDef("V", "V", "V"),
    ShellActionId.TOGGLE_COMPONENT_PROFILES: ShortcutDef("M", "M", "M"),
    # Mode menu (numbering follows core.editing_mode.MODE_WORKFLOW_ORDER)
    ShellActionId.IDENTIFY_MODE: ShortcutDef("Ctrl+1", "Cmd+1", "Ctrl+1"),
    ShellActionId.ANALYSIS_MODE: ShortcutDef("Ctrl+2", "Cmd+2", "Ctrl+2"),
    ShellActionId.CONTINUUM_MODE: ShortcutDef("Ctrl+3", "Cmd+3", "Ctrl+3"),
    ShellActionId.ANALYSIS_BACK: ShortcutDef("Alt+Left", "Alt+Left", "Alt+Left"),
    # Settings menu
    ShellActionId.OPEN_LINE_DATABASE_FOLDER: ShortcutDef("Ctrl+D", "Cmd+D", "Ctrl+D"),
    ShellActionId.COSMOLOGY_SETTINGS: ShortcutDef("Ctrl+U", "Cmd+U", "Ctrl+U"),
    ShellActionId.RESOLUTION_SETTINGS: ShortcutDef("Ctrl+Shift+R", "Cmd+Shift+R", "Ctrl+Shift+R"),
    ShellActionId.LANGUAGE_SETTINGS: ShortcutDef("Ctrl+L", "Cmd+L", "Ctrl+L"),
    # Other
    ShellActionId.FIT_MODEL: ShortcutDef("F5", "F5", "F5"),
    ShellActionId.HELP: ShortcutDef("F1", "F1", "F1"),
}


def get_shortcut_key(action_key: ShellActionId) -> QKeySequence.StandardKey | str | None:
    """Get the shortcut key for an action.

    Args:
        action_key: The action identifier (e.g., "undo", "redo").

    Returns:
        The shortcut key (StandardKey or string), or None if not defined.
    """
    shortcut_def = SHORTCUTS.get(action_key)
    return shortcut_def.key if shortcut_def else None


def get_shortcut_display(action_key: ShellActionId) -> str:
    """Get the cross-platform shortcut display string for an action.

    Args:
        action_key: The action identifier (e.g., "undo", "redo").

    Returns:
        Display text for documentation, or an empty string when no shortcut is defined.
    """
    shortcut_def = SHORTCUTS.get(action_key)
    return shortcut_def.display if shortcut_def else ""


def get_runtime_shortcut_display(
    action_key: ShellActionId, *, platform: ShortcutPlatform | None = None
) -> str:
    """Return the shortcut label for the running or explicitly supplied platform."""
    shortcut_def = SHORTCUTS.get(action_key)
    if shortcut_def is None:
        return ""
    resolved_platform = platform or current_shortcut_platform()
    return shortcut_def.display_for(resolved_platform)


_ACTION_SHORTCUT_TOKEN = re.compile(r"\{(?P<action>[a-z_]+)_shortcut\}")
_PRIMARY_MODIFIER_TOKEN = "{primary_modifier}"  # noqa: S105 - format token, not a secret


def format_runtime_shortcuts(text: str, *, platform: ShortcutPlatform | None = None) -> str:
    """Replace typed shortcut placeholders in already-translated runtime text.

    Action placeholders use ``{<ShellActionId value>_shortcut}``, for example
    ``{undo_shortcut}``. ``{primary_modifier}`` is provided for mouse gestures
    such as multi-selection, which are not shell actions.
    """
    resolved_platform = platform or current_shortcut_platform()

    def replace_action(match: re.Match[str]) -> str:
        action_id = ShellActionId(match.group("action"))
        display = get_runtime_shortcut_display(action_id, platform=resolved_platform)
        if not display:
            msg = f"No runtime shortcut display is defined for {action_id.value!r}."
            raise ValueError(msg)
        return display

    formatted = _ACTION_SHORTCUT_TOKEN.sub(replace_action, text)
    primary_modifier = "Cmd" if resolved_platform is ShortcutPlatform.MACOS else "Ctrl"
    return formatted.replace(_PRIMARY_MODIFIER_TOKEN, primary_modifier)
