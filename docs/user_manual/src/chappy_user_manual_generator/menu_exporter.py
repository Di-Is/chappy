"""Utilities for exporting menu documentation tables."""

from __future__ import annotations

import contextlib
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from PySide6.QtCore import QT_TRANSLATE_NOOP, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QApplication, QMainWindow, QMenu

from chappy.gui.shell.shortcuts import get_shortcut_display
from chappy_user_manual_generator.annotations import apply_doc_annotations
from chappy_user_manual_generator.exporter import DocExportConfig, export_window_docs, scale_pixmap
from chappy_user_manual_generator.markdown import MarkdownTableBuilder, format_markdown_text
from chappy_user_manual_generator.templates import mode_label_map
from chappy_user_manual_generator.translations import translate_manual_text

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from chappy_user_manual_generator.dialog_providers import DialogProvider
    from chappy_user_manual_generator.models import MenuDocSpec


@dataclass(slots=True)
class MenuDocConfig:
    """Configuration options for menu documentation exports."""

    out_dir: Path
    version: str = "unversioned"
    # Table options
    include_shortcuts: bool = True
    include_modes: bool = True
    include_status: bool = True
    include_notes: bool = True
    mode_labels: dict[str, str] = field(default_factory=mode_label_map)
    # Overview/individual pages
    overview_filename: str | None = "index.md"
    write_individual_pages: bool = True
    shortcuts_filename: str | None = "shortcuts.md"
    # Visual options
    include_screenshot: bool = True
    screenshot_scale_width: int = 800
    # Dialog documentation options
    dialog_output_subdir: str = "dialogs"
    dialog_providers: dict[str, tuple[DialogProvider, ...]] = field(default_factory=dict)
    # Compiled single-page
    compiled_filename: str | None = "menus.md"


@dataclass(slots=True)
class MenuDocEntry:
    """Metadata about an exported menu document."""

    key: str
    title: str
    description: str | None = None
    markdown_path: Path | None = None
    image_relpath: str | None = None
    table_lines: list[str] = field(default_factory=list)
    dialog_links: list[tuple[str, Path]] = field(default_factory=list)


@dataclass(slots=True)
class MenuDocResult:
    """Result bundle returned after exporting menu documentation."""

    entries: list[MenuDocEntry]
    overview_path: Path | None = None
    shortcuts_path: Path | None = None


_LOGGER = logging.getLogger(__name__)

_MENU_CONTEXT = "ManualMenu"
_ANNOTATIONS_CONTEXT = "ManualAnnotations"


def export_menu_docs(
    window: QMainWindow, spec: MenuDocSpec, config: MenuDocConfig
) -> MenuDocResult:
    """Generate Markdown tables describing application menus."""
    out_dir = config.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    action_factory = getattr(window, "action_factory", None)
    if action_factory is None:
        msg = "Target window does not expose an action_factory for menu export."
        raise TypeError(msg)

    actions_by_key = getattr(action_factory, "actions", None)
    menus_by_key = getattr(action_factory, "menus", None)
    if not isinstance(actions_by_key, dict) or not isinstance(menus_by_key, dict):
        msg = "Menu action factory does not provide expected mappings."
        raise TypeError(msg)

    action_lookup = {action: key for key, action in actions_by_key.items()}
    menu_keys = spec.menu_keys or tuple(menus_by_key.keys())

    entries: list[MenuDocEntry] = []
    all_shortcut_rows: list[tuple[str, str]] = []

    for menu_key in menu_keys:
        menu = menus_by_key.get(menu_key)
        if menu is None:
            continue
        entry = _collect_menu_content(
            menu=menu,
            menu_key=menu_key,
            spec=spec,
            config=config,
            action_lookup=action_lookup,
            all_shortcut_rows=all_shortcut_rows,
            window=window,
        )
        if config.write_individual_pages:
            entry.markdown_path = _write_individual_menu_page(entry, config)
        entries.append(entry)

    overview_path: Path | None = None
    if entries and config.overview_filename:
        overview_path = _write_overview(entries, config, spec)

    # Collect shortcuts from hidden actions marked for documentation
    if config.shortcuts_filename:
        _collect_extra_shortcuts(actions_by_key, all_shortcut_rows)

    shortcuts_path: Path | None = None
    if config.shortcuts_filename and all_shortcut_rows:
        shortcuts_path = _write_shortcuts(all_shortcut_rows, config)

    # Compiled single page (optional)
    if entries and getattr(config, "compiled_filename", None):
        _write_compiled_page(entries, config, spec)

    return MenuDocResult(
        entries=entries, overview_path=overview_path, shortcuts_path=shortcuts_path
    )


