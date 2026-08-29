"""Unified context bar widget that combines toolbar and mode information."""

from __future__ import annotations

from dataclasses import dataclass
from textwrap import dedent
from typing import TYPE_CHECKING

from PySide6.QtCore import QT_TRANSLATE_NOOP, QEvent, QSize, Qt, Signal
from PySide6.QtGui import QPainter, QPaintEvent, QPalette, QResizeEvent
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from chappy.core.editing_mode import MODE_WORKFLOW_ORDER
from chappy.gui.shell.actions.ids import ShellActionId
from chappy.gui.shell.shortcuts import format_runtime_shortcuts
from chappy.gui.theme import (
    Colors,
    Fonts,
    Spacing,
    mode_segmented_control_style,
    toolbar_tool_button_style,
)
from chappy.gui.visual_tokens import LayoutMetrics

if TYPE_CHECKING:
    from chappy.core.editing_mode import EditingMode


@dataclass
class ModeContextConfig:
    """Configuration for mode context display.

    Note:
        ``icon`` and ``title`` are kept for callers (status messages, etc.) but
        the context bar itself no longer renders them: they duplicated the
        active mode button right next to the info section. Only ``subtitle``
        affects the bar's info section; its background is a fixed neutral shared
        across modes (mode identity is already carried by the active mode
        button, so a per-mode tint added no signal and its red-brown analysis
        variant misread as a danger state).
    """

    icon: str
    title: str
    subtitle: str | None = None


@dataclass(frozen=True, slots=True)
class _ButtonTemplate:
    """Static template describing a button's icon and Qt source text.

    Attributes:
        icon: Icon prefix displayed beside the button text.
        text: Qt source text for the button label.
        tooltip: Qt source text for the button tooltip.
    """

    icon: str
    text: str
    tooltip: str


@dataclass(slots=True)
class _ButtonTranslationData:
    """Translation metadata bundle for button widgets."""

    button: QAbstractButton
    icon: str
    text: str
    tooltip: str


_TOOLBAR_BUTTON_TEMPLATES: dict[ShellActionId, _ButtonTemplate] = {
    ShellActionId.OPEN_OBSERVATION_DATA: _ButtonTemplate(
        icon="📄",
        text=str(QT_TRANSLATE_NOOP("ModeContextBar", "New")),
        tooltip=str(
            QT_TRANSLATE_NOOP("ModeContextBar", "Load observed flux and error FITS files")
        ),
    ),
    ShellActionId.OPEN_PROJECT: _ButtonTemplate(
        icon="📂",
        text=str(QT_TRANSLATE_NOOP("ModeContextBar", "Open")),
        #: Keep {open_project_shortcut} unchanged; it is replaced for the running OS.
        tooltip=str(QT_TRANSLATE_NOOP("ModeContextBar", "Open project ({open_project_shortcut})")),
    ),
    ShellActionId.SAVE_PROJECT: _ButtonTemplate(
        icon="💾",
        text=str(QT_TRANSLATE_NOOP("ModeContextBar", "Save")),
        #: Keep {save_project_shortcut} unchanged; it is replaced for the running OS.
        tooltip=str(QT_TRANSLATE_NOOP("ModeContextBar", "Save project ({save_project_shortcut})")),
    ),
    ShellActionId.UNDO: _ButtonTemplate(
        icon="↶",
        text=str(QT_TRANSLATE_NOOP("ModeContextBar", "Undo")),
        #: Keep {undo_shortcut} unchanged; it is replaced for the running OS.
        tooltip=str(QT_TRANSLATE_NOOP("ModeContextBar", "Undo last action ({undo_shortcut})")),
    ),
    ShellActionId.REDO: _ButtonTemplate(
        icon="↷",
        text=str(QT_TRANSLATE_NOOP("ModeContextBar", "Redo")),
        #: Keep {redo_shortcut} unchanged; it is replaced for the running OS.
        tooltip=str(
            QT_TRANSLATE_NOOP("ModeContextBar", "Redo last undone action ({redo_shortcut})")
        ),
    ),
}


