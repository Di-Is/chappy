"""Qt translation catalog loading for the manual generator."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication

from chappy.i18n import QtTranslatorInstaller

_MANUAL_CATALOG_PREFIX = "manual"
_MANUAL_TRANSLATION_ROOT = Path(__file__).resolve().parent / "i18n"

_installers: list[QtTranslatorInstaller] = []


def install_language(language_code: str) -> None:
    """Install Qt translation catalogs for the manual generator.

    Loads the manual generator's own catalog plus the chappy runtime catalog
    (``src/chappy/i18n/qt``, prefix ``chappy``) so that shared metadata such
    as ``MenuRegistry`` descriptions resolves through the same mechanism.

    Args:
        language_code: Language code such as ``en`` or ``ja``.
    """
    if not _installers:
        _installers.append(
            QtTranslatorInstaller(
                translation_root=_MANUAL_TRANSLATION_ROOT, catalog_prefix=_MANUAL_CATALOG_PREFIX
            )
        )
        _installers.append(QtTranslatorInstaller())

    for installer in _installers:
        installer.install_language(language_code)


def translate_manual_text(
    context: str, source_text: str, disambiguation: str | None = None
) -> str:
    """Translate an English source string through the manual generator's Qt catalog.

    Args:
        context: Qt translation context (for example ``ManualAnnotations``).
        source_text: English source string as it appears in the code/YAML.
        disambiguation: Optional Qt disambiguation comment for duplicate sources.

    Returns:
        Translated text, or ``source_text`` unchanged when no catalog entry
        matches (this is the normal Qt behaviour for the source language and
        for untranslated messages).
    """
    if not source_text:
        return source_text
    return QCoreApplication.translate(context, source_text, disambiguation)