def _as_link_text(label: str) -> str:
    """リンク表示向けに末尾の三点リーダ（…/...）などを外して整形する。."""
    text = label.strip()
    if text.endswith("…"):
        text = text[:-1]
    elif text.endswith("..."):
        text = text[:-3]
    return text.strip()


def _collect_menu_content(
    *,
    menu: QMenu,
    menu_key: str,
    spec: MenuDocSpec,
    config: MenuDocConfig,
    action_lookup: dict[QAction, str],
    all_shortcut_rows: list[tuple[str, str]],
    window: QMainWindow,
) -> MenuDocEntry:
    actions = [action for action in menu.actions() if _is_documentable_action(action)]
    if not actions:
        return MenuDocEntry(
            key=menu_key, title=_menu_title(menu), description=spec.menu_descriptions.get(menu_key)
        )

    title = _menu_title(menu)
    description = spec.menu_descriptions.get(menu_key)
    # メニュー自体に doc.descKey がある場合は優先して訳す
    desc_key = menu.property("doc.descKey")
    if isinstance(desc_key, str) and desc_key.strip():
        description = translate_manual_text(_ANNOTATIONS_CONTEXT, desc_key.strip())

    columns: list[str] = [
        translate_manual_text(_MENU_CONTEXT, QT_TRANSLATE_NOOP("ManualMenu", "Action"))
    ]
    if config.include_shortcuts:
        columns.append(
            translate_manual_text(_MENU_CONTEXT, QT_TRANSLATE_NOOP("ManualMenu", "Shortcut"))
        )
    if config.include_modes:
        columns.append(
            translate_manual_text(
                _MENU_CONTEXT, QT_TRANSLATE_NOOP("ManualMenu", "Available Modes")
            )
        )
    if config.include_status or config.include_notes:
        columns.append(
            translate_manual_text(_MENU_CONTEXT, QT_TRANSLATE_NOOP("ManualMenu", "Description"))
        )

    # Optional dropdown screenshot
    image_relpath: str | None = None
    if config.include_screenshot:
        image_relpath = _capture_menu_image(menu, menu_key, config)

    table_builder = MarkdownTableBuilder(columns)

    dialog_links: list[tuple[str, Path]] = []
    for action in actions:
        action_key = action_lookup.get(action, "")
        label = _clean_label(action.text())
        shortcut_text = _format_shortcuts(action) if config.include_shortcuts else ""
        if shortcut_text and config.shortcuts_filename:
            all_shortcut_rows.append((label, shortcut_text))
        mode_text = _format_modes(action, action_key, spec, config) if config.include_modes else ""
        # アクション側に doc.descKey があれば最優先
        desc_key = action.property("doc.descKey")
        description_text = ""
        if isinstance(desc_key, str) and desc_key.strip():
            description_text = translate_manual_text(_ANNOTATIONS_CONTEXT, desc_key.strip())
        if config.include_status and not description_text:
            description_text = _format_description(action)
        if config.include_notes:
            note = spec.action_notes.get(action_key)
            if note:
                description_text = _merge_note(description_text, note)

        # Dialog documentation if providers exist
        providers = config.dialog_providers.get(action_key, ())
        for provider in providers:
            dialog_info = _export_dialog_doc(
                window=window,
                provider=provider,
                menu_key=menu_key,
                action_key=action_key,
                config=config,
            )
            if dialog_info is None:
                continue
            dialog_path, dialog_label = dialog_info
            link_text = dialog_label or _as_link_text(label)
            dialog_links.append((link_text, dialog_path))
            rel_dialog = dialog_path
            with contextlib.suppress(ValueError):
                rel_dialog = dialog_path.relative_to(config.out_dir)
            message = translate_manual_text(
                _MENU_CONTEXT,
                #: {label} と {path} は実行時に置換されるため書き換えないこと。
                QT_TRANSLATE_NOOP(
                    "ManualMenu", "See [{label}]({path}) for details of the dialog."
                ),
            ).format(label=link_text, path=rel_dialog.as_posix())
            description_text = _merge_note(description_text, message)

        row_values = [label]
        if config.include_shortcuts:
            row_values.append(shortcut_text or "―")
        if config.include_modes:
            row_values.append(
                mode_text
                or translate_manual_text(
                    _MENU_CONTEXT, QT_TRANSLATE_NOOP("ManualMenu", "All modes")
                )
            )
        if config.include_status or config.include_notes:
            row_values.append(description_text or "―")
        table_builder.add_row(row_values)

    return MenuDocEntry(
        key=menu_key,
        title=title,
        description=description,
        markdown_path=None,
        image_relpath=image_relpath,
        table_lines=table_builder.lines(),
        dialog_links=dialog_links,
    )


