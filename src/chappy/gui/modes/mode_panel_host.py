"""Container that swaps side panel widgets based on the active editing mode."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtWidgets import QLabel, QSizePolicy, QStackedLayout, QVBoxLayout, QWidget

from chappy.core.editing_mode import EditingMode
from chappy.gui.theme import Colors, Fonts

if TYPE_CHECKING:
    from chappy.gui.modes.common.contracts import ModePanelRegistration


class ModeSidePanelHost(QWidget):
    """Host mode-specific side panel widgets and switch them on demand."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the mode-aware side panel container.

        Args:
            parent: Parent widget for the side panel.
        """
        super().__init__(parent)
        self.setObjectName("modeSidePanel")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # No descendant QWidget rule here: widget-level sheets outrank the
        # application sheet, so it would wipe QPushButton[variant=...] fills.
        self.setStyleSheet(f"#modeSidePanel {{ background-color: {Colors.BACKGROUND_PANEL}; }}")

        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.setSpacing(0)

        self._mode_indices: dict[EditingMode, int] = {}
        self._placeholder_label: QLabel | None = None
        self._placeholder_is_start = True

        placeholder = self._create_placeholder()
        self._placeholder_index = self._stack.addWidget(placeholder)

    @override
    def minimumSizeHint(self) -> QSize:
        """Return the active page's minimum instead of every stacked page's maximum."""
        page = self._stack.currentWidget()
        if page is None:
            return QSize(0, 0)

        hint = page.minimumSizeHint()
        explicit_minimum = page.minimumSize()
        margins = self._stack.contentsMargins()
        return QSize(
            max(0, hint.width(), explicit_minimum.width()) + margins.left() + margins.right(),
            max(0, hint.height(), explicit_minimum.height()) + margins.top() + margins.bottom(),
        )

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        """Handle Qt language changes for already visible placeholders.

        Args:
            event: Qt change event delivered to this widget.
        """
        if event.type() == QEvent.Type.LanguageChange:
            self._retranslate_ui()
        super().changeEvent(event)

    def register_panel(self, mode: EditingMode, panel: QWidget) -> None:
        """Register a widget to display when the given mode is active.

        Args:
            mode: Editing mode associated with the side panel.
            panel: Widget to display for the mode.
        """
        if panel.parent() is not self:
            panel.setParent(self)
        panel.setObjectName(f"modeSidePanel_{mode.value}")
        index = self._stack.addWidget(panel)
        self._mode_indices[mode] = index

    def register_panel_entry(self, registration: ModePanelRegistration) -> None:
        """Register a mode panel entry.

        Args:
            registration: Mode panel registration produced by a mode module.

        Raises:
            TypeError: If the registration panel is not a QWidget.
            RuntimeError: If the registration lifecycle is missing.
        """
        if not isinstance(registration.panel, QWidget):
            msg = "Mode panel registration must contain a QWidget"
            raise TypeError(msg)
        if registration.lifecycle is None:
            msg = f"Mode panel registration for {registration.mode.value} is missing lifecycle"
            raise RuntimeError(msg)
        self.register_panel(registration.mode, registration.panel)

    def activate_mode(self, mode: EditingMode | None) -> None:
        """Show the panel associated with ``mode`` or a placeholder when missing.

        Args:
            mode: Editing mode to activate, or None for the initial placeholder.
        """
        if mode is None:
            self._update_placeholder_text(start_hint=True)
            self._set_current_stack_index(self._placeholder_index)
            return

        if mode is EditingMode.START:
            self._update_placeholder_text(start_hint=True)
            self._set_current_stack_index(self._placeholder_index)
            return

        index = self._mode_indices.get(mode)
        if index is None:
            msg = f"No side panel registered for mode: {mode.value}"
            raise RuntimeError(msg)

        self._set_current_stack_index(index)
        self._placeholder_is_start = False

    def _set_current_stack_index(self, index: int) -> None:
        """Activate one page and publish its changed geometry requirements."""
        self._stack.setCurrentIndex(index)
        self.updateGeometry()

    def _create_placeholder(self) -> QWidget:
        """Create the placeholder shown when no mode panel is available.

        Returns:
            Placeholder widget containing the translated guidance label.
        """
        placeholder = QWidget(self)
        placeholder.setObjectName("modeSidePanelPlaceholder")
        placeholder.setStyleSheet(
            "#modeSidePanelPlaceholder {"
            f" background-color: {Colors.BACKGROUND_PANEL};"
            f" border-left: 1px solid {Colors.BORDER_DEFAULT};"
            "}"
        )

        layout = QVBoxLayout(placeholder)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addStretch()

        self._placeholder_label = QLabel("", placeholder)
        self._placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder_label.setStyleSheet(
            f"color: {Colors.TEXT_DISABLED}; font-size: {Fonts.SIZE_NORMAL};"
        )
        layout.addWidget(self._placeholder_label)
        self._update_placeholder_text()
        layout.addStretch()

        return placeholder

    def _retranslate_ui(self) -> None:
        """Refresh translatable text after a Qt translator changes."""
        self._update_placeholder_text()

    def _update_placeholder_text(self, *, start_hint: bool | None = None) -> None:
        """Update the placeholder label for the current placeholder state.

        Args:
            start_hint: Optional override for whether to show the start-mode hint.
        """
        if self._placeholder_label is None:
            return

        use_start_hint = self._placeholder_is_start if start_hint is None else start_hint
        if use_start_hint:
            self._placeholder_label.setText(
                self.tr("Open observation data or a project to see tools here.")
            )
        else:
            self._placeholder_label.setText(self.tr("No side panel available for this mode."))
        self._placeholder_is_start = use_start_hint
        self.updateGeometry()
