"""Confirmation dialog guiding the close-project workflow (SCR-DIA-CPJ)."""

from __future__ import annotations

from enum import Enum, auto

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from chappy.gui.dialog_sizing import enforce_translated_minimum_size
from chappy.gui.theme import apply_action_row_sizing, apply_button_variant
from chappy.gui.visual_tokens import DialogMetrics


class CloseProjectDialog(QDialog):
    """Three-way confirmation dialog used when the user closes a project.

    The dialog adheres to SCR-DIA-COM button placement guidelines and exposes
    the user's choice so the caller can orchestrate save/discard flows.
    """

    class Choice(Enum):
        """Possible outcomes for the close project confirmation."""

        SAVE = auto()
        DISCARD = auto()
        CANCEL = auto()

    def __init__(self, parent: QWidget | None = None, *, project_name: str | None = None) -> None:
        """Initialize the dialog with translated labels and initial layout.

        Args:
            parent: Parent widget for the dialog.
            project_name: Optional project name shown in the confirmation details.
        """
        super().__init__(parent)
        self._choice = CloseProjectDialog.Choice.CANCEL
        self._project_name = project_name

        self._message_label: QLabel | None = None
        self._detail_label: QLabel | None = None
        self._guidance_label: QLabel | None = None

        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        self._build_ui(project_name)
        self._wire_signals()
        self._retranslate_ui()

    @property
    def choice(self) -> CloseProjectDialog.Choice:
        """Return the user's selected action.

        Returns:
            Selected close-project action.
        """
        return self._choice

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        """Retranslate the dialog when Qt translators change.

        Args:
            event: Qt change event delivered to the dialog.
        """
        if event.type() == QEvent.Type.LanguageChange:
            self._retranslate_ui()
        super().changeEvent(event)

    def _build_ui(self, project_name: str | None) -> None:
        """Build the static widget tree for the dialog.

        Args:
            project_name: Optional project name used to decide whether details are shown.
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        self._message_label = QLabel(self)
        self._message_label.setWordWrap(True)
        self._message_label.setObjectName("closeProjectMessage")
        layout.addWidget(self._message_label)

        if project_name:
            self._detail_label = QLabel(self)
            self._detail_label.setObjectName("closeProjectDetail")
            self._detail_label.setWordWrap(True)
            layout.addWidget(self._detail_label)

        # Optional hint about the resulting state
        self._guidance_label = QLabel(self)
        self._guidance_label.setObjectName("closeProjectGuidance")
        self._guidance_label.setWordWrap(True)
        layout.addWidget(self._guidance_label)

        layout.addItem(
            QSpacerItem(0, 12, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        )

        buttons = QHBoxLayout()
        buttons.setSpacing(12)

        self._cancel_button = QPushButton(self)
        self._cancel_button.setObjectName("closeProjectCancelButton")
        self._cancel_button.setDefault(False)
        self._cancel_button.setAutoDefault(False)
        apply_button_variant(self._cancel_button, "secondary")

        self._dont_save_button = QPushButton(self)
        self._dont_save_button.setObjectName("closeProjectDontSaveButton")
        self._dont_save_button.setDefault(False)
        self._dont_save_button.setAutoDefault(False)
        apply_button_variant(self._dont_save_button, "danger")

        self._save_button = QPushButton(self)
        self._save_button.setObjectName("closeProjectSaveButton")
        self._save_button.setDefault(True)
        self._save_button.setAutoDefault(True)
        apply_button_variant(self._save_button, "primary")

        apply_action_row_sizing(self._cancel_button, self._dont_save_button, self._save_button)

        buttons.addWidget(self._cancel_button)
        buttons.addWidget(self._dont_save_button)
        buttons.addStretch()
        buttons.addWidget(self._save_button)

        layout.addLayout(buttons)

        self.setTabOrder(self._cancel_button, self._dont_save_button)
        self.setTabOrder(self._dont_save_button, self._save_button)
        self._save_button.setFocus(Qt.FocusReason.OtherFocusReason)

    def _wire_signals(self) -> None:
        """Connect dialog buttons to their selection handlers."""
        self._cancel_button.clicked.connect(self._on_cancel_clicked)
        self._dont_save_button.clicked.connect(self._on_discard_clicked)
        self._save_button.clicked.connect(self._on_save_clicked)

    def _retranslate_ui(self) -> None:
        """Apply translated text while preserving the current dialog state."""
        self.setWindowTitle(self.tr("&Close Project"))

        if self._message_label is not None:
            self._message_label.setText(
                self.tr("The current project has unsaved changes.\nDo you want to save them?")
            )

        if self._detail_label is not None:
            if self._project_name:
                name_label = self.tr("Name")
                self._detail_label.setText(f"{name_label}: {self._project_name}")
                self._detail_label.setVisible(True)
            else:
                self._detail_label.clear()
                self._detail_label.setVisible(False)

        guidance_label = self._guidance_label
        if guidance_label is not None:
            guidance_text = self.tr(
                "Closing returns to Start mode. Use File \u2192 Open Project to load it again."
            )
            guidance_label.setText(guidance_text)
            guidance_label.setVisible(bool(guidance_text))

        self._cancel_button.setText(self.tr("Cancel"))
        self._dont_save_button.setText(self.tr("Don't Save"))
        self._save_button.setText(self.tr("Save"))

        enforce_translated_minimum_size(
            self, floor=QSize(DialogMetrics.MIN_WIDTH_SMALL, DialogMetrics.MIN_HEIGHT_SMALL)
        )

    def _on_cancel_clicked(self) -> None:
        """Reject the dialog after recording the cancel choice."""
        self._choice = CloseProjectDialog.Choice.CANCEL
        self.reject()

    def _on_discard_clicked(self) -> None:
        """Accept the dialog after recording the discard choice."""
        self._choice = CloseProjectDialog.Choice.DISCARD
        self.accept()

    def _on_save_clicked(self) -> None:
        """Accept the dialog after recording the save choice."""
        self._choice = CloseProjectDialog.Choice.SAVE
        self.accept()


def prompt_close_project(
    parent: QWidget | None, *, project_name: str | None = None
) -> CloseProjectDialog.Choice:
    """Show the close project dialog and return the selected option.

    Args:
        parent: Parent widget for the modal dialog.
        project_name: Optional project name shown in the confirmation details.

    Returns:
        Selected close-project action.
    """
    dialog = CloseProjectDialog(parent, project_name=project_name)
    dialog.exec()
    return dialog.choice
