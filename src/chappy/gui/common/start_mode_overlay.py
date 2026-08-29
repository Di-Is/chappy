"""Start mode overlay widget providing drag-and-drop guidance."""

from __future__ import annotations

from typing import override

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from chappy.gui.theme import Colors, Fonts
from chappy.gui.visual_tokens import ModeContextColors


class StartModeOverlay(QFrame):
    """Overlay shown in start mode to guide the user toward loading data."""

    def __init__(
        self, parent: QWidget | None = None, *, drop_target: QWidget | None = None
    ) -> None:
        """Set up layout and drag-and-drop affordances."""
        super().__init__(parent)
        self.setObjectName("startModeOverlay")
        # ドキュメント自動生成ではオーバーレイ自体は掲載しない
        self.setProperty("doc.include", False)
        self.setAcceptDrops(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._highlighted = False
        self._drop_target = drop_target

        self._main_text_override: str | None = None
        self._secondary_text_override: str | None = None
        self._formats_text_override: str | None = None

        self._build_ui()
        self._apply_base_style()
        self.use_default_messages()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Highlight drop zone when files enter."""
        self._forward_drag_event("dragEnterEvent", event)
        self._set_highlight(event.isAccepted())

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802
        """Keep highlight state in sync while dragging."""
        self._forward_drag_event("dragMoveEvent", event)
        self._set_highlight(event.isAccepted())

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:  # noqa: N802
        """Reset highlight when cursor leaves the drop zone."""
        self._set_highlight(False)
        self._forward_drag_event("dragLeaveEvent", event)

    def dropEvent(self, event: QDropEvent) -> None:
        """Forward drop events to the main window handler."""
        self._set_highlight(False)
        self._forward_drag_event("dropEvent", event)

    @override
    def changeEvent(self, event: QEvent) -> None:
        """Retranslate Qt-managed labels after the application language changes."""
        if event.type() == QEvent.Type.LanguageChange:
            self._apply_translations()
        super().changeEvent(event)

    def set_status_message(self, message: str | None) -> None:
        """Update the status label under the call-to-action."""
        if message:
            self._status_label.setText(message)
            self._status_label.show()
        else:
            self._status_label.clear()
            self._status_label.hide()

    def use_default_messages(self) -> None:
        """Restore the default translated call-to-action texts."""
        self._main_text_override = None
        self._secondary_text_override = None
        self._formats_text_override = None
        self._apply_translations()

    def set_drop_target(self, drop_target: QWidget | None) -> None:
        """Set the explicit drag-and-drop target for forwarded events."""
        self._drop_target = drop_target

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        spacer_top = QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        spacer_bottom = QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        root_layout.addItem(spacer_top)

        container = QFrame(self)
        container.setObjectName("startOverlayContainer")
        container.setMaximumWidth(880)
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        # 枠コンテナも掲載対象から除外
        container.setProperty("doc.include", False)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(48, 48, 48, 48)
        container_layout.setSpacing(24)

        icon_label = QLabel("📁", container)
        icon_label.setProperty("doc.include", False)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet(f"font-size: {Fonts.SIZE_ICON_XL};")

        self._main_label = QLabel("", container)
        self._main_label.setProperty("doc.include", False)
        self._main_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._main_label.setWordWrap(True)
        self._main_label.setStyleSheet(
            f"font-size: {Fonts.SIZE_DISPLAY}; font-weight: 600; color: {Colors.TEXT_PRIMARY};"
        )

        self._secondary_label = QLabel("", container)
        self._secondary_label.setProperty("doc.include", False)
        self._secondary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._secondary_label.setWordWrap(True)
        self._secondary_label.setStyleSheet(
            f"font-size: {Fonts.SIZE_LARGE}; color: {Colors.TEXT_SECONDARY};"
        )

        self._formats_label = QLabel("", container)
        self._formats_label.setProperty("doc.include", False)
        self._formats_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._formats_label.setWordWrap(True)
        self._formats_label.setStyleSheet(
            f"font-size: {Fonts.SIZE_NORMAL}; color: {Colors.TEXT_DISABLED};"
        )

        self._status_label = QLabel("", container)
        self._status_label.setProperty("doc.include", False)
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setWordWrap(True)
        status_color = Colors.WARNING
        self._status_label.setStyleSheet(f"font-size: {Fonts.SIZE_MEDIUM}; color: {status_color};")
        self._status_label.hide()

        container_layout.addWidget(icon_label)
        container_layout.addWidget(self._main_label)
        container_layout.addWidget(self._formats_label)
        container_layout.addWidget(self._secondary_label)
        container_layout.addWidget(self._status_label)

        container_row = QHBoxLayout()
        container_row.setContentsMargins(0, 0, 0, 0)
        container_row.addStretch(1)
        container_row.addWidget(container)
        container_row.addStretch(1)
        root_layout.addLayout(container_row)
        root_layout.addItem(spacer_bottom)

        self._drop_frame = container
        self.set_status_message(None)

    def _apply_base_style(self) -> None:
        self.setStyleSheet(
            "#startModeOverlay {"
            f" background-color: {Colors.BACKGROUND_MAIN};"
            "}"
            "#startOverlayContainer {"
            f" border: 2px dashed {Colors.BORDER_DEFAULT};"
            f" background-color: {Colors.BACKGROUND_PANEL};"
            f" border-radius: 12px;"
            "}"
            "#startOverlayContainer QLabel {"
            " background-color: transparent;"
            "}"
        )

    def _set_highlight(self, enabled: bool) -> None:
        if self._highlighted == enabled:
            return

        self._highlighted = enabled
        border_color = ModeContextColors.ORGANIZE if enabled else Colors.BORDER_DEFAULT
        border_style = "solid" if enabled else "dashed"
        border_width = "3px" if enabled else "2px"

        style = (
            "#startOverlayContainer {"
            f" border: {border_width} {border_style} {border_color};"
            f" background-color: {Colors.BACKGROUND_PANEL};"
            f" border-radius: 12px;"
            "}"
            "#startOverlayContainer QLabel {"
            " background-color: transparent;"
            "}"
        )
        self._drop_frame.setStyleSheet(style)

    def _forward_drag_event(
        self,
        method_name: str,
        event: QDragEnterEvent | QDragMoveEvent | QDragLeaveEvent | QDropEvent,
    ) -> None:
        if self._drop_target is None:
            return

        if method_name == "dragEnterEvent" and isinstance(event, QDragEnterEvent):
            self._drop_target.dragEnterEvent(event)
            return
        if method_name == "dragMoveEvent" and isinstance(event, QDragMoveEvent):
            self._drop_target.dragMoveEvent(event)
            return
        if method_name == "dragLeaveEvent" and isinstance(event, QDragLeaveEvent):
            self._drop_target.dragLeaveEvent(event)
            return
        if method_name == "dropEvent" and isinstance(event, QDropEvent):
            self._drop_target.dropEvent(event)
            return

        msg = (
            f"Unsupported start overlay drag method or event type: "
            f"{method_name}, {type(event).__name__}"
        )
        raise ValueError(msg)

    def _apply_translations(self) -> None:
        main_text = self._main_text_override
        if main_text is None:
            main_text = self.tr("Drop files here")
        self._main_label.setText(main_text)

        secondary_text = self._secondary_text_override
        if secondary_text is None:
            secondary_text = self.tr("or use New / Open")
        if secondary_text:
            self._secondary_label.setText(secondary_text)
            self._secondary_label.show()
        else:
            self._secondary_label.clear()
            self._secondary_label.hide()

        formats_text = self._formats_text_override
        if formats_text is None:
            formats_text = self.tr("FITS (flux + error)\nProject (.h5 or .hdf5)")
        self._formats_label.setText(formats_text)
