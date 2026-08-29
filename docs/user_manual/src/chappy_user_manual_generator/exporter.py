"""Utilities to capture annotated UI screenshots and Markdown tables.

The module walks a running PySide6 window, draws numbered callouts, and generates
Markdown tables that correlate those callouts to widget metadata.  It is designed
to keep the docs in `docs/` up to date with the actual UI layout.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol

from PySide6.QtCore import QT_TRANSLATE_NOOP, QPoint, QRect, Qt
from PySide6.QtGui import QAction, QFont, QGuiApplication, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDateTimeEdit,
    QDockWidget,
    QDoubleSpinBox,
    QFrame,
    QGroupBox,
    QLineEdit,
    QListView,
    QListWidget,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QRadioButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStatusBar,
    QTableView,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QTreeView,
    QWidget,
)

from chappy_user_manual_generator.annotations import apply_doc_annotations
from chappy_user_manual_generator.data import section_texts
from chappy_user_manual_generator.data.analysis_structure_operations import (
    render_analysis_structure_operations_table,
)
from chappy_user_manual_generator.data.keyboard_operations import render_keyboard_operations_table
from chappy_user_manual_generator.markdown import MarkdownTableBuilder, format_markdown_text
from chappy_user_manual_generator.panel_windows import (
    IdentifyPanelDocWindow,
    ParameterAdjustmentDocDialog,
    VelocityPlotDocWindow,
)
from chappy_user_manual_generator.template_engine import render_markdown_template
from chappy_user_manual_generator.templates import language_switcher
from chappy_user_manual_generator.translations import translate_manual_text

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Sequence
    from pathlib import Path

# Default scope inference maps
DEFAULT_SCOPE_CLASS_ALIASES: dict[str, str] = {"ModeContextBar": "common", "QStatusBar": "common"}

DEFAULT_SCOPE_OBJECT_ALIASES: dict[str, str] = {
    "modeContextBar": "common",
    "mainStatusBar": "common",
}

CHAPPY_MAIN_WINDOW_CLASS_NAMES: tuple[str, ...] = ("MainWindow",)
DOC_INCLUDE_CLASS_PREFIXES: tuple[str, ...] = ("Chappy",)

_DOC_DEBUG = bool(os.environ.get("CHAPPY_DOC_DEBUG"))
_LOGGER = logging.getLogger(__name__)

_EXPORTER_CONTEXT = "ManualExporter"
_ANNOTATIONS_CONTEXT = "ManualAnnotations"


def _debug(message: str) -> None:
    """Log documentation export debug messages when enabled.

    Args:
        message: Debug message to record.
    """
    if _DOC_DEBUG:
        _LOGGER.debug("[doc-export] %s", message)


def extract_localised_value(value: object, fallback: str = "") -> str:
    """Normalise widget property values that may contain localisation metadata."""
    if isinstance(value, str):
        text = value.strip()
        return text or fallback

    if isinstance(value, dict):
        switcher = language_switcher()
        if switcher is not None:
            lang = switcher.current_language
            if lang in value and isinstance(value[lang], str):
                text = value[lang].strip()
                if text:
                    return text
            base = lang.split("-")[0]
            if base in value and isinstance(value[base], str):
                text = value[base].strip()
                if text:
                    return text
        for candidate_key in ("default", "en", "ja"):
            candidate = value.get(candidate_key)
            if isinstance(candidate, str):
                text = candidate.strip()
                if text:
                    return text
        for candidate in value.values():
            if isinstance(candidate, str):
                text = candidate.strip()
                if text:
                    return text
        return fallback

    return fallback


def resolve_localised_property(widget: QWidget, base_name: str, fallback: str = "") -> str:
    """Resolve custom doc* widget properties with localisation support."""
    direct = extract_localised_value(widget.property(base_name), fallback="")
    if direct:
        return direct

    key_value = widget.property(f"{base_name}Key")
    if isinstance(key_value, str):
        key_value = key_value.strip()
        if key_value:
            return translate_manual_text(_ANNOTATIONS_CONTEXT, key_value)

    return fallback


def lookup_scoped_value(mapping: object, scope: str | None) -> object | None:
    """Return a scope-specific value from ``mapping`` with common fallbacks."""
    if scope is None or not isinstance(mapping, dict):
        return None

    candidates: list[str] = []
    seen: set[str] = set()

    def add_candidate(value: str | None) -> None:
        if not value:
            return
        if value in seen:
            return
        candidates.append(value)
        seen.add(value)

    add_candidate(scope)
    if scope.startswith("mode_"):
        add_candidate(scope.removeprefix("mode_"))

    if "." in scope:
        parts = scope.split(".")
        for end in range(len(parts) - 1, 0, -1):
            add_candidate(".".join(parts[:end]))

    for alias in ("default", "common", "*"):
        add_candidate(alias)

    for candidate in candidates:
        if candidate in mapping:
            return mapping[candidate]
    return None


def resolve_scoped_localised_property(widget: QWidget, base_name: str, scope: str | None) -> str:
    """Resolve properties that vary by scope with localisation support."""
    scoped_values = widget.property(f"{base_name}ByScope")
    value = lookup_scoped_value(scoped_values, scope)
    text = extract_localised_value(value, fallback="")
    if text:
        return text

    scoped_keys = widget.property(f"{base_name}ByScopeKey")
    key_value = lookup_scoped_value(scoped_keys, scope)
    if isinstance(key_value, str):
        key_value = key_value.strip()
        if key_value:
            return translate_manual_text(_ANNOTATIONS_CONTEXT, key_value)
    return ""


def has_mode_specific_metadata(widget: QWidget, scope: str | None) -> bool:
    """Return True if widget exposes scope-specific metadata for the target mode."""
    if not scope:
        return False

    for suffix in ("label", "desc", "role"):
        direct = widget.property(f"doc.{suffix}ByScope")
        if isinstance(direct, dict) and scope in direct:
            return True
        keyed = widget.property(f"doc.{suffix}ByScopeKey")
        if isinstance(keyed, dict) and scope in keyed:
            return True

    include_modes = widget.property("doc.modeScopes")
    if isinstance(include_modes, list | tuple | set):
        return scope in include_modes

    return False


# Collecting widget metadata


@dataclass(slots=True)
class DocItem:
    """Annotation payload for a single widget."""

    widget: QWidget
    rect: QRect
    label: str
    role: str
    description: str
    shortcut: str
    object_name: str
    class_name: str
    path_hint: str = ""
    scope: str | None = None
    index: int = 0
    section: str | None = None


@dataclass(slots=True)
class CustomCaptureSpec:
    """Configuration for an extra screenshot capture."""

    section: str | None = None
    suffix: str = ""
    label_source: str = ""
    position: Literal["before", "after"] = "before"
    pre_capture: Callable[[QMainWindow], None] | None = None
    post_capture: Callable[[QMainWindow], None] | None = None
    post_annotation: Callable[[QMainWindow], None] | None = None


@dataclass(slots=True)
class DocExportConfig:
    """Configuration for a documentation export run."""

    out_dir: Path
    version: str = "unversioned"
    include_tabs: bool = True
    scale_width: int = 1600
    min_rect: int = 12
    allowed_types: tuple[type[QWidget], ...] = (
        QAbstractButton,
        QCheckBox,
        QComboBox,
        QDateEdit,
        QDateTimeEdit,
        QDockWidget,
        QDoubleSpinBox,
        QFrame,
        QGroupBox,
        QLineEdit,
        QListWidget,
        QListView,
        QPlainTextEdit,
        QProgressBar,
        QRadioButton,
        QScrollArea,
        QSlider,
        QSpinBox,
        QTabWidget,
        QTableView,
        QTextEdit,
        QToolButton,
        QTreeView,
        QStatusBar,
    )
    role_aliases: dict[str, str] = field(
        default_factory=lambda: {
            "QAbstractButton": QT_TRANSLATE_NOOP("ManualExporter", "Button"),
            "QPushButton": QT_TRANSLATE_NOOP("ManualExporter", "Button"),
            "QToolButton": QT_TRANSLATE_NOOP("ManualExporter", "Tool button"),
            "QComboBox": QT_TRANSLATE_NOOP("ManualExporter", "Dropdown"),
            "QLineEdit": QT_TRANSLATE_NOOP("ManualExporter", "Text input"),
            "QPlainTextEdit": QT_TRANSLATE_NOOP("ManualExporter", "Text area"),
            "QTextEdit": QT_TRANSLATE_NOOP("ManualExporter", "Rich text"),
            "QSpinBox": QT_TRANSLATE_NOOP("ManualExporter", "Numeric input"),
            "QDoubleSpinBox": QT_TRANSLATE_NOOP("ManualExporter", "Numeric input"),
            "QDateEdit": QT_TRANSLATE_NOOP("ManualExporter", "Date input"),
            "QDateTimeEdit": QT_TRANSLATE_NOOP("ManualExporter", "Date/time input"),
            "QCheckBox": QT_TRANSLATE_NOOP("ManualExporter", "Checkbox"),
            "QRadioButton": QT_TRANSLATE_NOOP("ManualExporter", "Radio button"),
            "QScrollArea": QT_TRANSLATE_NOOP("ManualExporter", "Scroll area"),
            "QTreeView": QT_TRANSLATE_NOOP("ManualExporter", "Tree view"),
            "QTableView": QT_TRANSLATE_NOOP("ManualExporter", "Table view"),
            "QListView": QT_TRANSLATE_NOOP("ManualExporter", "List view"),
            "QListWidget": QT_TRANSLATE_NOOP("ManualExporter", "List view"),
            "QGroupBox": QT_TRANSLATE_NOOP("ManualExporter", "Group"),
            "QTabWidget": QT_TRANSLATE_NOOP("ManualExporter", "Tab"),
            "QProgressBar": QT_TRANSLATE_NOOP("ManualExporter", "Progress bar"),
            "QStatusBar": QT_TRANSLATE_NOOP("ManualExporter", "Status bar"),
        }
    )
    include_scopes: set[str] | None = None
    include_unscoped: bool = True
    exclude_scopes: set[str] = field(default_factory=set)
    show_internal_widget_name: bool = False
    custom_captures: list[CustomCaptureSpec] = field(default_factory=list)
    write_markdown: bool = True


@dataclass(slots=True)
class DocExportResult:
    """Result information for a captured window."""

    markdown_path: Path
    image_paths: list[Path]
    items: list[DocItem]
    layout_blocks: list[str]


class WindowProvider(Protocol):
    """Protocol for objects that produce fully constructed windows."""

    def create_window(self, app: QApplication) -> QMainWindow:  # pragma: no cover - protocol
        """Build and return the window that should be documented.

        Args:
            app: Running Qt application used to parent the created window.

        Returns:
            Window instance ready for capture and annotation.
        """
        ...


def export_window_docs(window: QMainWindow, config: DocExportConfig) -> DocExportResult:
    """Capture screenshots and a Markdown table for a target window."""
    ensure_high_dpi_mode()
    config.out_dir.mkdir(parents=True, exist_ok=True)
    image_dir = config.out_dir / "images"
    image_dir.mkdir(exist_ok=True)

    layout_blocks: list[str] = []
    screenshots: list[Path] = []
    all_items: list[DocItem] = []
    seen_signatures: set[tuple[tuple[str, str, str, str, str], ...]] = set()
    is_common_scope = config.include_scopes == {"common"}
    page_scope: str | None = None
    if config.include_scopes and len(config.include_scopes) == 1:
        page_scope = next(iter(config.include_scopes))
    _debug(f"export_window_docs start include_scopes={config.include_scopes}")

    base_title = window.windowTitle() or type(window).__name__
    title_key = window.property("doc.windowTitleKey")
    if isinstance(title_key, str) and title_key:
        title = translate_manual_text(_ANNOTATIONS_CONTEXT, title_key)
    else:
        title_override = window.property("doc.windowTitle")
        title = (
            title_override if isinstance(title_override, str) and title_override else base_title
        )
    summary_text = resolve_doc_summary(window, page_scope)
    summary_text = summary_text.strip()
    if not summary_text:
        summary_text = translate_manual_text(
            _EXPORTER_CONTEXT, QT_TRANSLATE_NOOP("ManualExporter", "Content coming soon.")
        )
    internal_identifier_block = ""
    if config.show_internal_widget_name:
        internal_identifier_block = "\n\n" + translate_manual_text(
            _EXPORTER_CONTEXT,
            #: {identifier} は実行時に置換されるため書き換えないこと。
            QT_TRANSLATE_NOOP("ManualExporter", "Internal identifier: {identifier}"),
        ).format(identifier=type(window).__name__)

    def append_layout_block(image_path: Path, items: list[DocItem], label: str | None) -> None:
        """Append a layout block, optionally suppressing tables for specific scopes."""
        relative_image = image_path.relative_to(config.out_dir)
        table_markdown = ""
        if page_scope != "start":
            table_markdown = build_markdown_table(items)
        layout_blocks.append(render_layout_block(label, relative_image, table_markdown))

    def capture_one(
        suffix: str = "", *, section: str | None = None
    ) -> tuple[Path, list[DocItem]] | None:
        items = sorted_items(window, config)
        if section is not None:
            items = [item for item in items if item.section == section]
        if not items:
            return None

        # Key on each item's own section so an unfiltered capture that yields
        # exactly the same widgets as an earlier section-filtered capture is
        # recognised as a duplicate and skipped.
        signature = tuple(
            (
                item.section or "",
                item.object_name,
                item.label,
                item.class_name,
                item.role,
                item.description,
            )
            for item in items
        )
        if config.include_scopes is not None:
            if signature in seen_signatures:
                return None
            seen_signatures.add(signature)

        for idx, item in enumerate(items, start=1):
            item.index = idx

        final_suffix = suffix
        if is_common_scope and not final_suffix:
            final_suffix = "_common"
        image_path = image_dir / f"{type(window).__name__}{final_suffix}_annotated.png"
        draw_annotations(window, items, image_path, scale_width=config.scale_width)
        return image_path, items

    def section_label(tab_text: str | None = None, tab_index: int | None = None) -> str | None:
        if is_common_scope:
            return translate_manual_text(
                _EXPORTER_CONTEXT, QT_TRANSLATE_NOOP("ManualExporter", "Common UI")
            )
        if tab_text:
            return tab_text
        if tab_index is not None:
            return translate_manual_text(
                _EXPORTER_CONTEXT,
                #: {index} は実行時に置換されるため書き換えないこと。
                QT_TRANSLATE_NOOP("ManualExporter", "Tab {index}"),
            ).format(index=str(tab_index + 1))
        return None

    def execute_custom_capture(spec: CustomCaptureSpec) -> None:
        if spec.pre_capture:
            spec.pre_capture(window)
            app = QApplication.instance()
            if app is not None:
                app.processEvents()
        apply_doc_annotations(window)
        if spec.post_annotation:
            spec.post_annotation(window)

        result = capture_one(spec.suffix, section=spec.section)
        if result is not None:
            image_path, items = result
            screenshots.append(image_path)
            all_items.extend(items)
            label: str | None = None
            if spec.label_source:
                label = translate_manual_text(_EXPORTER_CONTEXT, spec.label_source)
            append_layout_block(image_path, items, label)

        if spec.post_capture:
            spec.post_capture(window)
            app = QApplication.instance()
            if app is not None:
                app.processEvents()

    before_captures = [spec for spec in config.custom_captures if spec.position == "before"]
    after_captures = [spec for spec in config.custom_captures if spec.position == "after"]

    for spec in before_captures:
        execute_custom_capture(spec)

    if config.include_tabs:
        captured = False
        for tab_widget in window.findChildren(QTabWidget):
            _debug(f"processing tab widget {tab_widget.objectName()} count={tab_widget.count()}")
            tab_scope = infer_scope(tab_widget)
            if (
                config.include_scopes is not None
                and tab_scope not in config.include_scopes
                and not (tab_scope is None and config.include_unscoped)
            ):
                continue
            if config.exclude_scopes and tab_scope in config.exclude_scopes:
                continue
            original = tab_widget.currentIndex()
            tab_sections = tab_widget.property("doc.tabSections")
            for tab_index in range(tab_widget.count()):
                _debug(f" capture tab index={tab_index}")
                tab_widget.setCurrentIndex(tab_index)
                tab_text = tab_widget.tabText(tab_index)
                if is_common_scope:
                    suffix = "_common"
                else:
                    suffix = f"_tab{tab_index + 1}"
                    if tab_text:
                        suffix += f"_{tab_text}"
                section_value: str | None = None
                if isinstance(tab_sections, dict):
                    index_key = str(tab_index)
                    if index_key in tab_sections:
                        section_value = str(tab_sections[index_key])
                    elif tab_text and tab_text in tab_sections:
                        section_value = str(tab_sections[tab_text])
                result = capture_one(suffix, section=section_value)
                if result is None and section_value is not None:
                    result = capture_one(suffix)
                if result is None:
                    continue
                image_path, items = result
                screenshots.append(image_path)
                all_items.extend(items)
                label = section_label(tab_text, tab_index)
                append_layout_block(image_path, items, label)
                captured = True
            tab_widget.setCurrentIndex(original)
        if not captured:
            default_suffix = "_common" if is_common_scope else ""
            result = capture_one(default_suffix)
            if result is not None:
                image_path, items = result
                screenshots.append(image_path)
                all_items.extend(items)
                label = section_label()
                append_layout_block(image_path, items, label)
    else:
        default_suffix = "_common" if is_common_scope else ""
        result = capture_one(default_suffix)
        if result is not None:
            image_path, items = result
            screenshots.append(image_path)
            all_items.extend(items)
            label = section_label()
            append_layout_block(image_path, items, label)

    for spec in after_captures:
        execute_custom_capture(spec)

    markdown_path = config.out_dir / f"{type(window).__name__}.md"
    layout_heading = translate_manual_text(
        _EXPORTER_CONTEXT, QT_TRANSLATE_NOOP("ManualExporter", "Screen Overview")
    )
    if layout_blocks:
        layout_blocks_text = "\n\n".join(layout_blocks)
    else:
        placeholder = translate_manual_text(
            _EXPORTER_CONTEXT, QT_TRANSLATE_NOOP("ManualExporter", "Content coming soon.")
        )
        layout_blocks_text = placeholder

    operations_section, notes_section = build_usage_sections(window, page_scope)
    additional_section_blocks = additional_sections(window, config)
    additional_sections_text = ""
    if additional_section_blocks:
        prefix = "\n\n"
        additional_sections_text = prefix + "\n\n".join(additional_section_blocks)

    page_text = render_markdown_template(
        "dialog_page.md.tmpl",
        title=title,
        internal_identifier_block=internal_identifier_block,
        summary_text=summary_text,
        layout_heading=layout_heading,
        layout_blocks=layout_blocks_text,
        operations_section=operations_section,
        notes_section=notes_section,
        additional_sections=additional_sections_text,
    )
    formatted_page = format_markdown_text(page_text)
    if config.write_markdown:
        if not formatted_page.endswith("\n"):
            formatted_page += "\n"
        markdown_path.write_text(formatted_page, encoding="utf-8")
    return DocExportResult(
        markdown_path=markdown_path,
        image_paths=screenshots,
        items=all_items,
        layout_blocks=layout_blocks,
    )


# High level helpers


def ensure_high_dpi_mode() -> None:
    """Enable high DPI behaviour once per process."""
    app = QGuiApplication.instance()
    if app is None:
        return
    app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)


def sorted_items(window: QMainWindow, config: DocExportConfig) -> list[DocItem]:
    """Collect documentation items and sort in reading order."""
    raw_items = list(gather_items(window, config))
    items = [item for item in raw_items if scope_matches(item, config)]
    for item in items:
        order_prop = item.widget.property("doc.order")
        order = int(order_prop) if isinstance(order_prop, int) else 1_000_000
        widget_pos = (item.rect.y() // 16, item.rect.x())
        item.widget.setProperty("_doc_sort_key", (order, *widget_pos))
    items.sort(key=lambda it: it.widget.property("_doc_sort_key"))
    return items


def gather_items(window: QMainWindow, config: DocExportConfig) -> Iterator[DocItem]:
    """Yield documentation records for eligible widgets."""
    buddy_map = build_buddy_map(window)
    default_scope: str | None = None
    if config.include_scopes and len(config.include_scopes) == 1 and config.include_unscoped:
        default_scope = next(iter(config.include_scopes))

    for widget in window.findChildren(QWidget):
        if _DOC_DEBUG and widget.objectName():
            _debug(f" gather widget={widget.objectName()} class={widget.metaObject().className()}")
        if not should_include(widget, config.allowed_types):
            continue
        parent_widget = widget.parentWidget()
        if parent_widget is not None and isinstance(parent_widget, QAbstractSpinBox):
            continue
        rect = window_relative_rect(widget, window, config.min_rect)
        if rect is None:
            continue
        inferred_scope = infer_scope(widget)
        scope = inferred_scope or default_scope
        effective_scope = scope
        if inferred_scope == "common" and default_scope is not None:
            if has_mode_specific_metadata(widget, default_scope):
                effective_scope = default_scope
            else:
                effective_scope = inferred_scope
        label = resolve_label(widget, buddy_map, effective_scope)
        action = default_action(widget)
        description = resolve_description(widget, action, effective_scope)
        shortcut = resolve_shortcut(action)
        path_hint = resolve_path_hint(widget)
        class_name = widget.metaObject().className()
        role_source = config.role_aliases.get(class_name)
        role = (
            translate_manual_text(_EXPORTER_CONTEXT, role_source)
            if role_source is not None
            else class_name
        )
        section = resolve_section(widget, effective_scope)

        if not include_structural_item(widget, label, description, role):
            continue

        yield DocItem(
            widget=widget,
            rect=rect,
            label=label,
            role=role,
            description=description,
            shortcut=shortcut,
            object_name=widget.objectName() or "",
            class_name=class_name,
            path_hint=path_hint,
            scope=effective_scope,
            section=section,
        )


def scope_matches(item: DocItem, config: DocExportConfig) -> bool:
    """Return True when an item should be included based on scope filters."""
    if config.exclude_scopes and item.scope in config.exclude_scopes:
        return False
    if config.include_scopes is not None:
        if item.scope in config.include_scopes:
            return True
        if item.scope is None and config.include_unscoped:
            return True
        return bool(item.scope == "common" and config.include_unscoped)
    return True


def build_buddy_map(window: QMainWindow) -> dict[QWidget, str]:
    """Return mapping from input widgets to label text."""
    mapping: dict[QWidget, str] = {}
    for label in window.findChildren(QWidget):
        if not hasattr(label, "buddy"):
            continue
        try:
            buddy = label.buddy()
        except (AttributeError, RuntimeError):  # pragma: no cover - Qt binding specifics
            buddy = None
        if buddy is None:
            continue
        text = getattr(label, "text", lambda: "")()
        if text:
            mapping[buddy] = text.replace("&", "")
    return mapping


def resolve_section(widget: QWidget, scope: str | None) -> str | None:
    """Resolve the documentation section identifier for a widget."""
    direct = widget.property("doc.section")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    scoped = widget.property("doc.sectionByScope")
    value = lookup_scoped_value(scoped, scope)
    if isinstance(value, str) and value.strip():
        return value.strip()

    key_value = widget.property("doc.sectionKey")
    if isinstance(key_value, str) and key_value.strip():
        return key_value.strip()
    return None


def should_include(widget: QWidget, allowed_types: Sequence[type[QWidget]]) -> bool:
    """Check if a widget should be documented."""
    include_prop = widget.property("doc.include")
    if isinstance(include_prop, bool):
        return include_prop

    if any(isinstance(widget, allowed) for allowed in allowed_types):
        return True

    # Allow project specific widgets via marker property
    if widget.property("doc.include") is not None:
        return bool(widget.property("doc.include"))

    class_name = widget.metaObject().className()
    return any(class_name.startswith(prefix) for prefix in DOC_INCLUDE_CLASS_PREFIXES)


def window_relative_rect(widget: QWidget, window: QMainWindow, min_rect: int) -> QRect | None:
    """Return a widget rectangle in window coordinates."""
    target_widget: QWidget = widget
    rect_target_prop = widget.property("doc.rectTarget")
    if isinstance(rect_target_prop, str):
        rect_target = rect_target_prop.strip()
        if rect_target:
            if rect_target == "tabBar" and isinstance(widget, QTabWidget):
                tab_bar = widget.tabBar()
                if tab_bar is not None:
                    target_widget = tab_bar
            elif rect_target.startswith("child:"):
                child_name = rect_target.split(":", 1)[1].strip()
                if child_name:
                    child_widget = widget.findChild(QWidget, child_name)
                    if child_widget is not None:
                        target_widget = child_widget

    if not target_widget.isVisible():
        return None

    ancestor = target_widget
    while ancestor is not None and ancestor is not window:
        ancestor = ancestor.parentWidget()
    if ancestor is None:
        return None

    local_rect = target_widget.rect()
    top_left = target_widget.mapTo(window, QPoint(0, 0))
    mapped = QRect(top_left, local_rect.size())
    if mapped.width() < min_rect or mapped.height() < min_rect:
        return None
    return mapped


def resolve_label(widget: QWidget, buddies: dict[QWidget, str], scope: str | None = None) -> str:
    """Resolve a human readable label for a widget."""
    scoped_label = resolve_scoped_localised_property(widget, "doc.label", scope)
    if scoped_label:
        return scoped_label

    doc_label = resolve_localised_property(widget, "doc.label", fallback="")
    if doc_label:
        return doc_label

    if widget in buddies:
        return buddies[widget]

    if hasattr(widget, "text"):
        try:
            text = widget.text()
            if text:
                return text.replace("&", "")
        except (AttributeError, RuntimeError):  # pragma: no cover - Qt binding specifics
            pass

    if hasattr(widget, "placeholderText"):
        try:
            placeholder = widget.placeholderText()
            if placeholder:
                return placeholder
        except (AttributeError, RuntimeError):  # pragma: no cover - Qt binding specifics
            pass

    accessible = widget.accessibleName()
    if accessible:
        return accessible

    return widget.objectName() or widget.metaObject().className()


def default_action(widget: QWidget) -> QAction | None:
    """Return default action for tool buttons."""
    if isinstance(widget, QToolButton):
        try:
            return widget.defaultAction()
        except (AttributeError, RuntimeError):  # pragma: no cover - Qt binding specifics
            return None
    return None


def resolve_description(widget: QWidget, action: QAction | None, scope: str | None) -> str:
    """Choose the best available description for a widget."""
    scoped_desc = resolve_scoped_localised_property(widget, "doc.desc", scope)
    if scoped_desc:
        return scoped_desc

    doc_desc = resolve_localised_property(widget, "doc.desc", fallback="")
    if doc_desc:
        return doc_desc

    def clean(value: str | None) -> str:
        return (value or "").strip()

    for source in (
        getattr(widget, "whatsThis", lambda: "")(),
        getattr(widget, "toolTip", lambda: "")(),
        getattr(widget, "statusTip", lambda: "")(),
    ):
        text = clean(source)
        if text:
            return text

    if action is not None:
        for source in (action.whatsThis(), action.toolTip(), action.statusTip()):
            text = clean(source)
            if text:
                return text

    return ""


def resolve_shortcut(action: QAction | None) -> str:
    """Return the shortcut string for a QAction."""
    if action is None:
        return ""
    shortcut = action.shortcut()
    if shortcut is not None and not shortcut.isEmpty():
        return shortcut.toString()
    return ""


def include_structural_item(widget: QWidget, label: str, description: str, role: str) -> bool:
    """Filter out structural widgets lacking user-facing metadata."""
    if widget.property("doc.include") is True:
        return True

    class_name = widget.metaObject().className()
    if class_name in {"QFrame", "QSplitter"}:
        return False

    normalized_label = label.strip()
    normalized_desc = description.strip()
    if not normalized_desc:
        return False
    empty_label_candidates = {role, class_name, widget.objectName() or ""}
    fallback_descriptions = {""}

    return not (
        normalized_label in empty_label_candidates and normalized_desc in fallback_descriptions
    )


def additional_sections(window: QMainWindow, config: DocExportConfig) -> list[str]:
    """Append window-specific documentation sections."""
    sections: list[str] = []
    class_name = window.__class__.__name__
    scopes = {scope.lower() for scope in (config.include_scopes or set())}

    if class_name == "AnalysisStructureDocWindow":
        sections.append(render_analysis_structure_operations_table())
        return sections

    if class_name in CHAPPY_MAIN_WINDOW_CLASS_NAMES and "analysis_structure" in scopes:
        section_heading = translate_manual_text(
            _EXPORTER_CONTEXT, section_texts.ANALYSIS_STRUCTURE_HEADING
        ).strip()
        section_intro = translate_manual_text(
            _EXPORTER_CONTEXT, section_texts.ANALYSIS_STRUCTURE_INTRO
        ).strip()
        operations_block = render_analysis_structure_operations_table()

        block_lines = [f"## {section_heading}"]
        if section_intro:
            block_lines.extend(["", section_intro])
        block_lines.extend(["", operations_block])
        sections.append("\n".join(block_lines))

    if class_name in CHAPPY_MAIN_WINDOW_CLASS_NAMES and "identify" in scopes:
        sections.extend(_render_identify_side_panel_sections(config))

    if class_name in CHAPPY_MAIN_WINDOW_CLASS_NAMES and "analysis_region_detail" in scopes:
        sections.extend(_render_analysis_detail_velocity_plot_section(config))
        sections.extend(_render_parameter_adjustment_dialog_section(config))

    if class_name == "PresetListDialog":
        heading = translate_manual_text(
            _EXPORTER_CONTEXT, QT_TRANSLATE_NOOP("ManualExporter", "Related Dialogs")
        )
        link_label = translate_manual_text(
            _EXPORTER_CONTEXT,
            QT_TRANSLATE_NOOP("ManualExporter", "Absorption-line Database Search"),
        )
        lines = [f"## {heading}", "", f"- [{link_label}](LineSelectionDialog.md)"]
        sections.append("\n".join(lines))

    # Add keyboard/mouse operations section for main window
    if class_name in CHAPPY_MAIN_WINDOW_CLASS_NAMES:
        for scope in scopes:
            keyboard_section = render_keyboard_operations_table(scope)
            if keyboard_section:
                sections.append(keyboard_section)

    return sections


def _render_identify_side_panel_sections(config: DocExportConfig) -> list[str]:
    app = QApplication.instance()
    if app is None:
        return []

    panel_window = IdentifyPanelDocWindow()
    panel_window.show()
    apply_doc_annotations(panel_window)
    app.processEvents()

    panel_dir = config.out_dir / "identify_side_panel"
    panel_config = DocExportConfig(
        out_dir=panel_dir,
        version=config.version,
        include_tabs=True,
        scale_width=min(config.scale_width, 900),
        include_scopes={"identify_panel"},
        include_unscoped=True,
        exclude_scopes={"common"},
        show_internal_widget_name=False,
        write_markdown=False,
    )
    result = export_window_docs(panel_window, panel_config)

    panel_window.close()
    app.processEvents()

    heading = translate_manual_text(
        _EXPORTER_CONTEXT, QT_TRANSLATE_NOOP("ManualExporter", "Side Panel Details")
    )
    intro = translate_manual_text(
        _EXPORTER_CONTEXT,
        QT_TRANSLATE_NOOP(
            "ManualExporter",
            "Review the side panel widgets in workflow order: the preset setup header,"
            " detection candidates, temporary lines with registration, and confirmed"
            " regions.",
        ),
    ).strip()

    lines: list[str] = [f"## {heading}"]
    if intro:
        lines.extend(["", intro])
    relative_prefix = panel_dir.relative_to(config.out_dir).as_posix()
    image_prefix = f"{relative_prefix}/images/" if relative_prefix else "images/"

    for block in result.layout_blocks:
        adjusted_block = block.replace("](images/", f"]({image_prefix}")
        lines.extend(["", adjusted_block])

    return ["\n".join(lines)]


def _render_parameter_adjustment_dialog_section(config: DocExportConfig) -> list[str]:
    """Render documentation section for the parameter adjustment dialog."""
    app = QApplication.instance()
    if app is None:
        return []

    dialog = ParameterAdjustmentDocDialog()
    dialog.show()
    apply_doc_annotations(dialog)
    app.processEvents()

    dialog_dir = config.out_dir / "parameter_dialog"
    dialog_config = DocExportConfig(
        out_dir=dialog_dir,
        version=config.version,
        include_tabs=False,
        scale_width=min(config.scale_width, 600),
        include_scopes={"optimize_dialog"},
        include_unscoped=True,
        exclude_scopes={"common"},
        show_internal_widget_name=False,
        write_markdown=False,
    )
    result = export_window_docs(dialog, dialog_config)

    dialog.close()
    app.processEvents()

    heading = translate_manual_text(_EXPORTER_CONTEXT, section_texts.PARAMETER_DIALOG_HEADING)
    intro = translate_manual_text(_EXPORTER_CONTEXT, section_texts.PARAMETER_DIALOG_INTRO).strip()

    lines: list[str] = [f"## {heading}"]
    if intro:
        lines.extend(["", intro])
    relative_prefix = dialog_dir.relative_to(config.out_dir).as_posix()
    image_prefix = f"{relative_prefix}/images/" if relative_prefix else "images/"

    for block in result.layout_blocks:
        adjusted_block = block.replace("](images/", f"]({image_prefix}")
        lines.extend(["", adjusted_block])

    return ["\n".join(lines)]


def _render_analysis_detail_velocity_plot_section(config: DocExportConfig) -> list[str]:
    """Render the Analysis Region Detail velocity-plot section."""
    app = QApplication.instance()
    if app is None:
        return []

    window = VelocityPlotDocWindow()
    window.show()
    apply_doc_annotations(window)
    # The dedicated preview documents the overlay's controls and representative
    # subplot, so a full-surface callout would only obscure those annotations.
    window.velocity_overlay.setProperty("doc.include", False)
    app.processEvents()

    velocity_dir = config.out_dir / "velocity_plot"
    velocity_config = DocExportConfig(
        out_dir=velocity_dir,
        version=config.version,
        include_tabs=False,
        scale_width=min(config.scale_width, 1000),
        include_scopes={"optimize_velocity"},
        include_unscoped=True,
        exclude_scopes={"common"},
        show_internal_widget_name=False,
        write_markdown=False,
    )
    result = export_window_docs(window, velocity_config)

    window.close()
    app.processEvents()

    heading = translate_manual_text(_EXPORTER_CONTEXT, section_texts.VELOCITY_PLOT_HEADING)
    intro = translate_manual_text(_EXPORTER_CONTEXT, section_texts.VELOCITY_PLOT_INTRO).strip()
    op_heading = translate_manual_text(
        _EXPORTER_CONTEXT, section_texts.VELOCITY_PLOT_OPERATIONS_HEADING
    )

    lines: list[str] = [f"## {heading}"]
    if intro:
        lines.extend(["", intro])

    # Add annotated screenshot and table from export result
    relative_prefix = velocity_dir.relative_to(config.out_dir).as_posix()
    image_prefix = f"{relative_prefix}/images/" if relative_prefix else "images/"

    for block in result.layout_blocks:
        adjusted_block = block.replace("](images/", f"]({image_prefix}")
        lines.extend(["", adjusted_block])

    operations = [
        translate_manual_text(_EXPORTER_CONTEXT, source)
        for source in section_texts.VELOCITY_PLOT_OPERATION_SOURCES
    ]
    filtered_ops = [op for op in operations if op]

    if filtered_ops:
        lines.append("")
        lines.append(f"### {op_heading}")
        lines.append("")
        lines.extend(f"- {op}" for op in filtered_ops)

    return ["\n".join(lines)]


def resolve_doc_summary(window: QMainWindow, scope: str | None) -> str:
    """Return summary text shown at the top of documentation pages."""
    summary = resolve_scoped_localised_property(window, "doc.summary", scope)
    if not summary:
        summary = resolve_localised_property(window, "doc.summary", fallback="")
    return summary.strip()


def build_usage_sections(window: QMainWindow, scope: str | None) -> tuple[str, str]:
    """Return rendered sections for primary operations and cautions."""
    operations = resolve_doc_sequence(window, "doc.operations", scope)
    notes = resolve_doc_sequence(window, "doc.notes", scope)

    operations_section = ""
    if operations:
        heading = resolve_scoped_localised_property(window, "doc.operationsHeading", scope)
        if not heading:
            heading = resolve_localised_property(window, "doc.operationsHeading", fallback="")
        heading = heading.strip()
        if not heading:
            heading = translate_manual_text(
                _EXPORTER_CONTEXT, QT_TRANSLATE_NOOP("ManualExporter", "Key Operations")
            )
        if heading:
            rendered = render_bullet_section(heading, operations)
            operations_section = "\n\n" + rendered

    notes_section = ""
    if notes:
        heading = resolve_scoped_localised_property(window, "doc.notesHeading", scope)
        if not heading:
            heading = resolve_localised_property(window, "doc.notesHeading", fallback="")
        heading = heading.strip()
        if not heading:
            heading = translate_manual_text(
                _EXPORTER_CONTEXT, QT_TRANSLATE_NOOP("ManualExporter", "Notes & Caveats")
            )
        if heading:
            prefix = "\n\n"
            rendered = render_bullet_section(heading, notes)
            notes_section = prefix + rendered

    return operations_section, notes_section


def resolve_doc_sequence(window: QMainWindow, base_name: str, scope: str | None) -> list[str]:
    """Convert doc annotations into a sequence of lines."""
    entries: list[str] = []

    scoped_values = lookup_scoped_value(window.property(f"{base_name}ByScope"), scope)
    entries.extend(_coerce_doc_sequence(scoped_values))

    if not entries:
        scoped_keys = lookup_scoped_value(window.property(f"{base_name}ByScopeKey"), scope)
        entries.extend(_coerce_doc_sequence(scoped_keys))

    if not entries:
        entries.extend(_coerce_doc_sequence(window.property(base_name)))

    if not entries:
        entries.extend(_coerce_doc_sequence(window.property(f"{base_name}Key")))

    return entries


def _coerce_doc_sequence(value: object) -> list[str]:
    """Normalise doc annotation payloads into plain strings."""
    if value is None:
        return []

    if isinstance(value, list | tuple):
        lines: list[str] = []
        for entry in value:
            lines.extend(_coerce_doc_sequence(entry))
        return lines

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        translated = translate_manual_text(_ANNOTATIONS_CONTEXT, stripped)
        return [line.strip() for line in translated.splitlines() if line.strip()]

    if isinstance(value, dict):
        text = extract_localised_value(value, fallback="")
        return _coerce_doc_sequence(text)

    return []


def resolve_path_hint(widget: QWidget) -> str:
    """Build a menu path hint for widgets hosted in menus or toolbars."""
    parents: list[str] = []
    parent = widget.parentWidget()
    depth = 0
    while parent is not None and depth < 4:
        if parent.objectName():
            parents.append(parent.objectName())
        parent = parent.parentWidget()
        depth += 1
    if parents:
        return " / ".join(reversed(parents))
    return ""


def infer_scope(widget: QWidget) -> str | None:
    """Infer scope for a widget based on explicit properties or ancestors."""
    current: QWidget | None = widget
    depth = 0
    while current is not None and depth < 8:
        scope_prop = current.property("doc.scope")
        if isinstance(scope_prop, str) and scope_prop.strip():
            return scope_prop.strip()

        object_name = current.objectName()
        if object_name and object_name in DEFAULT_SCOPE_OBJECT_ALIASES:
            return DEFAULT_SCOPE_OBJECT_ALIASES[object_name]

        class_name = current.metaObject().className()
        if class_name in DEFAULT_SCOPE_CLASS_ALIASES:
            return DEFAULT_SCOPE_CLASS_ALIASES[class_name]

        current = current.parentWidget()
        depth += 1
    return None


# Rendering helpers


def draw_annotations(
    window: QMainWindow, items: Iterable[DocItem], out_path: Path, *, scale_width: int
) -> None:
    """Draw annotated rectangles and badges."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    original = window.grab()
    scaled = scale_pixmap(original, width=scale_width)
    sx = scaled.width() / max(1, window.width())
    sy = scaled.height() / max(1, window.height())

    painter = QPainter(scaled)
    pen = QPen(Qt.red)
    pen.setWidth(3)
    painter.setPen(pen)

    font = QFont()
    font.setBold(True)
    font.setPointSize(10)
    painter.setFont(font)

    for item in items:
        rect = item.rect
        scaled_rect = QRect(
            int(rect.x() * sx), int(rect.y() * sy), int(rect.width() * sx), int(rect.height() * sy)
        )
        painter.drawRect(scaled_rect)
        badge = _annotation_badge_rect(item, scaled_rect)
        painter.fillRect(badge, Qt.black)
        painter.setPen(Qt.white)
        painter.drawText(badge.adjusted(6, 3, 0, 0), Qt.AlignLeft, str(item.index))
        painter.setPen(pen)

    painter.end()
    scaled.save(str(out_path))


