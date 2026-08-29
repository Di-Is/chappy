"""OS-specific shortcut label tests for runtime GUI copy."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from chappy.gui.common.tutorial import TutorialBubble, TutorialStep
from chappy.gui.shell.actions.ids import ShellActionId
from chappy.gui.shell.shortcuts import (
    ShortcutPlatform,
    format_runtime_shortcuts,
    get_runtime_shortcut_display,
)


@pytest.mark.parametrize(
    ("platform", "undo", "redo"),
    [
        (ShortcutPlatform.MACOS, "Cmd+Z", "Cmd+Shift+Z"),
        (ShortcutPlatform.WINDOWS_LINUX, "Ctrl+Z", "Ctrl+Y"),
    ],
)
def test_runtime_shortcuts_match_platform(
    platform: ShortcutPlatform, undo: str, redo: str
) -> None:
    """Runtime labels select exactly one platform, including divergent Redo keys."""
    assert get_runtime_shortcut_display(ShellActionId.UNDO, platform=platform) == undo
    assert get_runtime_shortcut_display(ShellActionId.REDO, platform=platform) == redo


@pytest.mark.parametrize(
    ("platform", "expected"),
    [
        (ShortcutPlatform.MACOS, "Save with Cmd+S; select with Cmd+click."),
        (ShortcutPlatform.WINDOWS_LINUX, "Save with Ctrl+S; select with Ctrl+click."),
    ],
)
def test_runtime_shortcut_formatter_resolves_actions_and_mouse_modifier(
    platform: ShortcutPlatform, expected: str
) -> None:
    """Action and mouse-gesture placeholders share the same platform decision."""
    template = "Save with {save_project_shortcut}; select with {primary_modifier}+click."

    assert format_runtime_shortcuts(template, platform=platform) == expected


def test_runtime_shortcut_formatter_rejects_unknown_action_token() -> None:
    """A misspelled action placeholder fails instead of leaking into the UI."""
    with pytest.raises(ValueError, match="not a valid ShellActionId"):
        format_runtime_shortcuts("Press {missing_action_shortcut}.")


def test_tutorial_formats_shortcuts_after_translation(qtbot: QtBot) -> None:
    """Tutorial bubbles apply runtime values to their translated text templates."""
    host = QWidget()
    qtbot.addWidget(host)
    bubble = TutorialBubble(
        host,
        text_formatter=lambda text: format_runtime_shortcuts(
            text, platform=ShortcutPlatform.MACOS
        ),
    )
    bubble.show_step(
        TutorialStep(
            targets=(),
            action_source="Press {undo_shortcut}.",
            expected_source="Select with {primary_modifier}+click.",
        ),
        chapter_title_source="Shortcuts",
        progress_text="1/1",
    )

    assert bubble._action_label.text() == "Press Cmd+Z."
    assert bubble._expected_label.text() == "Select with Cmd+click."