def _write_individual_menu_page(entry: MenuDocEntry, config: MenuDocConfig) -> Path:
    """Write a standalone page for a single menu using collected content."""
    header = [
        f"# {entry.title}",
        "",
        translate_manual_text(
            _MENU_CONTEXT,
            #: {menu} は実行時に置換されるため書き換えないこと。
            QT_TRANSLATE_NOOP(
                "ManualMenu", "This page explains the actions and shortcuts for the {menu} menu."
            ),
        ).format(menu=entry.title),
    ]
    if entry.description:
        header.extend(["", entry.description])
    if entry.image_relpath:
        header.extend(
            [
                "",
                "## "
                + translate_manual_text(
                    _MENU_CONTEXT, QT_TRANSLATE_NOOP("ManualMenu", "Menu Structure")
                ),
                f"![menu]({entry.image_relpath})",
            ]
        )
    lines = [*header, *entry.table_lines[:]]
    if entry.dialog_links:
        dialogs_heading = translate_manual_text(
            _MENU_CONTEXT, QT_TRANSLATE_NOOP("ManualMenu", "Dialogs Opened from This Menu")
        )
        lines.extend(["", f"## {dialogs_heading}", ""])
        for link_label, path in entry.dialog_links:
            rel = path
            with contextlib.suppress(ValueError):
                rel = path.relative_to(config.out_dir)
            lines.append(f"- [{link_label}]({rel.as_posix()})")
    filename = f"menu_{entry.key}.md"
    markdown_path = config.out_dir / filename
    _write_markdown(markdown_path, "\n".join(lines))
    return markdown_path


def _write_markdown(path: Path, content: str) -> None:
    formatted = format_markdown_text(content)
    if not formatted.endswith("\n"):
        formatted += "\n"
    path.write_text(formatted, encoding="utf-8")


def _is_documentable_action(action: QAction) -> bool:
    if action.isSeparator():
        return False
    if not action.isVisible():
        return False
    return not (not action.text() and not action.iconText())


def _collect_extra_shortcuts(
    actions_by_key: dict[str, QAction], shortcut_rows: list[tuple[str, str]]
) -> None:
    """Collect shortcuts from actions marked with doc.includeInShortcuts.

    This allows hidden actions (like toggle_velocity_plot_optimize) to appear
    in shortcuts.md even though they're not visible in menu tables.
    """
    for action in actions_by_key.values():
        if not action.property("doc.includeInShortcuts"):
            continue
        label = _clean_label(action.text())
        # Skip if already collected from menu
        if any(row[0] == label for row in shortcut_rows):
            continue
        shortcut_text = _format_shortcuts(action)
        if shortcut_text:
            shortcut_rows.append((label, shortcut_text))


