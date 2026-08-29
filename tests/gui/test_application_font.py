"""Tests for cross-platform Qt application font selection."""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

import chappy.gui.application_font as application_font
from chappy.gui.application_font import (
    FontConfigurationError,
    application_font_candidates,
    choose_font_family,
    configure_application_font,
    configure_offscreen_font_environment,
)


def test_application_font_candidates_prefer_platform_fonts() -> None:
    candidates = application_font_candidates("windows")

    assert candidates[:4] == ("Yu Gothic UI", "Yu Gothic", "Meiryo", "MS Gothic")
    assert len(candidates) == len(set(candidates))


def test_choose_font_family_skips_unsupported_candidates() -> None:
    selected = choose_font_family(
        ("Unavailable", "Latin only", "Japanese"),
        {"Latin only", "Japanese"},
        lambda family: family == "Japanese",
    )

    assert selected == "Japanese"


def test_configure_offscreen_font_environment_exposes_windows_fonts(tmp_path: Path) -> None:
    font_directory = tmp_path / "Fonts"
    font_directory.mkdir()
    environment = {"QT_QPA_PLATFORM": "offscreen", "SystemRoot": str(tmp_path)}

    selected_directory = configure_offscreen_font_environment(
        system_name="windows", environment=environment
    )

    assert selected_directory == font_directory
    assert environment["QT_QPA_FONTDIR"] == str(font_directory)


def test_configure_offscreen_font_environment_ignores_non_offscreen(tmp_path: Path) -> None:
    environment = {"QT_QPA_PLATFORM": "windows", "SystemRoot": str(tmp_path)}

    selected_directory = configure_offscreen_font_environment(
        system_name="windows", environment=environment
    )

    assert selected_directory is None
    assert "QT_QPA_FONTDIR" not in environment


def test_configure_application_font_strict_mode_rejects_missing_fonts(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(application_font, "application_font_candidates", lambda: ("Missing",))
    monkeypatch.setattr(application_font.QFontDatabase, "families", lambda: [])

    with pytest.raises(FontConfigurationError, match="No Japanese-capable Qt font"):
        configure_application_font(qapp, strict=True)
