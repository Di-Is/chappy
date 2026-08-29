"""Dialog that allows the user to switch the application language."""

from __future__ import annotations

from PySide6.QtCore import QT_TRANSLATE_NOOP, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QShowEvent  # noqa: TC002
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGroupBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chappy.gui.theme import apply_button_variant
from chappy.gui.visual_tokens import DialogMetrics
from chappy.i18n import LanguageSwitcher, QtCatalogLookup, get_language_switcher

_TRANSLATION_CONTEXT = "LanguageSettingsDialog"
_TITLE_SOURCE = str(QT_TRANSLATE_NOOP("LanguageSettingsDialog", "Language Settings"))
_DESCRIPTION_SOURCE = str(
    QT_TRANSLATE_NOOP("LanguageSettingsDialog", "Select the display language.")
)
_PREVIEW_LABEL_SOURCE = str(QT_TRANSLATE_NOOP("LanguageSettingsDialog", "Preview"))
_PREVIEW_HEADING_SOURCE = str(
    QT_TRANSLATE_NOOP("LanguageSettingsDialog", "Example interface text")
)
_ERROR_SAVE_SOURCE = str(
    QT_TRANSLATE_NOOP("LanguageSettingsDialog", "The language selection could not be saved.")
)
_OK_SOURCE = str(QT_TRANSLATE_NOOP("LanguageSettingsDialog", "OK"))
_CANCEL_SOURCE = str(QT_TRANSLATE_NOOP("LanguageSettingsDialog", "Cancel"))
_FILE_MENU_SOURCE = str(QT_TRANSLATE_NOOP("LanguageSettingsDialog", "&File"))
_OPEN_SOURCE = str(QT_TRANSLATE_NOOP("LanguageSettingsDialog", "Open"))
_OPEN_PROJECT_SOURCE = str(QT_TRANSLATE_NOOP("LanguageSettingsDialog", "Open Project"))
_OPEN_PROJECT_TOOLTIP_SOURCE = str(
    QT_TRANSLATE_NOOP("LanguageSettingsDialog", "Open observation data / project")
)
_PREVIEW_SAMPLE_SOURCE = str(
    QT_TRANSLATE_NOOP("LanguageSettingsDialog", "Example: It will look like this")
)