def _menu_title(menu: QMenu) -> str:
    return _clean_label(menu.title() or menu.objectName() or "Menu")


def _clean_label(text: str) -> str:
    """自然な表記に整形する（アクセラレータ記号/括弧注記/三点リーダの統一）。."""
    cleaned = text.replace("&", "")
    # 例: "ファイル(&F)" / "ファイル(F)" / "ファイル（F）" → 括弧注記を除去
    cleaned = re.sub(r"[\s\u3000]*[\(（][A-Za-z0-9][\)）]", "", cleaned)
    # 例: "..." を和文の三点リーダに統一
    cleaned = cleaned.replace("...", "…")
    return cleaned.strip()


def _heading_anchor(title: str, *, fallback: str) -> str:
    """Derive a Markdown anchor slug from a heading title."""
    slug = title.strip().lower()
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"[^\w\-ー〜ぁ-んァ-ン一-龥々・0-9]", "", slug)
    if not slug:
        slug = fallback.strip().lower() or fallback
    return slug


def _format_shortcuts(action: QAction) -> str:
    # shortcut.key プロパティがあれば一元管理の定義を使用
    action_key = action.property("shortcut.key")
    if action_key:
        display = get_shortcut_display(action_key)
        if display:
            return display

    # カスタムショートカットなど、一元管理にない場合のフォールバック
    sequences: Iterable[QKeySequence]
    sequences = action.shortcuts()
    collected = []
    for seq in sequences:
        text = seq.toString(QKeySequence.SequenceFormat.PortableText)
        if not text:
            text = seq.toString(QKeySequence.SequenceFormat.NativeText)
        text = text.strip()
        if text and text not in collected:
            collected.append(text)
    if not collected:
        seq = action.shortcut()
        if not seq.isEmpty():
            text = seq.toString(QKeySequence.SequenceFormat.PortableText)
            if not text:
                text = seq.toString(QKeySequence.SequenceFormat.NativeText)
            text = text.strip()
            if text:
                collected.append(text)
    return ", ".join(collected)


def _format_modes(
    action: QAction, action_key: str, spec: MenuDocSpec, config: MenuDocConfig
) -> str:
    modes_obj = action.property("doc.modes")
    modes: tuple[str, ...] | None = None
    if isinstance(modes_obj, tuple | list):
        modes = tuple(str(mode) for mode in modes_obj if str(mode))
    if not modes:
        modes = spec.action_modes.get(action_key)
    if not modes:
        return translate_manual_text(_MENU_CONTEXT, QT_TRANSLATE_NOOP("ManualMenu", "All modes"))

    if "all" in modes or "*" in modes:
        return translate_manual_text(_MENU_CONTEXT, QT_TRANSLATE_NOOP("ManualMenu", "All modes"))

    translated = []
    for mode in modes:
        label = config.mode_labels.get(mode, mode)
        if label not in translated:
            translated.append(label)
    return " / ".join(translated)


def _format_description(action: QAction) -> str:
    for attribute in ("statusTip", "toolTip", "whatsThis"):
        getter = getattr(action, attribute, None)
        if callable(getter):
            value = getter()
            if value:
                return " ".join(value.split())
    return ""


def _merge_note(base: str, note: str) -> str:
    if not base:
        return note
    return f"{base} ※{note}"


def _write_overview(entries: list[MenuDocEntry], config: MenuDocConfig, spec: MenuDocSpec) -> Path:
    lines = [
        "# "
        + translate_manual_text(_MENU_CONTEXT, QT_TRANSLATE_NOOP("ManualMenu", "Menu Overview")),
        "",
    ]
    # 集約ページへの誘導（後方互換のため概要ページは維持）
    compiled_name = config.compiled_filename or "menus.md"
    lines.append(
        translate_manual_text(
            _MENU_CONTEXT,
            #: {name} は実行時に置換されるため書き換えないこと。
            QT_TRANSLATE_NOOP(
                "ManualMenu",
                "This is the legacy format. Please use [Menus (Single Page)]({name}) instead.",
            ),
        ).format(name=compiled_name)
    )
    lines.append("")
    desc = spec.menu_descriptions.get("__overview__")
    if desc:
        lines.append(desc)
        lines.append("")
    for entry in entries:
        rel_path = entry.markdown_path.name
        description = entry.description or ""
        if description:
            lines.append(f"- [{entry.title}]({rel_path}) — {description}")
        else:
            lines.append(f"- [{entry.title}]({rel_path})")
    target = config.out_dir / config.overview_filename
    _write_markdown(target, "\n".join(lines))
    return target


