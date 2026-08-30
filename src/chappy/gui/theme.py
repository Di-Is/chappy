"""Unified theme system for the Chappy application GUI.

This module provides centralized styling constants and utility functions
to ensure consistent appearance across all GUI components.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QMenu

_FONT_POINT_CONVERSION = 0.75 * 1.3


def _format_point_size(px: int) -> str:
    """Convert logical pixels into Qt stylesheet point units with scaling.

    The default px tokens predate high-DPI adjustments. This helper maps them to
    point sizes and applies a 1.25× boost to compensate for smaller perceived
    text after the px→pt migration.

    Args:
        px: Logical pixel value defined by the design system.

    Returns:
        Stylesheet-ready point-value string (e.g., "11.25pt").
    """
    point_value = px * _FONT_POINT_CONVERSION
    if point_value.is_integer():
        size_repr = str(int(point_value))
    else:
        size_repr = f"{point_value:.2f}".rstrip("0").rstrip(".")
    return f"{size_repr}pt"


if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication, QPushButton, QWidget


# Color palette
class Colors:
    """Application color palette."""

    # Primary colors
    PRIMARY = "#4DA3FF"
    PRIMARY_HOVER = "#68B5FF"
    PRIMARY_PRESSED = "#3F94F8"

    # Secondary colors
    SECONDARY = "#8C96A9"
    SECONDARY_HOVER = "#9FB0C3"
    SECONDARY_PRESSED = "#8695AE"

    # Background colors
    BACKGROUND_MAIN = "#2B2B2B"
    BACKGROUND_PANEL = "#3A3A3A"
    BACKGROUND_WIDGET = "#4A4A4A"
    BACKGROUND_INPUT = "#555555"
    UI_ACCENT_MUTED = "#44475A"

    # Text colors
    TEXT_PRIMARY = "#FFFFFF"
    TEXT_SECONDARY = "#CCCCCC"
    TEXT_DISABLED = "#888888"

    # Border colors
    BORDER_DEFAULT = "#666666"
    BORDER_HOVER = "#888888"
    BORDER_FOCUS = "#4A90E2"
    BORDER_DISABLED = "#4C4C4C"

    # Status colors
    SUCCESS = "#40C087"
    WARNING = "#FFB347"
    WARNING_HOVER = "#FFC36A"
    WARNING_PRESSED = "#E89C2A"
    ERROR = "#FF6B6B"
    ERROR_HOVER = "#FF7F7F"
    ERROR_PRESSED = "#FF5A5A"
    INFO = "#3498DB"

    # TODO(Di-Is): refine these colors
    ACCENT_SELECTION_LIGHT = "#3D85C6"

    # Categorical accent colors for parameter tie sets (cycled by label index)
    TIE_ACCENT_COLORS = (
        "#4DA3FF",
        "#9B59B6",
        "#2ECC71",
        "#E67E22",
        "#1ABC9C",
        "#E91E63",
        "#F1C40F",
        "#95A5A6",
    )

    # Table-specific colors
    TABLE_BACKGROUND = "#2F3338"
    TABLE_ALT_BACKGROUND = "#292D31"
    TABLE_BORDER = "#44484E"
    TABLE_GRID = "#3A3E44"
    TABLE_HEADER = "#363A40"
    TABLE_SELECTION = "#455264"
    TEXT_ON_SELECTION = "#F4F6F8"


# Typography
class Fonts:
    """Font specifications."""

    FAMILY = "system-ui, -apple-system, sans-serif"
    # Application font must use the same point size (see __main__), otherwise
    # size hints computed from the widget font under-report the QSS-rendered
    # text and widgets overlap on native macOS.
    POINT_SIZE_NORMAL = 12
    POINT_SIZE_TINY = 10
    SIZE_TINY = _format_point_size(POINT_SIZE_TINY)
    SIZE_SMALL = _format_point_size(11)
    SIZE_NORMAL = _format_point_size(POINT_SIZE_NORMAL)
    SIZE_MEDIUM = _format_point_size(13)
    SIZE_LARGE = _format_point_size(14)
    SIZE_HEADER = _format_point_size(16)
    SIZE_DISPLAY = _format_point_size(24)
    SIZE_ICON_XL = _format_point_size(48)

    WEIGHT_NORMAL = "normal"
    WEIGHT_BOLD = "bold"

    # Point sizes for widgets that set QFont directly instead of stylesheets.
    POINT_ICON_MEDIUM = 16


# Spacing
class Spacing:
    """Spacing constants."""

    XS = "4px"
    SM = "8px"
    MD = "12px"
    LG = "16px"
    XL = "20px"


# Common widget styles
def compose_stylesheet(*styles: str) -> str:
    """Join individual style fragments into a single stylesheet string."""
    blocks = [block.strip() for block in styles if block and block.strip()]
    return "\n\n".join(blocks)


def widget_base_style() -> str:
    """Base styling shared by all widgets."""
    return f"""
    QAbstractScrollArea {{
        background-color: {Colors.BACKGROUND_WIDGET};
        color: {Colors.TEXT_PRIMARY};
    }}
    QAbstractScrollArea:disabled {{
        color: {Colors.TEXT_DISABLED};
    }}
    QAbstractItemView {{
        background-color: {Colors.TABLE_BACKGROUND};
        alternate-background-color: {Colors.TABLE_ALT_BACKGROUND};
        color: {Colors.TEXT_PRIMARY};
    }}
    QToolTip {{
        background-color: {Colors.BACKGROUND_PANEL};
        color: {Colors.TEXT_PRIMARY};
        border: 1px solid {Colors.BORDER_DEFAULT};
        padding: {Spacing.SM};
    }}
    """


def button_style() -> str:
    """Generate the neutral baseline styling shared by all push buttons.

    Color variants are opt-in via the ``variant`` property
    (see :func:`button_variant_style` and :func:`apply_button_variant`).
    """
    return f"""
    QPushButton {{
        background-color: {Colors.BACKGROUND_WIDGET};
        color: {Colors.TEXT_PRIMARY};
        border: 1px solid {Colors.BORDER_DEFAULT};
        border-radius: 6px;
        padding: {Spacing.SM} {Spacing.MD};
        min-height: 20px;
    }}
    QPushButton:hover {{
        background-color: {Colors.BACKGROUND_INPUT};
        border-color: {Colors.BORDER_HOVER};
    }}
    QPushButton:pressed {{
        background-color: {Colors.BACKGROUND_MAIN};
    }}
    QPushButton:disabled {{
        color: {Colors.TEXT_DISABLED};
        border-color: {Colors.BORDER_DISABLED};
    }}
    """


def _colored_button_variant_rule(name: str, color: str, hover: str, pressed: str) -> str:
    """Generate a solid-fill color variant rule for a given ``variant`` value."""
    return f"""
    QPushButton[variant="{name}"] {{
        background-color: {color};
        color: {Colors.TEXT_PRIMARY};
        border-color: {Colors.BORDER_DEFAULT};
    }}
    QPushButton[variant="{name}"]:hover {{
        background-color: {hover};
        border-color: {Colors.BORDER_HOVER};
    }}
    QPushButton[variant="{name}"]:pressed {{
        background-color: {pressed};
    }}
    QPushButton[variant="{name}"]:disabled {{
        background-color: {Colors.BACKGROUND_WIDGET};
        color: {Colors.TEXT_DISABLED};
        border-color: {Colors.BORDER_DEFAULT};
    }}
    """


def button_variant_style() -> str:
    """Generate all opt-in button color variants (`QPushButton[variant=...]`).

    This is the sole source of button color; there is no implicit
    `:default`-driven accent (see `action_row_button_style()`).
    """
    return compose_stylesheet(
        _colored_button_variant_rule(
            "primary", Colors.PRIMARY, Colors.PRIMARY_HOVER, Colors.PRIMARY_PRESSED
        ),
        _colored_button_variant_rule(
            "secondary", Colors.SECONDARY, Colors.SECONDARY_HOVER, Colors.SECONDARY_PRESSED
        ),
        _colored_button_variant_rule(
            "danger", Colors.ERROR, Colors.ERROR_HOVER, Colors.ERROR_PRESSED
        ),
        f"""
        QPushButton[variant="text"] {{
            background-color: transparent;
            color: {Colors.PRIMARY};
            border: 1px solid transparent;
            border-radius: 4px;
        }}
        QPushButton[variant="text"]:hover {{
            color: {Colors.PRIMARY_HOVER};
            background-color: {Colors.BACKGROUND_WIDGET};
        }}
        QPushButton[variant="text"]:pressed {{
            color: {Colors.PRIMARY_PRESSED};
        }}
        QPushButton[variant="text"]:disabled {{
            color: {Colors.TEXT_DISABLED};
        }}
        """,
        """
        QPushButton#tutorialBubbleNoteToggle {
            text-align: left;
            padding: 2px 0;
        }
        """,
    )


def mode_segmented_control_style() -> str:
    """Generate styling for the context-bar segmented mode selector."""
    return f"""
    QFrame#modeSegmentedControl {{
        background-color: {Colors.BORDER_DEFAULT};
        border: 1px solid {Colors.BORDER_DEFAULT};
        border-radius: 6px;
    }}
    QFrame#modeSegmentedControl QPushButton {{
        background-color: {Colors.BACKGROUND_WIDGET};
        color: {Colors.TEXT_SECONDARY};
        border: none;
        border-radius: 0;
        padding: {Spacing.SM} {Spacing.XL};
        font-size: {Fonts.SIZE_NORMAL};
        font-weight: {Fonts.WEIGHT_NORMAL};
    }}
    QFrame#modeSegmentedControl QPushButton[segmentPosition="first"] {{
        border-top-left-radius: 4px;
        border-bottom-left-radius: 4px;
    }}
    QFrame#modeSegmentedControl QPushButton[segmentPosition="last"] {{
        border-top-right-radius: 4px;
        border-bottom-right-radius: 4px;
    }}
    QFrame#modeSegmentedControl QPushButton:hover {{
        background-color: {Colors.BACKGROUND_INPUT};
        color: {Colors.TEXT_PRIMARY};
    }}
    QFrame#modeSegmentedControl QPushButton:checked {{
        background-color: {Colors.PRIMARY};
        color: {Colors.TEXT_PRIMARY};
        font-weight: {Fonts.WEIGHT_BOLD};
    }}
    QFrame#modeSegmentedControl QPushButton:checked:hover {{
        background-color: {Colors.PRIMARY_HOVER};
    }}
    QFrame#modeSegmentedControl QPushButton:checked:pressed {{
        background-color: {Colors.PRIMARY_PRESSED};
    }}
    QFrame#modeSegmentedControl QPushButton:disabled {{
        background-color: {Colors.BACKGROUND_WIDGET};
        color: {Colors.TEXT_DISABLED};
    }}
    """


def toolbar_tool_button_style() -> str:
    """Generate styling for toolbar tool buttons.

    Returns:
        str: Stylesheet fragment for toolbar tool buttons.
    """
    return f"""
    QToolButton {{
        background-color: transparent;
        color: {Colors.TEXT_PRIMARY};
        border: 1px solid transparent;
        border-radius: 4px;
        padding: {Spacing.SM} {Spacing.MD};
    }}
    QToolButton:hover {{
        background-color: {Colors.BACKGROUND_WIDGET};
        border: 1px solid {Colors.BORDER_DEFAULT};
    }}
    QToolButton:pressed {{
        background-color: {Colors.BACKGROUND_INPUT};
    }}
    QToolButton:checked {{
        background-color: {Colors.PRIMARY};
        color: {Colors.TEXT_PRIMARY};
        border: 1px solid {Colors.PRIMARY};
    }}
    QToolButton:checked:hover {{
        background-color: {Colors.PRIMARY_HOVER};
        border: 1px solid {Colors.PRIMARY_HOVER};
    }}
    QToolButton:checked:pressed {{
        background-color: {Colors.PRIMARY_PRESSED};
        border: 1px solid {Colors.PRIMARY_PRESSED};
    }}
    QToolButton:disabled {{
        color: {Colors.TEXT_DISABLED};
    }}
    """


def group_box_style() -> str:
    """Generate consistent group box styling."""
    return f"""
    QGroupBox {{
        font-weight: {Fonts.WEIGHT_BOLD};
        color: {Colors.TEXT_PRIMARY};
        border: 1px solid {Colors.BORDER_DEFAULT};
        border-radius: 6px;
        margin: {Spacing.SM} 0;
        padding-top: {Spacing.MD};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 {Spacing.SM};
        background-color: {Colors.BACKGROUND_PANEL};
        color: {Colors.TEXT_PRIMARY};
    }}
    """


def input_style() -> str:
    """Generate consistent input field styling."""
    return f"""
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background-color: {Colors.BACKGROUND_INPUT};
        color: {Colors.TEXT_PRIMARY};
        border: 1px solid {Colors.BORDER_DEFAULT};
        border-radius: 4px;
        padding: {Spacing.SM};
        min-height: 18px;
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
        border-color: {Colors.BORDER_FOCUS};
        background-color: {Colors.BACKGROUND_INPUT};
    }}
    QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
        background-color: {Colors.BACKGROUND_WIDGET};
        color: {Colors.TEXT_DISABLED};
    }}
    QLineEdit[error="true"], QSpinBox[error="true"], QDoubleSpinBox[error="true"], QComboBox[error="true"] {{
        border: 1px solid {Colors.ERROR};
    }}
    QComboBox::item:selected {{
        background-color: {Colors.PRIMARY};
        color: {Colors.TEXT_PRIMARY};
    }}
    """


def table_style() -> str:
    """Generate consistent table styling."""
    return f"""
    QTableWidget, QTableView, QTreeWidget {{
        background-color: {Colors.TABLE_BACKGROUND};
        alternate-background-color: {Colors.TABLE_ALT_BACKGROUND};
        color: {Colors.TEXT_PRIMARY};
        gridline-color: {Colors.TABLE_GRID};
        border: 1px solid {Colors.TABLE_BORDER};
        border-radius: 4px;
    }}
    QTableWidget::item, QTableView::item, QTreeWidget::item {{
        padding: {Spacing.SM};
        border: none;
    }}
    QTableWidget::item:selected, QTableView::item:selected, QTreeWidget::item:selected {{
        background-color: {Colors.TABLE_SELECTION};
        color: {Colors.TEXT_ON_SELECTION};
    }}
    QTableWidget::item:hover, QTableView::item:hover, QTreeWidget::item:hover {{
        background-color: {Colors.BACKGROUND_WIDGET};
    }}
    QHeaderView::section {{
        background-color: {Colors.TABLE_HEADER};
        color: {Colors.TEXT_PRIMARY};
        padding: {Spacing.SM};
        border: 1px solid {Colors.TABLE_BORDER};
        font-weight: {Fonts.WEIGHT_BOLD};
    }}
    QTableWidget#identifyCandidateTable::item {{
        padding: 2px 0;
    }}
    QTableWidget#identifyCandidateTable QHeaderView::section {{
        padding: 2px 1px;
    }}
    """


def list_style() -> str:
    """Generate list widget item spacing matching the table row rhythm."""
    # QListWidget only: QListView::item would also restyle QComboBox popups.
    return f"""
    QListWidget::item {{
        padding: {Spacing.XS} {Spacing.SM};
    }}
    """


def tab_widget_style() -> str:
    """Generate consistent tab widget styling."""
    return f"""
    QTabWidget::pane {{
        border: 1px solid {Colors.BORDER_DEFAULT};
        border-radius: 4px;
        background-color: {Colors.BACKGROUND_PANEL};
        margin-top: 2px;
    }}
    QTabBar::tab {{
        background-color: {Colors.BACKGROUND_WIDGET};
        color: {Colors.TEXT_SECONDARY};
        border: 1px solid {Colors.BORDER_DEFAULT};
        border-bottom: none;
        border-radius: 4px 4px 0 0;
        padding: {Spacing.SM} {Spacing.MD};
        margin-right: 2px;
        min-width: 60px;
    }}
    QTabBar::tab:selected {{
        background-color: {Colors.BACKGROUND_PANEL};
        color: {Colors.TEXT_PRIMARY};
        border-color: {Colors.BORDER_DEFAULT};
        font-weight: {Fonts.WEIGHT_BOLD};
    }}
    QTabBar::tab:hover:!selected {{
        background-color: {Colors.BACKGROUND_INPUT};
        color: {Colors.TEXT_PRIMARY};
    }}
    QTabBar::tab:first {{
        margin-left: 0;
    }}
    """


def dock_widget_style() -> str:
    """Generate consistent dock widget styling."""
    return f"""
    QDockWidget {{
        color: {Colors.TEXT_PRIMARY};
    }}
    QDockWidget::title {{
        background-color: {Colors.BACKGROUND_PANEL};
        color: {Colors.TEXT_PRIMARY};
        padding: {Spacing.SM};
        border: 1px solid {Colors.BORDER_DEFAULT};
        font-weight: {Fonts.WEIGHT_BOLD};
    }}
    """


def label_style() -> str:
    """Generate consistent label styling."""
    return f"""
    QLabel {{
        color: {Colors.TEXT_PRIMARY};
    }}
    """


def card_frame_style(object_name: str | None = None) -> str:
    """Provide a reusable card frame style for side panel sections."""
    selector = f"QFrame#{object_name}" if object_name else "QFrame"
    return f"""
    {selector} {{
        background-color: {Colors.BACKGROUND_PANEL};
        border: 1px solid {Colors.BORDER_DEFAULT};
        border-radius: 8px;
    }}
    """


def table_surface_frame_style(object_name: str) -> str:
    """Return a table-like frame style for stable list content surfaces."""
    return f"""
    QFrame#{object_name} {{
        background-color: {Colors.TABLE_BACKGROUND};
        border: 1px solid {Colors.TABLE_BORDER};
        border-radius: 4px;
    }}
    """


def empty_state_label_style(*, font_size: str | None = None, padding: str | None = None) -> str:
    """Return style string for empty-state placeholder labels."""
    resolved_font_size = font_size or Fonts.SIZE_SMALL
    resolved_padding = padding or Spacing.XL
    return f"""
    QLabel {{
        color: {Colors.TEXT_DISABLED};
        font-size: {resolved_font_size};
        padding: {resolved_padding};
    }}
    """


def _asset_url(name: str) -> str:
    return (Path(__file__).resolve().parent / "assets" / name).as_posix()


def checkbox_style() -> str:
    """Generate consistent checkbox and radio button styling.

    Indicators are drawn explicitly: Fusion derives its indicator outline by
    darkening the palette Window color, which is invisible on a dark theme.
    """
    check_url = _asset_url("check.svg")
    dot_url = _asset_url("radio_dot.svg")
    box_indicators = (
        "QCheckBox::indicator, QGroupBox::indicator, QTableWidget::indicator, "
        "QTableView::indicator, QTreeWidget::indicator, QListWidget::indicator"
    )
    return f"""
    QCheckBox {{
        color: {Colors.TEXT_PRIMARY};
        spacing: {Spacing.SM};
    }}
    QRadioButton {{
        color: {Colors.TEXT_PRIMARY};
        spacing: {Spacing.SM};
    }}
    {box_indicators}, QRadioButton::indicator {{
        width: 16px;
        height: 16px;
        border: 1px solid {Colors.BORDER_DEFAULT};
        background-color: {Colors.BACKGROUND_INPUT};
    }}
    {box_indicators} {{
        border-radius: 3px;
    }}
    QRadioButton::indicator {{
        border-radius: 9px;
    }}
    QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
        border-color: {Colors.BORDER_HOVER};
    }}
    {box_indicators.replace("::indicator", "::indicator:checked")} {{
        background-color: {Colors.PRIMARY};
        border-color: {Colors.PRIMARY};
        image: url("{check_url}");
    }}
    QRadioButton::indicator:checked {{
        background-color: {Colors.PRIMARY};
        border-color: {Colors.PRIMARY};
        image: url("{dot_url}");
    }}
    QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
        border-color: {Colors.BORDER_DISABLED};
        background-color: {Colors.BACKGROUND_WIDGET};
    }}
    QCheckBox::indicator:checked:disabled {{
        background-color: {Colors.UI_ACCENT_MUTED};
        border-color: {Colors.BORDER_DISABLED};
    }}
    """


def action_row_button_style() -> str:
    """Shared minimum footprint for the peer buttons of an action row.

    An action row is a dialog's commit/dismiss footer or a group of sibling
    commands operating on one view; its buttons line up only when they share a
    minimum. `QDialogButtonBox` declares that role structurally, hand-built
    rows declare it with `apply_action_row_sizing`. Coloring stays with
    `button_style()` and `button_variant_style()`; the width floor here is what
    `chappy.gui.dialog_sizing` compensates for when measuring labels.
    """
    return """
    QDialogButtonBox QPushButton,
    QPushButton[actionRow="true"] {
        min-width: 90px;
        min-height: 24px;
    }
    """


def menu_style() -> str:
    """Generate consistent menu bar and menu styling.

    ``QMenu QCheckBox`` / ``QMenu QLabel`` rules keep widget rows added via
    ``QWidgetAction`` aligned with plain ``QMenu::item`` rows: same vertical
    padding, and text starting at the shared indent.
    """
    item_text_indent = "32px"
    return f"""
    QMenuBar {{
        background-color: {Colors.BACKGROUND_PANEL};
        color: {Colors.TEXT_PRIMARY};
        spacing: {Spacing.SM};
        padding: 0 {Spacing.SM};
    }}
    QMenuBar::item {{
        background-color: transparent;
        color: {Colors.TEXT_PRIMARY};
        padding: {Spacing.SM} {Spacing.MD};
        border-radius: 4px;
    }}
    QMenuBar::item:selected {{
        background-color: {Colors.UI_ACCENT_MUTED};
    }}
    QMenuBar::item:pressed {{
        background-color: {Colors.PRIMARY};
    }}
    QMenu {{
        background-color: {Colors.BACKGROUND_PANEL};
        color: {Colors.TEXT_PRIMARY};
        border: 1px solid {Colors.BORDER_DEFAULT};
        padding: {Spacing.SM} 0;
    }}
    QMenu::item {{
        padding: {Spacing.SM} {Spacing.LG} {Spacing.SM} {item_text_indent};
        background-color: transparent;
    }}
    QMenu QCheckBox {{
        padding: {Spacing.SM} {Spacing.LG} {Spacing.SM} {Spacing.SM};
        spacing: {Spacing.SM};
    }}
    QMenu QLabel {{
        padding: {Spacing.SM} {Spacing.LG} {Spacing.SM} {item_text_indent};
        color: {Colors.TEXT_PRIMARY};
    }}
    QMenu QLabel[menuRowEnabled="false"] {{
        color: {Colors.TEXT_DISABLED};
    }}
    QMenu::item:selected {{
        background-color: {Colors.UI_ACCENT_MUTED};
        color: {Colors.TEXT_PRIMARY};
    }}
    QMenu::indicator {{
        width: 16px;
        height: 16px;
        left: {Spacing.SM};
    }}
    QMenu::indicator:non-exclusive {{
        width: 16px;
        height: 16px;
    }}
    QMenu::separator {{
        height: 1px;
        margin: {Spacing.SM} 0;
        background-color: {Colors.BORDER_DEFAULT};
    }}
    """


def main_splitter_style() -> str:
    """Style the main window splitter handle as a visible resize affordance.

    The grip dots themselves are painted by the handle widget
    (``gui/shell/window_layout_builder.py``) to match the Identify panel
    splitter; this rule supplies the normal and hover backgrounds.
    """
    return f"""
    QSplitter#mainSplitter::handle,
    QSplitter#analysisCenterSplitter::handle {{
        background-color: {Colors.BACKGROUND_PANEL};
    }}
    QSplitter#mainSplitter::handle:hover,
    QSplitter#analysisCenterSplitter::handle:hover {{
        background-color: {Colors.BORDER_HOVER};
    }}
    QSplitter#mainSplitter::handle:pressed,
    QSplitter#analysisCenterSplitter::handle:pressed {{
        background-color: {Colors.BORDER_FOCUS};
    }}
    QMainWindow::separator {{
        background-color: {Colors.BACKGROUND_PANEL};
        width: 6px;
        height: 6px;
    }}
    QMainWindow::separator:hover {{
        background-color: {Colors.BORDER_HOVER};
    }}
    """


def get_application_stylesheet() -> str:
    """Get complete application stylesheet combining all components."""
    return compose_stylesheet(
        f"""
        /* Main application styling */
        QMainWindow {{
            background-color: {Colors.BACKGROUND_MAIN};
            color: {Colors.TEXT_PRIMARY};
        }}
        """,
        widget_base_style(),
        button_style(),
        action_row_button_style(),
        button_variant_style(),
        group_box_style(),
        input_style(),
        table_style(),
        list_style(),
        tab_widget_style(),
        dock_widget_style(),
        main_splitter_style(),
        label_style(),
        checkbox_style(),
        menu_style(),
    )


ButtonVariant = Literal["primary", "secondary", "danger", "text"]


def apply_button_variant(button: QPushButton, variant: ButtonVariant) -> None:
    """Set a button's color variant and force the style to re-evaluate it.

    Replaces per-widget `setStyleSheet(get_button_styles()[...])` calls; the
    color rules live once in `button_variant_style()` and are selected here via
    the `variant` dynamic property.
    """
    button.setProperty("variant", variant)
    _repolish(button)


def apply_action_row_sizing(*buttons: QPushButton) -> None:
    """Give hand-built peer action buttons the shared action-row footprint.

    `QDialogButtonBox` children already carry the role structurally; use this
    for rows built directly with a box layout so they line up the same way.
    """
    for button in buttons:
        button.setProperty("actionRow", True)
        _repolish(button)


def _repolish(button: QPushButton) -> None:
    """Re-evaluate property selectors after a dynamic property changed."""
    style = button.style()
    style.unpolish(button)
    style.polish(button)


#: Leading glyph shared by every "up one level" navigation link so the gesture
#: reads the same across modes; the non-breaking space keeps it glued to the label.
BACK_ARROW_PREFIX = "← "


def create_styled_menu(parent: QWidget | None = None, title: str = "") -> QMenu:
    """Create a QMenu with proper application theme styling.

    This function ensures consistent styling across all context menus,
    preventing issues where menus inherit incorrect styles from parent widgets
    that have their own setStyleSheet() calls.

    Args:
        parent: Optional parent widget. Recommended to pass the top-level widget
                (e.g., main_window, view) for proper positioning.
        title: Optional menu title displayed at the top.

    Returns:
        QMenu instance with theme styling applied.

    Example:
        menu = create_styled_menu(self.view, "Options")
        menu.addAction("Action 1")
        menu.exec(global_pos)
    """
    menu = QMenu(title, parent) if title else QMenu(parent)
    # 親がある場合、明示的にスタイルを適用してアプリケーションレベルのスタイルを保証
    if parent is not None:
        menu.setStyleSheet(menu_style())
    return menu


def create_dark_palette() -> QPalette:
    """Create a QPalette configured for the application's dark theme.

    Every color role is set explicitly so none falls back to Qt's
    light-theme factory defaults (e.g. navy Link text on a dark background).
    """
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(Colors.BACKGROUND_PANEL))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(Colors.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Base, QColor(Colors.BACKGROUND_WIDGET))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(Colors.BACKGROUND_PANEL))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(Colors.BACKGROUND_PANEL))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(Colors.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Text, QColor(Colors.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(Colors.TEXT_DISABLED))

    button = QColor(Colors.BACKGROUND_WIDGET)
    palette.setColor(QPalette.ColorRole.Button, button)
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(Colors.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Light, button.lighter(150))
    palette.setColor(QPalette.ColorRole.Midlight, button.lighter(125))
    palette.setColor(QPalette.ColorRole.Mid, button.darker(130))
    palette.setColor(QPalette.ColorRole.Dark, button.darker(200))
    palette.setColor(QPalette.ColorRole.Shadow, QColor(Colors.BACKGROUND_MAIN).darker(200))

    palette.setColor(QPalette.ColorRole.BrightText, QColor(Colors.ERROR))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(Colors.PRIMARY))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(Colors.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Accent, QColor(Colors.PRIMARY))
    palette.setColor(QPalette.ColorRole.Link, QColor(Colors.PRIMARY))
    palette.setColor(QPalette.ColorRole.LinkVisited, QColor(Colors.PRIMARY_PRESSED))

    disabled_text = QColor(Colors.TEXT_DISABLED)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled_text)

    return palette


def apply_dark_palette(app: QApplication) -> None:
    """Apply the dark palette to the given QApplication instance."""
    palette = create_dark_palette()
    app.setPalette(palette)


def apply_application_theme(app: QApplication) -> None:
    """Apply the base style, dark palette, and stylesheet to the application."""
    # Native macOS style lays widgets out with Aqua layout-item rects (smaller
    # than the painted rect), which makes QSS-painted widgets overlap; Fusion
    # uses the widget rect and renders identically to offscreen test runs.
    app.setStyle("Fusion")
    apply_dark_palette(app)
    app.setStyleSheet(get_application_stylesheet())
