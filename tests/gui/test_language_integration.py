"""Integration tests for language switching within the main window."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtTest import QSignalSpy

from chappy.core.editing_mode import EditingMode
from chappy.gui.shell.main_window import MainWindow
from chappy.gui.modes.identify.presets.preset_store import IdentifyPresetStore
from chappy.gui.shell.actions.ids import ShellActionId
from chappy.gui.shell.composition import create_main_window
from chappy.gui.shell.dependencies import ShellDependencies
from chappy.i18n import QtTranslatorInstaller
from chappy.i18n import language_switcher as lm
from chappy.i18n.language_switcher import LanguageSwitcher
from chappy.infrastructure.composition import create_default_infrastructure_dependencies


@pytest.fixture()
def language_switcher(tmp_path: Path, monkeypatch, qapp) -> LanguageSwitcher:
    config_dir = tmp_path / "cfg"
    monkeypatch.setenv("CHAPPY_CONFIG_DIR", str(config_dir))
    lm._INSTANCE = None
    switcher = LanguageSwitcher(config_dir=config_dir)
    switcher.set_language("ja")
    lm._INSTANCE = switcher
    installer = QtTranslatorInstaller(qapp)
    installer.install_language(switcher.current_language)
    switcher.language_changed.connect(installer.install_language)
    yield switcher
    installer.remove_translators()
    lm._INSTANCE = None


def _build_main_window() -> MainWindow:
    """Build the main window through the GUI composition boundary."""
    dependencies = create_default_infrastructure_dependencies(translate_presets=str)
    return create_main_window(
        ShellDependencies(
            project_io_usecase=dependencies.project_io_usecase,
            atomic_data=dependencies.atomic_repository,
            preset_store=IdentifyPresetStore(dependencies.preset_store),
            optimize_model_addition_usecase=dependencies.optimize_model_addition_usecase,
        )
    )


def test_language_change_updates_settings_menu(qtbot, language_switcher: LanguageSwitcher) -> None:
    window = _build_main_window()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(window.isVisible)

    action_map = getattr(window, "action_map", None)
    if action_map is None:
        action_map = window.action_factory.get_all_actions() if window.action_factory else {}
    action = action_map.get(ShellActionId.LANGUAGE_SETTINGS)
    assert action is not None
    assert action.text() == "言語(&L)..."

    status_spy = QSignalSpy(window.status_message)
    language_spy = QSignalSpy(language_switcher.language_changed)

    language_switcher.set_language("en")
    qtbot.waitUntil(lambda: language_spy.count() >= 1)
    assert language_switcher.current_language == "en"

    assert action.text() == "&Language..."

    language_switcher.set_language("ja")
    qtbot.waitUntil(lambda: language_spy.count() >= 2)
    assert language_switcher.current_language == "ja"
    assert action.text() == "言語(&L)..."

    assert status_spy.count() == 0

    window.close()


@pytest.mark.parametrize("language", ["ja", "en"])
def test_analysis_overview_fits_real_800x600_window(
    qtbot, language_switcher: LanguageSwitcher, language: str
) -> None:
    """Real Fusion layout keeps spectrum/review/right minima with data controls visible."""
    language_switcher.set_language(language)
    window = _build_main_window()
    qtbot.addWidget(window)
    window.resize(800, 600)
    window.show()
    window.switch_mode(EditingMode.ANALYSIS)
    qtbot.waitUntil(lambda: window.isVisible())

    dock = window._require_dock_coordinator()
    workspace = dock.analysis_workspace
    assert workspace is not None
    assert window._layout_builder.side_panel_placeholder is not None
    assert window._layout_builder.side_panel_placeholder.minimumWidth() == 0
    assert dock.mode_panel is not None
    assert dock.mode_panel.minimumWidth() == 0
    assert workspace.right_stack.minimumWidth() == 220
    assert workspace.bottom_stack.minimumHeight() == 144
    assert window.view_stack is not None
    assert window.view_stack.minimumWidth() == 240
    assert window.view_stack.minimumHeight() == 240
    assert window.data_control_container is not None
    assert window.data_control_container.isVisible() is True

    window.close()