def _write_shortcuts(shortcut_rows: list[tuple[str, str]], config: MenuDocConfig) -> Path:
    unique_rows: dict[str, set[str]] = {}
    for label, shortcut in shortcut_rows:
        if not shortcut:
            continue
        parts = [part.strip() for part in shortcut.split(",") if part.strip()]
        if not parts:
            continue
        shortcut_set = unique_rows.setdefault(label, set())
        shortcut_set.update(parts)

    if not unique_rows:
        msg = "No shortcuts available to generate shortcut table."
        raise ValueError(msg)

    shortcuts_title = translate_manual_text(
        _MENU_CONTEXT, QT_TRANSLATE_NOOP("ManualMenu", "Shortcuts")
    )
    shortcuts_header = translate_manual_text(
        _MENU_CONTEXT, QT_TRANSLATE_NOOP("ManualMenu", "| Action | Shortcut |")
    )
    lines = [f"# {shortcuts_title}", "", shortcuts_header, "| --- | --- |"]
    for label in sorted(unique_rows):
        shortcut_list = ", ".join(sorted(unique_rows[label]))
        lines.append(f"| {label} | {shortcut_list} |")

    target = config.out_dir / config.shortcuts_filename
    _write_markdown(target, "\n".join(lines))
    return target


def _write_compiled_page(
    entries: list[MenuDocEntry], config: MenuDocConfig, spec: MenuDocSpec
) -> Path:
    """Generate a single-page menu manual with stable anchors."""
    lines: list[str] = []
    lines.append(
        "# " + translate_manual_text(_MENU_CONTEXT, QT_TRANSLATE_NOOP("ManualMenu", "Menus"))
    )
    lines.append("")
    lines.append(
        translate_manual_text(
            _MENU_CONTEXT,
            QT_TRANSLATE_NOOP(
                "ManualMenu",
                "This single page summarises all top menus. Use the table of contents below to jump to a menu.",
            ),
        )
    )
    lines.append("")
    #: {slug} は実行時に置換されるため書き換えないこと。
    profile_line = translate_manual_text(
        _MENU_CONTEXT, QT_TRANSLATE_NOOP("ManualMenu", "> Profile: {slug}")
    ).format(slug=spec.slug)
    lines.extend([profile_line, ""])
    # 目次
    lines.append(
        "## "
        + translate_manual_text(
            _MENU_CONTEXT, QT_TRANSLATE_NOOP("ManualMenu", "Table of Contents")
        )
    )
    lines.append("")
    for entry in entries:
        anchor = _heading_anchor(entry.title, fallback=entry.key)
        lines.append(f"- [{entry.title}](#{anchor})")
    lines.append("")

    # 各メニュー本体（アンカー付き）
    for entry in entries:
        # 見出しは通常の Markdown を利用（アンカーは自動生成に委ねる）
        lines.append(f"## {entry.title}")
        lines.append("")
        if entry.description:
            lines.append(entry.description)
            lines.append("")

        # メニュー画像
        key = entry.key
        image_path = config.out_dir / "images" / f"{key}_dropdown.png"
        if image_path.exists():
            lines.append(
                "### "
                + translate_manual_text(
                    _MENU_CONTEXT, QT_TRANSLATE_NOOP("ManualMenu", "Menu Structure")
                )
            )
            rel = image_path.relative_to(config.out_dir).as_posix()
            lines.append(f"![menu]({rel})")
            lines.append("")

        # 操作一覧（テーブル）
        if entry.table_lines:
            lines.append(
                "### "
                + translate_manual_text(_MENU_CONTEXT, QT_TRANSLATE_NOOP("ManualMenu", "Actions"))
            )
            lines.extend(entry.table_lines)
            lines.append("")

        # ダイアログ一覧（あれば）
        if entry.dialog_links:
            lines.append(
                "### "
                + translate_manual_text(
                    _MENU_CONTEXT, QT_TRANSLATE_NOOP("ManualMenu", "Dialogs Opened from This Menu")
                )
            )
            for link_label, path in entry.dialog_links:
                rel = path
                with contextlib.suppress(ValueError):
                    rel = path.relative_to(config.out_dir)
                lines.append(f"- [{link_label}]({rel.as_posix()})")
            lines.append("")

        # 戻りリンクは付けない（ページ内アンカーとブラウザの戻る操作で十分）

    compiled = config.out_dir / (config.compiled_filename or "menus.md")
    _write_markdown(compiled, "\n".join(lines))
    return compiled