def _annotation_badge_rect(item: DocItem, scaled_rect: QRect) -> QRect:
    """Return the badge rectangle without obscuring its annotated content."""
    badge = QRect(scaled_rect.topLeft(), scaled_rect.topLeft() + QPoint(24, 20))
    if (
        item.widget.property("doc.badgePosition") == "outside-left"
        and badge.width() <= scaled_rect.x()
    ):
        badge.moveRight(scaled_rect.left() - 1)
    return badge


def scale_pixmap(pixmap: QPixmap, width: int) -> QPixmap:
    """Scale a pixmap keeping aspect ratio."""
    if width <= 0 or pixmap.width() <= width:
        return pixmap
    height = int(pixmap.height() * (width / pixmap.width()))
    return pixmap.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def build_markdown_table(items: Iterable[DocItem]) -> str:
    """Return a Markdown table for the provided items."""
    shortcut_tail_pattern = re.compile(
        r"(?:\s*(?:\(|（)([^()（）]*?(?:Ctrl|Alt|Shift|Command|Cmd|Option|Meta|⌘|⌥)"
        r"[^()（）]*?)(?:\)|）))\s*$"
    )

    builder = MarkdownTableBuilder(
        [
            translate_manual_text(_EXPORTER_CONTEXT, QT_TRANSLATE_NOOP("ManualExporter", "No.")),
            translate_manual_text(_EXPORTER_CONTEXT, QT_TRANSLATE_NOOP("ManualExporter", "Item")),
            translate_manual_text(
                _EXPORTER_CONTEXT, QT_TRANSLATE_NOOP("ManualExporter", "Description")
            ),
            translate_manual_text(
                _EXPORTER_CONTEXT, QT_TRANSLATE_NOOP("ManualExporter", "Shortcut")
            ),
        ],
        alignments=("right", "left", "left", "left"),
    )
    for item in items:
        label = item.label.replace("\n", " ").strip()
        desc = item.description.replace("\n", "<br> ").strip()
        shortcut = item.shortcut or ""
        item_label = label or item.role
        item_desc = desc or item.role

        if item_desc:
            match = shortcut_tail_pattern.search(item_desc)
            if match:
                candidate = match.group(1).strip()
                if not shortcut or shortcut == candidate:
                    shortcut = shortcut or candidate
                    item_desc = item_desc[: match.start()].rstrip(" ・:：")

        index_value = "" if item.index is None else str(item.index)
        builder.add_row([index_value, item_label, item_desc, shortcut])
    return builder.as_text()


