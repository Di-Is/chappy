"""Shared helpers for documentation text and localisation."""

from __future__ import annotations

from functools import cache
from typing import TYPE_CHECKING

from PySide6.QtCore import QT_TRANSLATE_NOOP

from chappy.core.editing_mode import EditingMode
from chappy.i18n import get_language_switcher
from chappy_user_manual_generator.translations import translate_manual_text

if TYPE_CHECKING:
    from chappy.i18n.language_switcher import LanguageSwitcher

_TEMPLATES_CONTEXT = "ManualTemplates"


@cache
def _load_language_switcher() -> LanguageSwitcher | None:
    """Return cached language switcher instance if available."""
    try:
        return get_language_switcher()
    except (
        RuntimeError,
        ImportError,
    ):  # pragma: no cover - initialisation can fail in headless tests
        return None


def reset_language_switcher_cache() -> None:
    """Clear cached language switcher instance."""
    _load_language_switcher.cache_clear()


def language_switcher() -> LanguageSwitcher | None:
    """Return cached language switcher instance if available."""
    return _load_language_switcher()


#: {version} は実行時に置換されるため書き換えないこと。
_VERSION_LINE_SOURCE = QT_TRANSLATE_NOOP("ManualTemplates", "Target version: {version}")
_MODE_LABEL_START_SOURCE = QT_TRANSLATE_NOOP("ManualTemplates", "Start")
_MODE_LABEL_IDENTIFY_SOURCE = QT_TRANSLATE_NOOP("ManualTemplates", "Identify")
_MODE_LABEL_CONTINUUM_SOURCE = QT_TRANSLATE_NOOP("ManualTemplates", "Continuum")
_MODE_LABEL_ANALYSIS_SOURCE = QT_TRANSLATE_NOOP("ManualTemplates", "Analysis")


def doc_version_line(version: str) -> str:
    """Return a formatted 'version' line for documentation pages."""
    template = translate_manual_text(_TEMPLATES_CONTEXT, _VERSION_LINE_SOURCE)
    return template.format(version=version)


def mode_label_map() -> dict[str, str]:
    """Return the standard editing mode label mapping."""
    return {
        EditingMode.START.value: translate_manual_text(
            _TEMPLATES_CONTEXT, _MODE_LABEL_START_SOURCE
        ),
        EditingMode.IDENTIFY.value: translate_manual_text(
            _TEMPLATES_CONTEXT, _MODE_LABEL_IDENTIFY_SOURCE
        ),
        EditingMode.CONTINUUM.value: translate_manual_text(
            _TEMPLATES_CONTEXT, _MODE_LABEL_CONTINUUM_SOURCE
        ),
        EditingMode.ANALYSIS.value: translate_manual_text(
            _TEMPLATES_CONTEXT, _MODE_LABEL_ANALYSIS_SOURCE
        ),
    }
