"""Own the shell Display menu toggles for optional spectrum curves."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QSignalBlocker, Signal
from PySide6.QtGui import QAction, QKeySequence

from chappy.gui.shell.actions.ids import ShellActionId
from chappy.gui.shell.shortcuts import get_shortcut_key
from chappy.i18n import get_language_switcher
from chappy.presentation.spectrum import DEFAULT_SPECTRUM_DISPLAY_OPTIONS, SpectrumDisplayOptions

if TYPE_CHECKING:
    from chappy.i18n.language_switcher import LanguageSwitcher


class DisplayMenuController(QObject):
    """Expose spectrum display toggles as checkable actions for the Display menu."""

    display_options_changed = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        """Create the display toggle actions.

        Args:
            parent: Optional Qt parent that owns the created actions.
        """
        super().__init__(parent)
        self._error_spectrum_action = self._create_action(
            "displayOptionErrorSpectrum",
            checked=DEFAULT_SPECTRUM_DISPLAY_OPTIONS.show_error_spectrum,
        )
        self._component_profiles_action = self._create_action(
            "displayOptionComponentProfiles",
            checked=DEFAULT_SPECTRUM_DISPLAY_OPTIONS.show_component_profiles,
        )
        self._component_profiles_action.setEnabled(False)
        self._apply_shortcut(
            self._component_profiles_action, ShellActionId.TOGGLE_COMPONENT_PROFILES
        )
        self._language_switcher: LanguageSwitcher = get_language_switcher(self)
        self._language_switcher.language_changed.connect(self._on_language_changed)
        self._apply_translations()

    def actions(self) -> tuple[QAction, ...]:
        """Return the display toggles in menu order."""
        return (self._error_spectrum_action, self._component_profiles_action)

    @property
    def component_profiles_action(self) -> QAction:
        """Return the component-profiles toggle for external registration."""
        return self._component_profiles_action

    def options(self) -> SpectrumDisplayOptions:
        """Return the display options currently selected in the menu."""
        return SpectrumDisplayOptions(
            show_error_spectrum=self._error_spectrum_action.isChecked(),
            show_component_profiles=self._component_profiles_action.isChecked(),
        )

    def set_options(self, options: SpectrumDisplayOptions) -> None:
        """Restore check state from stored options without re-emitting them."""
        for action, checked in (
            (self._error_spectrum_action, options.show_error_spectrum),
            (self._component_profiles_action, options.show_component_profiles),
        ):
            with QSignalBlocker(action):
                action.setChecked(checked)

    def set_component_profiles_supported(self, supported: bool) -> None:
        """Enable or disable the component-profile toggle for the active surface."""
        self._component_profiles_action.setEnabled(supported)
        self._apply_component_profiles_tooltip()

    def _create_action(self, object_name: str, *, checked: bool) -> QAction:
        """Build one checkable display toggle action."""
        action = QAction(self)
        action.setObjectName(object_name)
        action.setCheckable(True)
        action.setChecked(checked)
        action.toggled.connect(self._emit_options)
        return action

    def _apply_shortcut(self, action: QAction, action_id: ShellActionId) -> None:
        """Apply the centrally defined shortcut and tag it for documentation."""
        shortcut_key = get_shortcut_key(action_id)
        if shortcut_key is not None:
            action.setShortcut(QKeySequence(shortcut_key))
        action.setProperty("shortcut.key", str(action_id))

    def _emit_options(self, _checked: bool) -> None:
        """Publish the display options selected by the user."""
        self.display_options_changed.emit(self.options())

    def _on_language_changed(self, _code: str) -> None:
        """Re-apply translated action text after a language change."""
        self._apply_translations()

    def _apply_translations(self) -> None:
        """Apply current language strings to the display toggles."""
        self._error_spectrum_action.setText(self.tr("Error spectrum"))
        self._component_profiles_action.setText(self.tr("Component profiles"))
        self._apply_component_profiles_tooltip()

    def _apply_component_profiles_tooltip(self) -> None:
        """Explain why the component-profile toggle is unavailable when disabled."""
        if self._component_profiles_action.isEnabled():
            self._component_profiles_action.setToolTip("")
            return
        self._component_profiles_action.setToolTip(self.tr("Available in Analysis region detail"))