_MODE_BUTTON_TEMPLATES: dict[ShellActionId, _ButtonTemplate] = {
    ShellActionId.IDENTIFY_MODE: _ButtonTemplate(
        icon="🔍",
        text=str(QT_TRANSLATE_NOOP("ModeContextBar", "Identify")),
        tooltip=str(QT_TRANSLATE_NOOP("ModeContextBar", "Identify mode")),
    ),
    ShellActionId.ANALYSIS_MODE: _ButtonTemplate(
        icon="⚙️",
        text=str(QT_TRANSLATE_NOOP("ModeContextBar", "Analysis")),
        tooltip=str(QT_TRANSLATE_NOOP("ModeContextBar", "Analysis workspace")),
    ),
    ShellActionId.CONTINUUM_MODE: _ButtonTemplate(
        icon="〰",
        text=str(QT_TRANSLATE_NOOP("ModeContextBar", "Continuum")),
        tooltip=str(QT_TRANSLATE_NOOP("ModeContextBar", "Continuum editing mode")),
    ),
}


def _tooltip_with_label(*, label: str, tooltip: str) -> str:
    """Ensure a tooltip carries the button label for icon-only presentation.

    Args:
        label: Translated button label.
        tooltip: Translated tooltip text.

    Returns:
        Tooltip guaranteed to contain the label.
    """
    if label.casefold() in tooltip.casefold():
        return tooltip
    return f"{label} — {tooltip}"


def _lock_minimum_width(button: QAbstractButton) -> None:
    """Lock a button's minimum width to its size hint.

    This prevents the layout from squeezing the button below the width of its
    current text, so labels never degrade into a bare ellipsis or a clipped
    glyph.

    Args:
        button: Button whose minimum width should track its size hint.
    """
    button.setMinimumWidth(button.sizeHint().width())


class _ElidedLabel(QLabel):
    """Label that elides overflowing text instead of forcing a full-width minimum.

    ``QLabel.minimumSizeHint`` normally equals the full text width, which
    prevents the surrounding layout from ever shrinking the label. This
    subclass reports a small minimum width and paints right-elided text so the
    context bar can compress gracefully; the full text stays available via the
    tooltip (managed by the caller).
    """

    _MINIMUM_TEXT_WIDTH = 24

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        """Allow the layout to shrink the label below its full text width."""
        hint = super().minimumSizeHint()
        return QSize(min(hint.width(), self._MINIMUM_TEXT_WIDTH), hint.height())

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        """Paint the label text elided to the available width."""
        del event
        painter = QPainter(self)
        rect = self.contentsRect()
        elided = self.fontMetrics().elidedText(
            self.text(), Qt.TextElideMode.ElideRight, rect.width()
        )
        painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        flags = int(
            Qt.AlignmentFlag.AlignLeft.value
            | Qt.AlignmentFlag.AlignVCenter.value
            | Qt.TextFlag.TextSingleLine.value
        )
        painter.drawText(rect, flags, elided)


_MODE_ACTION_NAMES: dict[ShellActionId, str] = {
    ShellActionId.IDENTIFY_MODE: "IDENTIFY",
    ShellActionId.ANALYSIS_MODE: "ANALYSIS",
    ShellActionId.CONTINUUM_MODE: "CONTINUUM",
}

_MODE_ACTION_BY_EDITING_MODE: dict[str, ShellActionId] = {
    "identify": ShellActionId.IDENTIFY_MODE,
    "analysis": ShellActionId.ANALYSIS_MODE,
    "continuum": ShellActionId.CONTINUUM_MODE,
}


