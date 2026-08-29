"""Custom status bar controller implementing SCR-COM zone layout."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QProgressBar, QStatusBar

from chappy.gui.theme import Colors
from chappy.gui.visual_tokens import LayoutMetrics, NotificationColors


class StatusBarController:
    """Helper that manages the three-zone status bar."""

    def __init__(self, status_bar: QStatusBar) -> None:
        """Cache references to child widgets and layout the status bar."""
        self._status_bar = status_bar
        self._status_bar.setObjectName("mainStatusBar")
        self._status_bar.setSizeGripEnabled(False)
        self._status_bar.setMinimumHeight(LayoutMetrics.STATUSBAR_HEIGHT)
        base_style = (
            f" background-color: {Colors.BACKGROUND_PANEL};"
            f" color: {Colors.TEXT_PRIMARY};"
            f" border-top: 1px solid {Colors.BORDER_DEFAULT};"
        )
        self._status_bar.setStyleSheet(
            "QStatusBar {" + base_style + "}"
            "#mainStatusBar {"
            f" background-color: {Colors.BACKGROUND_PANEL};"
            f" color: {Colors.TEXT_PRIMARY};"
            f" border-top: 1px solid {Colors.BORDER_DEFAULT};"
            "}"
            "#mainStatusBar QLabel {"
            " background-color: transparent;"
            " color: inherit;"
            "}"
            "#mainStatusBar QProgressBar {"
            " background-color: transparent;"
            " color: inherit;"
            "}"
            "QStatusBar::item {"
            " border: none;"
            " background: transparent;"
            f" color: {Colors.TEXT_PRIMARY};"
            "}"
            "QProgressBar::chunk {"
            f" background-color: {Colors.PRIMARY};"
            "}"
        )

        self._mode_label = QLabel("Mode: --")
        self._mode_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self._mode_label.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-weight: 600; padding: 0 8px;"
        )
        self._mode_label.setObjectName("statusModeLabel")

        self._message_label = QLabel("")
        self._message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message_label.setMinimumWidth(200)
        self._message_label.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-weight: 500; padding: 0 8px;"
        )
        self._message_label.setObjectName("statusMessageLabel")

        self._coordinate_label = QLabel("λ: --, Flux: --")
        self._coordinate_label.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        )
        self._coordinate_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; padding: 0 8px;")
        self._coordinate_label.setObjectName("statusCoordinateLabel")

        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        self._progress_bar.setMaximumWidth(200)

        self._status_bar.addWidget(self._mode_label)
        self._status_bar.addPermanentWidget(self._message_label, 1)
        self._status_bar.addPermanentWidget(self._coordinate_label)
        self._status_bar.addPermanentWidget(self._progress_bar)

        self._message_timer: QTimer | None = None

    @property
    def progress_bar(self) -> QProgressBar:
        """Expose the embedded progress bar widget."""
        return self._progress_bar

    def update_mode(self, mode_text: str) -> None:
        """Update the mode label text in the status bar."""
        self._mode_label.setText(f"Mode: {mode_text}")

    def show_message(self, text: str, timeout_ms: int = 3000, level: str = "info") -> None:
        """Display a temporary message with semantic coloring."""
        color = {
            "info": NotificationColors.INFO,
            "warning": NotificationColors.WARNING,
            "error": NotificationColors.ERROR,
            "success": NotificationColors.SUCCESS,
        }.get(level, NotificationColors.INFO)
        self._message_label.setStyleSheet(f"color: {color}; font-weight: 500; padding: 0 8px;")
        self._message_label.setText(text)

        if self._message_timer is None:
            self._message_timer = QTimer(self._status_bar)
            self._message_timer.setSingleShot(True)
            self._message_timer.timeout.connect(self.clear_message)

        if timeout_ms > 0:
            self._message_timer.start(timeout_ms)
        else:
            self._message_timer.stop()

    def clear_message(self) -> None:
        """Clear the message area."""
        self._message_label.setText("")
        self._message_label.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-weight: 500; padding: 0 8px;"
        )

    def update_coordinates(self, wavelength: float, flux: float) -> None:
        """Display cursor coordinates in the right-hand zone."""
        self._coordinate_label.setText(f"λ: {wavelength:.2f}, Flux: {flux:.3f}")

    def set_coordinates_visible(self, visible: bool) -> None:
        """Show or hide the coordinate display area."""
        self._coordinate_label.setVisible(visible)

    def clear_coordinates(self) -> None:
        """Reset coordinate display to placeholder."""
        self._coordinate_label.setText("λ: --, Flux: --")
