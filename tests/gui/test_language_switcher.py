"""Tests for the runtime language switcher."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtTest import QSignalSpy

from chappy.i18n import language_switcher as lm
from chappy.i18n.language_switcher import LanguageSwitcher


@pytest.fixture(autouse=True)
def reset_language_singleton() -> None:
    lm._INSTANCE = None
    yield
    lm._INSTANCE = None


@pytest.fixture()
def config_root(tmp_path: Path) -> Path:
    directory = tmp_path / "config"
    directory.mkdir()
    return directory


def test_reads_saved_language_preference(qtbot, config_root: Path) -> None:
    (config_root / "config.toml").write_text('[ui]\nlanguage = "en"\n', encoding="utf-8")

    switcher = LanguageSwitcher(config_dir=config_root)

    assert switcher.current_language == "en"


def test_reads_locale_language_preference_as_internal_id(qtbot, config_root: Path) -> None:
    (config_root / "config.toml").write_text('[ui]\nlanguage = "ja_JP"\n', encoding="utf-8")

    switcher = LanguageSwitcher(config_dir=config_root)

    assert switcher.current_language == "ja"


def test_language_labels_are_display_names(qtbot, config_root: Path) -> None:
    switcher = LanguageSwitcher(config_dir=config_root)

    assert switcher.label_for("ja") == "日本語"
    assert switcher.label_for("ja_JP") == "日本語"
    assert switcher.label_for("en") == "English"


def test_persists_language_changes_and_emits_signal(qtbot, config_root: Path) -> None:
    (config_root / "config.toml").write_text('[ui]\nlanguage = "ja"\n', encoding="utf-8")
    switcher = LanguageSwitcher(config_dir=config_root)

    spy = QSignalSpy(switcher.language_changed)

    switcher.set_language("en")

    assert spy.count() == 1
    assert spy.at(0)[0] == "en"

    content = (config_root / "config.toml").read_text(encoding="utf-8")
    assert 'language = "en"' in content


def test_set_language_normalizes_locale_code(qtbot, config_root: Path) -> None:
    (config_root / "config.toml").write_text('[ui]\nlanguage = "en"\n', encoding="utf-8")
    switcher = LanguageSwitcher(config_dir=config_root)

    switcher.set_language("ja_JP")

    assert switcher.current_language == "ja"
