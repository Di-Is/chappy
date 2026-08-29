"""Cross-platform Qt application font selection."""

from __future__ import annotations

import logging
import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtGui import QFont, QFontDatabase, QFontMetrics

from chappy.gui.theme import Fonts

if TYPE_CHECKING:
    from collections.abc import Callable, MutableMapping, Sequence

    from PySide6.QtWidgets import QApplication

logger = logging.getLogger(__name__)

FONT_GLYPH_SAMPLE = "Chappy 日本語 0123456789"


class FontConfigurationError(RuntimeError):
    """Raised when no font can render the required application glyphs."""


@dataclass(frozen=True, slots=True)
class ApplicationFontSelection:
    """Font selected for Qt application widgets."""

    family: str
    point_size: int


def platform_font_candidates(system_name: str) -> tuple[str, ...]:
    """Return preferred Japanese-capable font families for an operating system."""
    normalized = system_name.lower()
    if normalized == "darwin":
        return ("Hiragino Sans", "Hiragino Kaku Gothic ProN", "Yu Gothic", "Yu Gothic UI")
    if normalized == "windows":
        return ("Yu Gothic UI", "Yu Gothic", "Meiryo", "MS Gothic")
    if normalized == "linux":
        return ("Noto Sans CJK JP", "Noto Sans JP", "IPAexGothic", "IPAGothic")
    return ()


def common_font_candidates() -> tuple[str, ...]:
    """Return cross-platform Japanese-capable fallback font families."""
    return (
        "Noto Sans CJK JP",
        "Noto Sans JP",
        "Hiragino Sans",
        "Hiragino Kaku Gothic ProN",
        "Yu Gothic UI",
        "Yu Gothic",
        "Meiryo",
        "IPAexGothic",
        "IPAGothic",
        "MS Gothic",
    )


def application_font_candidates(system_name: str | None = None) -> tuple[str, ...]:
    """Return de-duplicated font candidates in platform preference order."""
    active_system = system_name or platform.system()
    return tuple(
        dict.fromkeys((*platform_font_candidates(active_system), *common_font_candidates()))
    )


def choose_font_family(
    candidates: Sequence[str],
    available_families: set[str],
    supports_required_glyphs: Callable[[str], bool],
) -> str | None:
    """Choose the first available candidate that supports required glyphs."""
    return next(
        (
            family
            for family in candidates
            if family in available_families and supports_required_glyphs(family)
        ),
        None,
    )


def font_supports_japanese(family: str) -> bool:
    """Return whether Qt reports Japanese support for a font family."""
    if family not in QFontDatabase.families():
        return False
    writing_systems = QFontDatabase.writingSystems(family)
    if QFontDatabase.WritingSystem.Japanese not in writing_systems:
        return False
    metrics = QFontMetrics(QFont(family, Fonts.POINT_SIZE_NORMAL))
    return all(
        metrics.inFontUcs4(ord(character))
        for character in FONT_GLYPH_SAMPLE
        if not character.isspace()
    )


def configure_application_font(
    app: QApplication, *, strict: bool = False
) -> ApplicationFontSelection | None:
    """Apply a Japanese-capable font to a Qt application.

    Args:
        app: Qt application whose global widget font is updated.
        strict: Raise when no compatible font is available instead of retaining
            Qt's default font.
    """
    available_families = set(QFontDatabase.families())
    family = choose_font_family(
        application_font_candidates(), available_families, font_supports_japanese
    )
    if family is not None:
        point_size = Fonts.POINT_SIZE_NORMAL
        app.setFont(QFont(family, point_size))
        logger.info("Configured application font: %s", family)
        return ApplicationFontSelection(family=family, point_size=point_size)

    sample = ", ".join(sorted(available_families)[:10]) or "<none>"
    message = f"No Japanese-capable Qt font is available. Available font samples: {sample}."
    if strict:
        raise FontConfigurationError(message)
    logger.warning(message)
    return None


def configure_offscreen_font_environment(
    *,
    platform_name: str | None = None,
    system_name: str | None = None,
    environment: MutableMapping[str, str] | None = None,
) -> Path | None:
    """Expose Windows system fonts to Qt's offscreen font database.

    This must run before constructing ``QApplication``.
    """
    active_environment = environment if environment is not None else os.environ
    active_platform = (
        platform_name
        if platform_name is not None
        else active_environment.get("QT_QPA_PLATFORM", "")
    )
    active_system = (system_name if system_name is not None else platform.system()).lower()
    if active_platform != "offscreen" or active_system != "windows":
        return None

    system_root = active_environment.get("SystemRoot", r"C:\Windows")
    font_directory = Path(system_root) / "Fonts"
    if not font_directory.is_dir():
        return None
    active_environment.setdefault("QT_QPA_FONTDIR", str(font_directory))
    return font_directory