class ModeContextBar(QFrame):
    """Unified toolbar and mode context bar.

    This widget provides:
    - Common file operations (New/Open Project/Save)
    - Edit operations (Undo/Redo)
    - View operations (Zoom)
    - Mode switching buttons
    - Mode-specific information display
    """

    _ZOOM_ICON_INACTIVE = "🔍"
    _ZOOM_ICON_ACTIVE = "🔲"

    # Signals
    toolbar_action_triggered = Signal(object)  # ShellActionId
    zoom_rect_toggled = Signal(bool)
    mode_switch_requested = Signal(object)  # ShellActionId

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the unified context bar."""
        super().__init__(parent)
        self.setObjectName("modeContextBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumHeight(LayoutMetrics.CTXBAR_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._tool_buttons: dict[ShellActionId, QToolButton] = {}
        self._mode_buttons: dict[ShellActionId, QPushButton] = {}
        self._mode_button_group: QButtonGroup | None = None

        self._tool_button_specs: dict[ShellActionId, _ButtonTranslationData] = {}
        self._mode_button_specs: dict[ShellActionId, _ButtonTranslationData] = {}
        self._zoom_button: QToolButton | None = None

        # Width-adaptive degradation state: when the bar is narrower than the
        # width required by full "icon + label" tool buttons, file/edit/view
        # tool buttons fall back to icon-only (mode buttons always keep text).
        self._compact_tools = False
        self._expanded_min_width = 0

        self._init_ui()
        self._stylesheet_template = dedent(
            """
            #modeContextBar {{
                background-color: {Colors.BACKGROUND_PANEL};
                border-bottom: 1px solid {Colors.BORDER_DEFAULT};
            }}

            QToolButton {{
                background-color: transparent;
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid transparent;
                padding: {Spacing.SM} {Spacing.MD};
                border-radius: 4px;
                font-size: {Fonts.SIZE_NORMAL};
            }}

            QToolButton:hover {{
                background-color: {Colors.BACKGROUND_WIDGET};
                border-color: {Colors.BORDER_DEFAULT};
            }}

            QToolButton:pressed {{
                background-color: {Colors.BACKGROUND_INPUT};
            }}

            QToolButton:disabled {{
                color: {Colors.TEXT_DISABLED};
            }}

            QFrame#modeContextSeparator {{
                background-color: {Colors.BORDER_DEFAULT};
                border: none;
                margin: 0 8px;
            }}

            """
        )
        self.setStyleSheet(
            self._stylesheet_template.format(Colors=Colors, Fonts=Fonts, Spacing=Spacing)
        )
        self._retranslate_ui()

    def _init_ui(self) -> None:
        """Initialize the UI layout."""
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(12, 6, 12, 6)
        self._layout.setSpacing(16)

        # File operations section
        self._create_file_section()

        # Separator
        self._add_separator()

        # Edit operations section
        self._create_edit_section()

        # Separator
        self._add_separator()

        # View operations section
        self._create_view_section()

        # Mode switching section, left-aligned right after the tool groups.
        self._create_mode_section()
        self._layout.addStretch(1)

        # Mode information section
        self._create_info_section()

    def _create_file_section(self) -> None:
        """Create file operation buttons."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Open Observation Data
        observation_btn = self._create_tool_button(ShellActionId.OPEN_OBSERVATION_DATA)
        layout.addWidget(observation_btn)

        # Open Project
        open_btn = self._create_tool_button(ShellActionId.OPEN_PROJECT)
        layout.addWidget(open_btn)

        # Save Project
        save_btn = self._create_tool_button(ShellActionId.SAVE_PROJECT)
        save_btn.setEnabled(False)  # Initially disabled
        layout.addWidget(save_btn)

        self._layout.addWidget(container)

    def _create_edit_section(self) -> None:
        """Create edit operation buttons."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Undo
        undo_btn = self._create_tool_button(ShellActionId.UNDO)
        undo_btn.setEnabled(False)  # Initially disabled
        layout.addWidget(undo_btn)

        # Redo
        redo_btn = self._create_tool_button(ShellActionId.REDO)
        redo_btn.setEnabled(False)  # Initially disabled
        layout.addWidget(redo_btn)

        self._layout.addWidget(container)

    def _create_view_section(self) -> None:
        """Create view operation buttons."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Rectangle Zoom Mode
        zoom_rect_btn = QToolButton()
        zoom_rect_btn.setCheckable(True)
        zoom_rect_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        zoom_rect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        zoom_rect_btn.setEnabled(False)  # Initially disabled
        zoom_rect_btn.setObjectName("modeContextBar_zoom_rect")

        # Add visual feedback for checked state
        zoom_rect_btn.setStyleSheet(toolbar_tool_button_style())

        self._zoom_button = zoom_rect_btn
        self._refresh_zoom_button_state(zoom_rect_btn.isChecked())

        zoom_rect_btn.toggled.connect(self._refresh_zoom_button_state)
        zoom_rect_btn.toggled.connect(self.zoom_rect_toggled.emit)
        layout.addWidget(zoom_rect_btn)
        self._tool_buttons[ShellActionId.ZOOM_RECT] = zoom_rect_btn

        self._layout.addWidget(container)

    def _create_mode_section(self) -> None:
        """Create the content-width segmented mode selector."""
        container = QFrame()
        container.setObjectName("modeSegmentedControl")
        container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        container.setStyleSheet(mode_segmented_control_style())
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)

        # Create button group for exclusive selection
        self._mode_button_group = QButtonGroup(self)
        self._mode_button_group.setExclusive(True)

        # Buttons follow the canonical workflow order (core.editing_mode.MODE_WORKFLOW_ORDER).
        last_index = len(MODE_WORKFLOW_ORDER) - 1
        for index, mode in enumerate(MODE_WORKFLOW_ORDER):
            action_id = _MODE_ACTION_BY_EDITING_MODE[mode.value]
            button = self._create_mode_button(action_id)
            position = "first" if index == 0 else "last" if index == last_index else "middle"
            button.setProperty("segmentPosition", position)
            layout.addWidget(button)

        self._layout.addWidget(container)

    def _create_info_section(self) -> None:
        """Create the mode information display section.

        Only the subtitle (mode description) is shown here. The mode title and
        icon are intentionally omitted: they duplicated the active mode button
        rendered immediately to the left of this section.
        """
        container = QWidget()
        container.setObjectName("modeContextBar_infoGroup")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._mode_subtitle = _ElidedLabel()
        self._subtitle_base_style = (
            f"font-size: {Fonts.SIZE_SMALL}; color: {Colors.TEXT_SECONDARY};"
        )
        self._mode_subtitle.setStyleSheet(self._subtitle_base_style)
        self._mode_subtitle.setObjectName("modeContextBar_subtitle")
        layout.addWidget(self._mode_subtitle)

        self._info_group = container
        # Hidden until a mode config provides a subtitle.
        container.hide()
        self._layout.addWidget(container)

    def _create_tool_button(self, action: ShellActionId) -> QToolButton:
        """Create a tool button with icon and translated labels."""
        template = _TOOLBAR_BUTTON_TEMPLATES[action]
        button = QToolButton()
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setObjectName(f"modeContextBar_{action.value}")
        button.clicked.connect(lambda: self.toolbar_action_triggered.emit(action))
        spec = _ButtonTranslationData(
            button=button, icon=template.icon, text=template.text, tooltip=template.tooltip
        )
        self._tool_button_specs[action] = spec
        self._tool_buttons[action] = button
        self._apply_button_translation(spec, icon_only=self._compact_tools)
        return button

    def set_zoom_mode_active(self, active: bool) -> None:
        """Set the zoom mode button state.

        Args:
            active: Whether zoom mode is active
        """
        if ShellActionId.ZOOM_RECT in self._tool_buttons:
            button = self._tool_buttons[ShellActionId.ZOOM_RECT]
            button.setChecked(active)

    def _create_mode_button(self, action_id: ShellActionId) -> QPushButton:
        """Create a mode switching button with translations."""
        template = _MODE_BUTTON_TEMPLATES[action_id]
        button = QPushButton()
        button.setCheckable(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setObjectName(f"modeButton_{_MODE_ACTION_NAMES[action_id]}")
        button.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        button.clicked.connect(lambda: self.mode_switch_requested.emit(action_id))

        spec = _ButtonTranslationData(
            button=button, icon=template.icon, text=template.text, tooltip=template.tooltip
        )
        self._mode_button_specs[action_id] = spec
        self._mode_buttons[action_id] = button
        if self._mode_button_group is not None:
            self._mode_button_group.addButton(button)
        self._apply_button_translation(spec, icon_only=False)
        return button

    def _add_separator(self) -> None:
        """Add a vertical separator line."""
        separator = QFrame()
        separator.setObjectName("modeContextSeparator")
        separator.setFrameShape(QFrame.Shape.NoFrame)
        # Give separators an explicit size so stylesheets can render a 1px divider line.
        separator.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        separator.setFixedWidth(1)
        self._layout.addWidget(separator)

    def _apply_button_translation(self, spec: _ButtonTranslationData, *, icon_only: bool) -> None:
        """Apply the current Qt translation to a button.

        The icon glyph and label are kept separate so the compact (icon-only)
        presentation never leaves a partially elided label behind. The button
        minimum width is locked to its size hint so the layout can never
        squeeze the visible text into a bare ellipsis.

        Args:
            spec: Button metadata containing source text and icon.
            icon_only: Whether to show only the icon glyph (compact mode).
        """
        text = self.tr(spec.text)
        tooltip = format_runtime_shortcuts(self.tr(spec.tooltip))
        if icon_only and spec.icon:
            spec.button.setText(spec.icon)
            tooltip = _tooltip_with_label(label=text, tooltip=tooltip)
        elif spec.icon:
            spec.button.setText(f"{spec.icon} {text}")
        else:
            spec.button.setText(text)

        spec.button.setToolTip(tooltip)
        _lock_minimum_width(spec.button)

    def _retranslate_ui(self) -> None:
        """Apply current Qt translations to all context bar button text."""
        self._apply_tool_presentation(icon_only=self._compact_tools)
        self._equalize_mode_button_heights()
        self._refresh_expanded_min_width()
        self._update_tool_density(self.width())

    def _equalize_mode_button_heights(self) -> None:
        """Give every segment the tallest translated mode-button height."""
        if not self._mode_buttons:
            return
        height = max(button.sizeHint().height() for button in self._mode_buttons.values())
        for button in self._mode_buttons.values():
            button.setFixedHeight(height)

    def _apply_tool_presentation(self, *, icon_only: bool) -> None:
        """Apply the requested density to file, edit, and view buttons.

        Mode segments always retain their labels because the mode identity is
        essential navigation state. In compact presentation only general tool
        buttons become icon-only and the subtitle info group is hidden.

        Args:
            icon_only: Whether buttons should show only their icon glyph.
        """
        for spec in self._tool_button_specs.values():
            self._apply_button_translation(spec, icon_only=icon_only)
        for spec in self._mode_button_specs.values():
            self._apply_button_translation(spec, icon_only=False)
        self._apply_zoom_presentation(icon_only=icon_only)
        self._info_group.setVisible(not icon_only and bool(self._mode_subtitle.text()))

    def _refresh_expanded_min_width(self) -> None:
        """Recompute the width required by the fully expanded presentation.

        The threshold is measured with every tool button showing its full
        "icon + label" text (the subtitle label already reports a small
        minimum). ``resizeEvent`` compares the bar width against this value to
        decide when to degrade tool buttons to icon-only.
        """
        if self._compact_tools:
            self._apply_tool_presentation(icon_only=False)
        self._layout.invalidate()
        self._expanded_min_width = self._layout.minimumSize().width()
        if self._compact_tools:
            self._apply_tool_presentation(icon_only=True)

    def _update_tool_density(self, available_width: int) -> None:
        """Switch tool buttons between full and icon-only presentation.

        Args:
            available_width: Current width available to the context bar.
        """
        compact = 0 < available_width < self._expanded_min_width
        if compact == self._compact_tools:
            return
        self._compact_tools = compact
        self._apply_tool_presentation(icon_only=compact)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        """Adapt tool button density to the new bar width.

        Args:
            event: Qt resize event.
        """
        super().resizeEvent(event)
        self._update_tool_density(event.size().width())

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        """Report a width-free minimum so the window can shrink below the bar.

        Without this, the expanded layout's minimum width would propagate to
        the main window and prevent it from ever reaching the width where the
        compact (icon-only) presentation takes over.

        Returns:
            Minimum size with an unconstrained width.
        """
        hint = super().minimumSizeHint()
        return QSize(0, hint.height())

    def _refresh_zoom_button_state(self, checked: bool) -> None:
        """Refresh the zoom button icon, label, and tooltip.

        Args:
            checked: Whether rectangle zoom mode is active.
        """
        del checked
        self._apply_zoom_presentation(icon_only=self._compact_tools)

    def _apply_zoom_presentation(self, *, icon_only: bool) -> None:
        """Refresh the zoom button text and tooltip for the given density.

        Args:
            icon_only: Whether to show only the zoom icon glyph.
        """
        if self._zoom_button is None:
            return

        checked = self._zoom_button.isChecked()
        text = self.tr("Zoom")
        icon = self._ZOOM_ICON_ACTIVE if checked else self._ZOOM_ICON_INACTIVE
        if checked:
            tooltip = self.tr("Rectangle zoom mode active - Click again to disable")
        else:
            tooltip = self.tr("Click and drag to zoom to selected area")

        if icon_only:
            self._zoom_button.setText(icon)
            tooltip = _tooltip_with_label(label=text, tooltip=tooltip)
        else:
            self._zoom_button.setText(f"{icon} {text}")
        self._zoom_button.setToolTip(tooltip)
        _lock_minimum_width(self._zoom_button)

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        """Retranslate the context bar when Qt sends a language change event.

        Args:
            event: Qt change event.
        """
        if event.type() == QEvent.Type.LanguageChange:
            self._retranslate_ui()
        super().changeEvent(event)

    def apply_config(self, config: ModeContextConfig) -> None:
        """Apply a mode configuration.

        Args:
            config: Configuration for mode display
        """
        # Only the subtitle is rendered; config.icon/config.title duplicate
        # the active mode button and are intentionally not displayed.
        self.update_subtitle(config.subtitle)

    def set_current_mode(self, mode: EditingMode) -> None:
        """Set the currently active mode.

        Args:
            mode: The editing mode to activate
        """
        action_id = _MODE_ACTION_BY_EDITING_MODE.get(mode.value)

        # Update mode button states
        for mode_key, button in self._mode_buttons.items():
            button.setChecked(action_id is not None and mode_key is action_id)

    def update_subtitle(self, subtitle: str | None, color: str | None = None) -> None:
        """Update the subtitle text and optional color."""
        if not subtitle:
            self._mode_subtitle.clear()
            self._mode_subtitle.setToolTip("")
            self._mode_subtitle.setStyleSheet(self._subtitle_base_style)
            self._info_group.hide()
            return

        style = (
            self._subtitle_base_style
            if not color
            else (f"font-size: {Fonts.SIZE_SMALL}; color: {color};")
        )
        if self._mode_subtitle.styleSheet() != style:
            self._mode_subtitle.setStyleSheet(style)

        self._mode_subtitle.setText(subtitle)
        # The subtitle elides when space is tight; keep the full text reachable.
        self._mode_subtitle.setToolTip(subtitle)
        self._info_group.setVisible(not self._compact_tools)

    def set_tool_enabled(self, action: ShellActionId, enabled: bool) -> None:
        """Enable or disable a toolbar action.

        Args:
            action: The toolbar action
            enabled: Whether to enable the action
        """
        if action in self._tool_buttons:
            self._tool_buttons[action].setEnabled(enabled)

    def set_mode_enabled(self, action_id: ShellActionId, enabled: bool) -> None:
        """Enable or disable a mode button.

        Args:
            action_id: The mode action identifier.
            enabled: Whether to enable the mode
        """
        if action_id in self._mode_buttons:
            self._mode_buttons[action_id].setEnabled(enabled)

    def set_project_loaded(self, has_project: bool) -> None:
        """Update button states based on project availability.

        Args:
            has_project: Whether a project is loaded
        """
        # Enable/disable project-dependent actions
        self.set_tool_enabled(ShellActionId.SAVE_PROJECT, has_project)
        self.set_tool_enabled(ShellActionId.ZOOM_RECT, has_project)

        # Enable/disable mode buttons
        self.set_mode_enabled(ShellActionId.IDENTIFY_MODE, has_project)
        self.set_mode_enabled(ShellActionId.ANALYSIS_MODE, has_project)
        self.set_mode_enabled(ShellActionId.CONTINUUM_MODE, has_project)

    @staticmethod
    def start_mode(title: str, subtitle: str | None) -> ModeContextConfig:
        """Create a configuration for start mode."""
        return ModeContextConfig(icon="📁", title=title, subtitle=subtitle)

    @staticmethod
    def continuum_mode(title: str, subtitle: str | None) -> ModeContextConfig:
        """Create a configuration for continuum mode."""
        return ModeContextConfig(icon="〰", title=title, subtitle=subtitle)

    @staticmethod
    def analysis_mode(title: str, subtitle: str | None) -> ModeContextConfig:
        """Create a configuration for the Analysis workspace."""
        return ModeContextConfig(icon="⚙️", title=title, subtitle=subtitle)

    @staticmethod
    def identify_mode(title: str, subtitle: str | None) -> ModeContextConfig:
        """Create a configuration for identify mode."""
        return ModeContextConfig(icon="🔍", title=title, subtitle=subtitle)