# --- New helpers: screenshots and dialog exports --------------------------------


def _capture_menu_image(menu: QMenu, menu_key: str, config: MenuDocConfig) -> str | None:
    """Show the QMenu offscreen and capture its rendered content as an image.

    Returns a relative path (from the menu document directory) suitable for Markdown.
    """
    try:
        app = QApplication.instance()
        if app is None:
            return None

        # Ensure geometry/layout is realized
        menu.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        menu.show()
        app.processEvents()

        pix = menu.grab()
        menu.hide()
        if pix.isNull():
            return None

        scaled = scale_pixmap(pix, width=config.screenshot_scale_width)
        images_dir = config.out_dir / "images"
        images_dir.mkdir(exist_ok=True)
        key = menu.objectName() or menu_key or "menu"
        filename = f"{key}_dropdown.png"
        out_path = images_dir / filename
        scaled.save(str(out_path))
    except (OSError, RuntimeError):
        # Non-fatal: screenshot is optional
        return None
    else:
        return f"images/{filename}"


def _export_dialog_doc(
    *,
    window: QMainWindow,
    provider: DialogProvider,
    menu_key: str,
    action_key: str,
    config: MenuDocConfig,
) -> tuple[Path, str | None] | None:
    """Materialise a dialog widget and export its annotated doc using the window exporter."""
    try:
        dialog = provider.factory(window)
        if dialog is None:
            return None
        # Avoid modal loops; just show to lay out widgets
        if hasattr(dialog, "setModal"):
            dialog.setModal(False)  # type: ignore[call-arg]
        dialog.show()
        app = QApplication.instance()
        if app is not None:
            app.processEvents()

        # Reuse the generic exporter for any QWidget-like window
        out_dir = config.out_dir / config.dialog_output_subdir
        out_dir.mkdir(parents=True, exist_ok=True)
        export_config = DocExportConfig(
            out_dir=out_dir,
            version=config.version,
            include_tabs=False,
            scale_width=max(640, config.screenshot_scale_width),
            include_scopes=set(),  # dialogs are unscoped
            include_unscoped=True,
        )
        apply_doc_annotations(dialog)
        result = export_window_docs(dialog, export_config)  # type: ignore[arg-type]
        if hasattr(dialog, "close"):
            dialog.close()
        path = result.markdown_path
        if path is None:
            return None

        label = provider.label
        if label is None and provider.label_getter is not None:
            try:
                label_candidate = provider.label_getter(dialog)
            except (RuntimeError, TypeError):
                label_candidate = None
            if label_candidate:
                label = label_candidate
        if label is None:
            label = _dialog_title_from_path(path)

    except (RuntimeError, TypeError, ValueError):
        # Best-effort: if dialog can't be constructed in doc env, skip silently
        return None
    else:
        _LOGGER.debug(
            "Exported dialog documentation (menu=%s, action=%s) -> %s", menu_key, action_key, path
        )
        return path, label


def _dialog_title_from_path(path: Path) -> str:
    """Build a readable title from a dialog markdown path."""
    title = path.stem
    if title.endswith("Dialog"):
        title = title.removesuffix("Dialog")
    return title