class LanguageSettingsDialog(QDialog):
    """Modal language selector implementing SCR-DIA-USR."""

    language_applied = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        language_switcher: LanguageSwitcher | None = None,
        qt_catalog_lookup: QtCatalogLookup | None = None,
    ) -> None:
        """Initialize the dialog and bind runtime language collaborators.

        Args:
            parent: Parent widget.
            language_switcher: Optional YAML language switcher for non-migrated strings.
            qt_catalog_lookup: Optional QM lookup used for selected-language previews.
        """
        super().__init__(parent)

        self._language_switcher = language_switcher or get_language_switcher(self)
        self._qt_catalog_lookup = qt_catalog_lookup or QtCatalogLookup(self)

        self.setModal(True)
        self.setObjectName("languageSettingsDialog")
        self.setProperty("accessible-role", "dialog")
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.setMinimumSize(DialogMetrics.MIN_WIDTH_SMALL, DialogMetrics.MIN_HEIGHT_SMALL)

        self._ok_guard = QTimer(self)
        self._ok_guard.setInterval(500)
        self._ok_guard.setSingleShot(True)
        self._ok_guard.timeout.connect(self._restore_ok_button)

        self._setup_ui()
        self._connect_signals()

        self._refresh_language_text(self._language_switcher.current_language)
        self._select_initial_language()
        self._update_preview(self._language_switcher.current_language)

        self._language_switcher.language_changed.connect(self._on_language_runtime_changed)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 - Qt override
        """Ensure focus defaults to the language selector when shown."""
        super().showEvent(event)
        self._language_combo.setFocus(Qt.FocusReason.TabFocusReason)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 16)
        layout.setSpacing(16)

        self._instruction_label = QLabel(self)
        self._instruction_label.setObjectName("languageInstruction")
        self._instruction_label.setWordWrap(True)
        self._instruction_label.setAccessibleDescription("language-instructions")
        layout.addWidget(self._instruction_label)

        self._language_combo = QComboBox(self)
        self._language_combo.setObjectName("languageComboBox")
        self._language_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._language_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        for option in self._language_switcher.options:
            self._language_combo.addItem(option.display_name, option.id)
        layout.addWidget(self._language_combo)

        separator = QFrame(self)
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator)

        self._preview_group = QGroupBox(self)
        self._preview_group.setObjectName("previewGroup")
        preview_layout = QVBoxLayout(self._preview_group)
        preview_layout.setContentsMargins(16, 12, 16, 12)
        preview_layout.setSpacing(12)

        self._preview_heading = QLabel(self._preview_group)
        self._preview_heading.setObjectName("previewHeading")
        self._preview_heading.setWordWrap(True)
        self._preview_heading.setProperty("aria-live", "polite")
        preview_layout.addWidget(self._preview_heading)

        self._preview_panel = QFrame(self._preview_group)
        self._preview_panel.setObjectName("previewPanel")
        self._preview_panel.setFrameShape(QFrame.Shape.StyledPanel)
        self._preview_panel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._preview_panel.setStyleSheet(
            "#previewPanel {"
            " background: palette(alternate-base);"
            " border-radius: 8px;"
            " padding: 12px;"
            "}"
        )

        panel_layout = QVBoxLayout(self._preview_panel)
        panel_layout.setContentsMargins(12, 8, 12, 8)
        panel_layout.setSpacing(8)

        self._preview_menu = QLabel(self._preview_panel)
        self._preview_menu.setObjectName("previewMenuLabel")
        self._preview_menu.setAccessibleDescription("preview-menu")
        panel_layout.addWidget(self._preview_menu)

        self._preview_button = QPushButton(self._preview_panel)
        self._preview_button.setObjectName("previewSampleButton")
        self._preview_button.setEnabled(False)
        self._preview_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        apply_button_variant(self._preview_button, "secondary")
        panel_layout.addWidget(self._preview_button)

        self._preview_status = QLabel(self._preview_panel)
        self._preview_status.setObjectName("previewStatusLabel")
        self._preview_status.setWordWrap(True)
        self._preview_status.setProperty("aria-live", "polite")
        panel_layout.addWidget(self._preview_status)

        preview_layout.addWidget(self._preview_panel)
        layout.addWidget(self._preview_group)

        button_bar = QDialogButtonBox(Qt.Orientation.Horizontal, self)
        self._cancel_button = button_bar.addButton(QDialogButtonBox.StandardButton.Cancel)
        self._cancel_button.setObjectName("cancelButton")
        self._ok_button = button_bar.addButton(QDialogButtonBox.StandardButton.Ok)
        self._ok_button.setObjectName("okButton")
        button_bar.setCenterButtons(False)
        button_bar.setProperty("dialogButtonBox", True)
        apply_button_variant(self._cancel_button, "secondary")
        apply_button_variant(self._ok_button, "primary")

        layout.addWidget(button_bar)

        self._button_box = button_bar

    def _connect_signals(self) -> None:
        self._language_combo.currentIndexChanged.connect(self._on_language_index_changed)
        self._button_box.accepted.connect(self._on_accept)
        self._button_box.rejected.connect(self.reject)

    @Slot(int)
    def _on_language_index_changed(self, _index: int) -> None:
        code = self._language_combo.currentData()
        if isinstance(code, str):
            self._update_preview(code)

    @Slot()
    def _on_accept(self) -> None:
        if not self._ok_button.isEnabled():
            return

        selection = self._selected_language()
        if selection is None:
            return

        self._ok_button.setEnabled(False)
        self._ok_guard.start()

        try:
            self._language_switcher.set_language(selection)
        except OSError:
            self._show_error(_ERROR_SAVE_SOURCE)
            self._restore_ok_button()
            return

        self.language_applied.emit(selection)
        self.accept()

    @Slot(str)
    def _on_language_runtime_changed(self, code: str) -> None:
        self._refresh_language_text(code)
        self._select_language_button(code)
        self._update_preview(code)

    def _selected_language(self) -> str | None:
        code = self._language_combo.currentData()
        return code if isinstance(code, str) else None

    def _select_initial_language(self) -> None:
        self._select_language_button(self._language_switcher.current_language)

    def _select_language_button(self, code: str) -> None:
        index = self._language_combo.findData(code)
        if index >= 0:
            self._language_combo.setCurrentIndex(index)

    def _refresh_language_text(self, language: str) -> None:
        title = self._qt_translate(language, _TITLE_SOURCE)
        self.setWindowTitle(title)
        self.setAccessibleName(title)

        self._instruction_label.setText(self._qt_translate(language, _DESCRIPTION_SOURCE))
        self._preview_group.setTitle(self._qt_translate(language, _PREVIEW_LABEL_SOURCE))
        self._preview_heading.setText(self._qt_translate(language, _PREVIEW_HEADING_SOURCE))

        ok_text = self._qt_translate(language, _OK_SOURCE)
        cancel_text = self._qt_translate(language, _CANCEL_SOURCE)
        self._ok_button.setText(ok_text)
        self._cancel_button.setText(cancel_text)

        for index, option in enumerate(self._language_switcher.options):
            self._language_combo.setItemText(index, option.display_name)

    def _update_preview(self, language: str) -> None:
        menu_title = self._qt_translate(language, _FILE_MENU_SOURCE)
        open_action = self._qt_translate(language, _OPEN_SOURCE)
        self._preview_menu.setText(f"{menu_title} → {open_action}")

        button_label = self._qt_translate(language, _OPEN_PROJECT_SOURCE)
        self._preview_button.setText(button_label)
        tooltip = self._qt_translate(language, _OPEN_PROJECT_TOOLTIP_SOURCE)
        self._preview_button.setToolTip(tooltip)

        status_text = self._qt_translate(language, _PREVIEW_SAMPLE_SOURCE)
        self._preview_status.setText(status_text)

    def _qt_translate(self, language: str, source_text: str) -> str:
        """Translate a Qt source string for an arbitrary language.

        Args:
            language: Target language code.
            source_text: Qt source text.

        Returns:
            Translated text from the direct QM lookup, or the source text.
        """
        return self._qt_catalog_lookup.translate(language, _TRANSLATION_CONTEXT, source_text)

    def _restore_ok_button(self) -> None:
        if not self._ok_button.isEnabled():
            self._ok_button.setEnabled(True)
        if self._ok_guard.isActive():
            self._ok_guard.stop()

    def _show_error(self, source_text: str) -> None:
        QMessageBox.critical(self, self.windowTitle(), self.tr(source_text))
