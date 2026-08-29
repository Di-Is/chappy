"""Supported application language definitions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LanguageDefinition:
    """Describe a supported application language."""

    id: str
    qt_locale: str
    catalog_suffix: str | None
    display_name: str


SOURCE_LANGUAGE_ID = "en"
DEFAULT_LANGUAGE_ID = "ja"

LANGUAGES: dict[str, LanguageDefinition] = {
    "ja": LanguageDefinition(
        id="ja", qt_locale="ja_JP", catalog_suffix="ja", display_name="日本語"
    ),
    "en": LanguageDefinition(id="en", qt_locale="en", catalog_suffix=None, display_name="English"),
}


def normalize_language_id(language_id: str) -> str:
    """Normalize a user or Qt locale language identifier.

    Args:
        language_id: Internal language id or locale-like language code.

    Returns:
        Supported internal language id.

    Raises:
        ValueError: When the language is not supported.
    """
    normalized = language_id.replace("-", "_")
    lowered = normalized.lower()
    for definition in LANGUAGES.values():
        if lowered == definition.id.lower() or lowered == definition.qt_locale.lower():
            return definition.id

    base_id = lowered.split("_", maxsplit=1)[0]
    if base_id in LANGUAGES:
        return base_id

    msg = f"Unsupported language code: {language_id}"
    raise ValueError(msg)


def require_language(language_id: str) -> LanguageDefinition:
    """Return a language definition for an internal id or locale.

    Args:
        language_id: Internal language id or locale-like language code.

    Returns:
        Supported language definition.
    """
    return LANGUAGES[normalize_language_id(language_id)]
