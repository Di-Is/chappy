"""Doc-only widget annotations injected during manual generation.

This module centralises `doc.*` property assignments so that runtime UI code
remains free from documentation/i18n concerns. The pipeline calls
`apply_doc_annotations` before exporting screenshots and tables.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

if TYPE_CHECKING:
    from PySide6.QtWidgets import QMainWindow
else:
    QMainWindow = Any  # type: ignore[misc, assignment]

LOGGER = logging.getLogger(__name__)
ANNOTATIONS_PATH = Path(__file__).with_name("annotations_map.yaml")


class DocAnnotationError(RuntimeError):
    """Raised when a documentation annotation cannot be resolved."""


def _resolve_text(value: object) -> str:
    if not isinstance(value, str):
        msg = f"Doc annotation 'text' must be a string, got {value!r}"
        raise DocAnnotationError(msg)
    return value


def _normalize(value: object) -> object:
    if isinstance(value, Mapping):
        if "text" in value:
            return _resolve_text(value["text"])
        return {str(key): _normalize(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


def _iter_python_children(window: QMainWindow) -> list[QWidget]:
    return window.findChildren(QWidget, options=Qt.FindChildrenRecursively)


def _resolve_window_path(window: QMainWindow, path: str) -> QWidget | None:
    current: Any = window
    for attr in path.split("."):
        if not attr:
            return None
        current = getattr(current, attr, None)
        if current is None:
            return None
    return current if isinstance(current, QWidget) else None


def _resolve_by_object_name(window: QMainWindow, name: str) -> list[QWidget]:
    if not name:
        return []
    return window.findChildren(QWidget, name, Qt.FindChildrenRecursively)


def _resolve_by_class_name(window: QMainWindow, class_name: str) -> list[QWidget]:
    if not class_name:
        return []
    candidates = CLASS_NAME_ALIASES.get(class_name, (class_name,))
    matches = [
        child for child in _iter_python_children(window) if child.__class__.__name__ in candidates
    ]
    if window.__class__.__name__ in candidates:
        matches.append(window)
    return matches


def _resolve_targets(window: QMainWindow, target: str) -> list[QWidget]:
    if target == "window":
        return [window]
    if target.startswith("window."):
        widget = _resolve_window_path(window, target[len("window.") :])
        return [widget] if widget is not None else []
    if target.startswith("objectName:"):
        return _resolve_by_object_name(window, target.split(":", 1)[1])
    if target.startswith("class:"):
        return _resolve_by_class_name(window, target.split(":", 1)[1])
    LOGGER.warning("Unsupported doc annotation target '%s'", target)
    return []


def _apply_props(widget: QWidget, props: Mapping[str, Any]) -> None:
    for name, value in props.items():
        widget.setProperty(name, _normalize(value))


def _load_annotations() -> list[tuple[str, Mapping[str, object]]]:
    if not ANNOTATIONS_PATH.exists():
        return []
    try:
        with ANNOTATIONS_PATH.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or []
    except yaml.YAMLError:  # pragma: no cover - configuration error path
        LOGGER.exception("Failed to parse %s", ANNOTATIONS_PATH)
        return []

    entries: list[tuple[str, Mapping[str, object]]] = []
    if not isinstance(data, list):
        LOGGER.warning("Doc annotations file must be a list of mappings")
        return entries

    for item in data:
        if not isinstance(item, Mapping):
            LOGGER.warning("Doc annotation entry is not a mapping: %r", item)
            continue
        target = item.get("target")
        props = item.get("props")
        if not isinstance(target, str):
            LOGGER.warning("Doc annotation entry missing string target: %r", item)
            continue
        if not isinstance(props, Mapping):
            LOGGER.warning("Doc annotation entry missing props mapping: %r", item)
            continue
        entries.append((target, props))
    return entries


def _apply_yaml_annotations(window: QMainWindow) -> set[str]:
    applied: set[str] = set()
    for target, props in _load_annotations():
        widgets = _resolve_targets(window, target)
        if not widgets:
            LOGGER.debug("Doc annotation target '%s' did not resolve to any widgets", target)
            continue
        for widget in widgets:
            _apply_props(widget, props)
        applied.add(target)
    return applied


def apply_doc_annotations(window: QMainWindow) -> None:
    """Attach doc properties to key widgets for documentation export only."""
    _apply_yaml_annotations(window)


CLASS_NAME_ALIASES: dict[str, tuple[str, ...]] = {"MainWindow": ("MainWindow",)}
