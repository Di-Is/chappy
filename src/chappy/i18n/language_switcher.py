"""Runtime language management utilities for the chappy GUI.

This module stores the current language selection, persists it to the user
configuration file, and exposes a Qt friendly interface for reacting to
language changes at runtime. Translations themselves are provided by the Qt
catalogs installed through :mod:`chappy.i18n.qt_translator`.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable

from PySide6.QtCore import QLocale, QObject, QSettings, Signal
from shiboken6 import Shiboken as _ShibokenRuntime

from chappy.i18n.languages import (
    DEFAULT_LANGUAGE_ID,
    LANGUAGES,
    LanguageDefinition,
    normalize_language_id,
    require_language,
)


@runtime_checkable
class _ShibokenProtocol(Protocol):
    """Protocol describing the subset of Shiboken API we rely on."""

    @staticmethod
    def isValid(obj: QObject) -> bool:
        """Return whether the wrapped C++ object is still valid."""
        ...


Shiboken: _ShibokenProtocol = cast("_ShibokenProtocol", _ShibokenRuntime)

if TYPE_CHECKING:
    from collections.abc import Iterable


_CONFIG_ENV_VAR = "CHAPPY_CONFIG_DIR"
_CONFIG_FILENAME = "config.toml"


class LanguageSwitcher(QObject):
    """Switch the active language and notify listeners about changes."""

    language_changed = Signal(str)

    def __init__(self, parent: QObject | None = None, *, config_dir: Path | None = None) -> None:
        """Create the switcher, restoring the persisted language selection.

        Args:
            parent: Optional Qt parent object.
            config_dir: Optional directory for persisted language settings.
        """
        super().__init__(parent)

        self._options = LANGUAGES

        base_dir = config_dir or self._default_config_dir()
        self._config_dir = base_dir
        self._config_file = self._config_dir / _CONFIG_FILENAME

        self._current_language = self._load_initial_language()

    @property
    def options(self) -> Iterable[LanguageDefinition]:
        """Return iterable of supported language options."""
        return self._options.values()

    @property
    def current_language(self) -> str:
        """Return the currently active language code."""
        return self._current_language

    def label_for(self, code: str) -> str:
        """Return the display label for a supported language."""
        option = self._require_option(code)
        return option.display_name

    def set_language(self, code: str) -> None:
        """Activate a new language and persist the choice."""
        normalized_code = normalize_language_id(code)
        if normalized_code == self._current_language:
            return

        self._require_option(normalized_code)

        previous = self._current_language
        self._current_language = normalized_code

        try:
            self._persist_language_setting(normalized_code)
        except OSError:
            self._current_language = previous
            raise

        self.language_changed.emit(normalized_code)

    def retranslate(self) -> None:
        """Emit change notification for the current language."""
        self.language_changed.emit(self._current_language)

    def _require_option(self, code: str) -> LanguageDefinition:
        return require_language(code)

    def _load_initial_language(self) -> str:
        saved = self._read_saved_language()
        if saved:
            return saved

        locale = QLocale.system()
        if locale.language() == QLocale.Language.Japanese:
            return "ja"
        if locale.language() == QLocale.Language.English:
            return "en"

        return DEFAULT_LANGUAGE_ID

    def _read_saved_language(self) -> str | None:
        if not self._config_file.exists():
            return None

        try:
            content = self._config_file.read_text(encoding="utf-8")
            config = tomllib.loads(content)
        except (OSError, tomllib.TOMLDecodeError):
            return None

        direct = config.get("language")
        if isinstance(direct, str):
            try:
                return normalize_language_id(direct)
            except ValueError:
                pass

        ui_section = config.get("ui")
        if isinstance(ui_section, dict):
            value = ui_section.get("language")
            if isinstance(value, str):
                try:
                    return normalize_language_id(value)
                except ValueError:
                    pass

        return None

    def _persist_language_setting(self, code: str) -> None:
        config: dict[str, Any] = {}
        if self._config_file.exists():
            try:
                content = self._config_file.read_text(encoding="utf-8")
                config = tomllib.loads(content)
            except (OSError, tomllib.TOMLDecodeError):
                config = {}

        ui_section = config.setdefault("ui", {})
        if not isinstance(ui_section, dict):
            ui_section = {}
            config["ui"] = ui_section

        ui_section["language"] = code

        self._config_dir.mkdir(parents=True, exist_ok=True)
        serialized = self._dump_toml(config)
        self._config_file.write_text(serialized, encoding="utf-8")

        settings = QSettings()
        settings.setValue("ui/language", code)

    def _dump_toml(self, data: dict[str, Any]) -> str:
        lines = self._dump_toml_section(data, ())
        return "\n".join(lines).strip() + "\n"

    def _dump_toml_section(self, data: dict[str, Any], path: tuple[str, ...]) -> list[str]:
        scalars: list[tuple[str, Any]] = []
        subtables: list[tuple[str, dict[str, Any]]] = []

        for key, value in data.items():
            if isinstance(value, dict):
                subtables.append((key, value))
            else:
                scalars.append((key, value))

        lines: list[str] = []
        if path:
            lines.append(f"[{'.'.join(path)}]")

        for key, value in scalars:
            lines.append(f"{key} = {self._format_toml_scalar(value)}")

        for key, value in subtables:
            if lines:
                lines.append("")
            lines.extend(self._dump_toml_section(value, (*path, key)))

        return lines

    def _format_toml_scalar(self, value: object) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int | float):
            return str(value)
        if isinstance(value, str):
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        return f'"{value!s}"'

    def _default_config_dir(self) -> Path:
        env_override = os.environ.get(_CONFIG_ENV_VAR)
        if env_override:
            return Path(env_override).expanduser().resolve()
        return Path.home() / ".chappy"


_INSTANCE: LanguageSwitcher | None = None


def _is_qobject_valid(obj: QObject | None) -> bool:
    """Check whether the Qt object still wraps a live C++ instance.

    Args:
        obj: QObject to validate.

    Returns:
        True when the C++ object is valid.
    """
    if obj is None:
        return False
    try:
        return bool(Shiboken.isValid(obj))
    except (RuntimeError, SystemError):
        return False


def _resolve_parent(candidate: QObject | None) -> QObject | None:  # noqa: ARG001
    """Choose a parent for the singleton.

    Args:
        candidate: Preferred parent provided by the caller (unused).

    Returns:
        None to avoid lifecycle issues with QApplication during tests.
    """
    # Don't parent to QApplication to avoid crashes when QApplication
    # is destroyed between pytest runs.
    return None


def get_language_switcher(parent: QObject | None = None) -> LanguageSwitcher:
    """Return singleton language switcher instance.

    The returned object is reparented to the current Qt application to ensure
    it survives widget teardown during tests.
    """
    global _INSTANCE  # noqa: PLW0603
    if _INSTANCE is None or not _is_qobject_valid(_INSTANCE):
        _INSTANCE = LanguageSwitcher(_resolve_parent(parent))
    else:
        resolved_parent = _resolve_parent(parent)
        if resolved_parent is not None and _INSTANCE.parent() is not resolved_parent:
            _INSTANCE.setParent(resolved_parent)
    return _INSTANCE