def render_layout_block(label: str | None, image_path: Path, table_markdown: str) -> str:
    """Render a layout block using the Markdown template."""
    heading_block = ""
    if label:
        heading_block = render_markdown_template("layout_heading.md.tmpl", heading=label) + "\n"
    rendered = render_markdown_template(
        "layout_block.md.tmpl",
        heading_block=heading_block,
        image_path=image_path.as_posix(),
        table_markdown=table_markdown,
    )
    return rendered.strip()


def render_bullet_section(heading: str, items: Sequence[str]) -> str:
    """Render a bullet list section when items are available."""
    if not items:
        return ""
    bullet_lines = [
        render_markdown_template("bullet_item.md.tmpl", text=item).strip() for item in items
    ]
    items_block = "\n".join(bullet_lines)
    rendered = render_markdown_template(
        "bullet_section.md.tmpl", heading=heading, items_block=items_block
    )
    return rendered.strip()


# Convenience utilities


def run_with_window(provider: WindowProvider, config: DocExportConfig) -> DocExportResult:
    """Create a QApplication if necessary and run an export."""
    ensure_high_dpi_mode()
    app_created = False
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
        app_created = True

    window = provider.create_window(app)
    window.show()
    result = export_window_docs(window, config)

    if app_created:
        app.quit()
    return result
