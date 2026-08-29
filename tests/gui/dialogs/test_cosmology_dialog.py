"""Tests for the cosmology parameter dialog."""

from __future__ import annotations

import math
import shutil
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QLabel, QPushButton, QDoubleSpinBox
from pytestqt.qtbot import QtBot

from chappy.core.cosmology import PLANCK_2018, CosmologyParameters
from chappy.gui.dialogs.cosmology_dialog import CosmologyDialog
from chappy.i18n.qt_translator import QtTranslatorInstaller
from scripts.i18n_lrelease import run_lrelease
from scripts.i18n_lupdate import run_lupdate


@pytest.fixture
def isolated_settings(tmp_path: Path) -> Iterator[QSettings]:
    """Provide an isolated QSettings instance per test.

    Args:
        tmp_path: Temporary directory provided by pytest.

    Yields:
        Isolated settings object.
    """
    settings_dir = tmp_path / "settings"
    settings_dir.mkdir()
    # The (org, app) constructor resolves to the shared Windows registry, which
    # races with parallel test workers; an explicit ini file stays test-local.
    settings = QSettings(str(settings_dir / "cosmology_tests.ini"), QSettings.Format.IniFormat)
    settings.clear()
    yield settings
    settings.clear()


def _ensure_visible(dialog: CosmologyDialog, qtbot: QtBot) -> None:
    """Show the dialog and wait until Qt marks it visible.

    Args:
        dialog: Dialog under test.
        qtbot: pytest-qt bot used to manage the widget.
    """
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(dialog.isVisible, timeout=1000)


def _extract_spin(dialog: CosmologyDialog, object_name: str) -> QDoubleSpinBox:
    """Find a spinbox by object name.

    Args:
        dialog: Dialog under test.
        object_name: Qt object name to look up.

    Returns:
        Matching spinbox.
    """
    spin = dialog.findChild(QDoubleSpinBox, object_name)
    assert spin is not None, f"Missing spinbox {object_name}"
    return spin


def _extract_label(dialog: CosmologyDialog, object_name: str) -> QLabel:
    """Find a label by object name.

    Args:
        dialog: Dialog under test.
        object_name: Qt object name to look up.

    Returns:
        Matching label.
    """
    label = dialog.findChild(QLabel, object_name)
    assert label is not None, f"Missing label {object_name}"
    return label


def _click_button(dialog: CosmologyDialog, object_name: str) -> QPushButton:
    """Click a button by object name.

    Args:
        dialog: Dialog under test.
        object_name: Qt object name to look up.

    Returns:
        Clicked button.
    """
    button = dialog.findChild(QPushButton, object_name)
    assert button is not None, f"Missing button {object_name}"
    button.click()
    return button


def _settings_float(value: object) -> float:
    """Convert a QSettings value to float for assertions.

    Args:
        value: Raw settings value.

    Returns:
        Converted float value.
    """
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        return float(value)
    msg = f"Expected numeric settings value, got {type(value).__name__}"
    raise TypeError(msg)


def _write_cosmology_ja_ts(ts_path: Path) -> None:
    """Write a minimal Japanese TS catalog for CosmologyDialog.

    Args:
        ts_path: Output TS file path.
    """
    ts_path.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="ja_JP">
<context>
    <name>CosmologyDialog</name>
    <message>
        <source>Cosmology Parameters</source>
        <translation>宇宙論パラメータ</translation>
    </message>
    <message>
        <source>Set parameters for ΛCDM cosmology.
Ωk is derived as 1−Ωm−ΩΛ from H₀, Ωm, ΩΛ and used to compute comoving distance and lookback time.
</source>
        <translation>ΛCDM宇宙論の計算に用いるパラメータを設定します。
H₀, Ωm, ΩΛ から Ωk=1−Ωm−ΩΛ を導出し、共動距離とルックバックタイムの計算に使用します。
</translation>
    </message>
    <message>
        <source>Hubble Constant H₀</source>
        <translation>ハッブル定数 H₀</translation>
    </message>
    <message>
        <source>km/s/Mpc</source>
        <translation>km/s/Mpc</translation>
    </message>
    <message>
        <source>Matter Density Ωm</source>
        <translation>物質密度 Ωm</translation>
    </message>
    <message>
        <source>Dark Energy Density ΩΛ</source>
        <translation>ダークエネルギー密度 ΩΛ</translation>
    </message>
    <message>
        <source>(dimensionless)</source>
        <translation>（無次元）</translation>
    </message>
    <message>
        <source>67.4</source>
        <translation>67.4</translation>
    </message>
    <message>
        <source>Ωk is informational (non-flat ΛCDM allowed)</source>
        <translation>Ωkは情報表示のみ（非平坦ΛCDMを許容）</translation>
    </message>
    <message>
        <source>Derived: Ωk</source>
        <translation>導出: Ωk</translation>
    </message>
    <message>
        <source>flat</source>
        <translation>flat</translation>
    </message>
    <message>
        <source>Apply Planck2018</source>
        <translation>Planck2018 を適用</translation>
    </message>
    <message>
        <source>Cancel</source>
        <translation>キャンセル</translation>
    </message>
    <message>
        <source>OK</source>
        <translation>OK</translation>
    </message>
    <message>
        <source>Universe is within flat tolerance</source>
        <translation>平坦宇宙とみなせる範囲です</translation>
    </message>
    <message>
        <source>Applied Planck2018 defaults</source>
        <translation>Planck2018の既定値を適用しました</translation>
    </message>
    <message>
        <source>Applied cosmology parameters (H₀={H0}, Ωm={Om}, ΩΛ={Ol}, Ωk={Ok})</source>
        <translation>宇宙論パラメータを適用しました (H₀={H0}, Ωm={Om}, ΩΛ={Ol}, Ωk={Ok})</translation>
    </message>
    <message>
        <source>Please enter a valid number</source>
        <translation>有効な数値を入力してください</translation>
    </message>
    <message>
        <source>H₀ must be between 50.0 and 100.0 km/s/Mpc</source>
        <translation>H₀は 50.0～100.0 km/s/Mpc の範囲で入力してください</translation>
    </message>
    <message>
        <source>Ωm must be between 0.0 and 1.0</source>
        <translation>Ωmは 0.0～1.0 の範囲で入力してください</translation>
    </message>
    <message>
        <source>ΩΛ must be between 0.0 and 1.0</source>
        <translation>ΩΛは 0.0～1.0 の範囲で入力してください</translation>
    </message>
</context>
</TS>
""",
        encoding="utf-8",
    )


def _compile_cosmology_ja_qm(tmp_path: Path) -> Path:
    """Compile a test Japanese QM catalog for CosmologyDialog.

    Args:
        tmp_path: Temporary directory for generated catalogs.

    Returns:
        Directory containing ``chappy_ja.qm``.
    """
    if shutil.which("pyside6-lrelease") is None:
        pytest.skip("pyside6-lrelease is not available")

    catalog_root = tmp_path / "qt_catalogs"
    catalog_root.mkdir()
    ts_path = catalog_root / "chappy_ja.ts"
    qm_path = catalog_root / "chappy_ja.qm"
    _write_cosmology_ja_ts(ts_path)
    run_lrelease(ts_input=ts_path, qm_output=qm_path)
    return catalog_root


@pytest.fixture()
def qt_translator_installer(tmp_path: Path) -> Iterator[QtTranslatorInstaller]:
    """Provide a translator installer with a compiled test Japanese catalog.

    Args:
        tmp_path: Temporary directory for generated catalogs.

    Yields:
        Translator installer configured with the test catalog root.
    """
    catalog_root = _compile_cosmology_ja_qm(tmp_path)
    installer = QtTranslatorInstaller(
        translation_root=catalog_root, qt_translation_root=tmp_path / "missing_qt_catalogs"
    )
    yield installer
    installer.remove_translators()


def test_dialog_loads_existing_settings(qtbot: QtBot, isolated_settings: QSettings) -> None:
    """Load persisted cosmology values into spinboxes."""
    isolated_settings.setValue("settings/cosmology/H0", 72.5)
    isolated_settings.setValue("settings/cosmology/Om", 0.333)
    isolated_settings.setValue("settings/cosmology/Ol", 0.611)

    dialog = CosmologyDialog(None, settings=isolated_settings)
    _ensure_visible(dialog, qtbot)

    params = dialog.parameters
    assert math.isclose(params.h0, 72.5, rel_tol=0.0, abs_tol=1e-3)
    assert math.isclose(params.omega_m, 0.333, rel_tol=0.0, abs_tol=1e-4)
    assert math.isclose(params.omega_lambda, 0.611, rel_tol=0.0, abs_tol=1e-4)


def test_invalid_h0_disables_ok(qtbot: QtBot, isolated_settings: QSettings) -> None:
    """Disable OK and show a translated range error for invalid H₀."""
    dialog = CosmologyDialog(None, settings=isolated_settings)
    _ensure_visible(dialog, qtbot)

    spin_h0 = _extract_spin(dialog, "spin_h0")
    line_edit = spin_h0.lineEdit()
    line_edit.setText("30")

    ok_button = dialog.findChild(QPushButton, "okButton")
    assert ok_button is not None
    qtbot.waitUntil(lambda: not ok_button.isEnabled())

    error_label = _extract_label(dialog, "error_h0")
    assert error_label.isVisible()
    assert "H₀" in error_label.text()


def test_defaults_button_applies_planck(qtbot: QtBot, isolated_settings: QSettings) -> None:
    """Apply Planck 2018 defaults and emit the derived values."""
    status_messages: list[tuple[str, int, str]] = []

    def _capture_status(message: str, timeout_ms: int, level: str) -> None:
        """Record emitted status messages.

        Args:
            message: Status message text.
            timeout_ms: Display duration in milliseconds.
            level: Visual status level.
        """
        status_messages.append((message, timeout_ms, level))

    dialog = CosmologyDialog(None, settings=isolated_settings, status_callback=_capture_status)
    _ensure_visible(dialog, qtbot)

    _click_button(dialog, "defaultsButton")

    assert math.isclose(dialog.parameters.h0, PLANCK_2018.h0, rel_tol=0.0, abs_tol=1e-6)
    assert math.isclose(dialog.parameters.omega_m, PLANCK_2018.omega_m, rel_tol=0.0, abs_tol=1e-6)
    assert math.isclose(
        dialog.parameters.omega_lambda, PLANCK_2018.omega_lambda, rel_tol=0.0, abs_tol=1e-6
    )
    assert math.isclose(dialog.parameters.omega_k, PLANCK_2018.omega_k, rel_tol=0.0, abs_tol=1e-6)
    assert status_messages[-1] == ("Applied Planck2018 defaults", 3000, "success")


def test_ok_persists_parameters(qtbot: QtBot, isolated_settings: QSettings) -> None:
    """Persist edited parameters and emit an applied status message."""
    status_messages: list[tuple[str, int, str]] = []

    def _capture_status(message: str, timeout_ms: int, level: str) -> None:
        """Record emitted status messages.

        Args:
            message: Status message text.
            timeout_ms: Display duration in milliseconds.
            level: Visual status level.
        """
        status_messages.append((message, timeout_ms, level))

    dialog = CosmologyDialog(None, settings=isolated_settings, status_callback=_capture_status)
    _ensure_visible(dialog, qtbot)

    _extract_spin(dialog, "spin_h0").setValue(70.1)
    _extract_spin(dialog, "spin_omega_m").setValue(0.321)
    _extract_spin(dialog, "spin_omega_lambda").setValue(0.640)

    _click_button(dialog, "okButton")

    assert math.isclose(dialog.parameters.h0, 70.1, rel_tol=0.0, abs_tol=1e-6)
    assert math.isclose(dialog.parameters.omega_m, 0.321, rel_tol=0.0, abs_tol=1e-6)
    assert math.isclose(dialog.parameters.omega_lambda, 0.640, rel_tol=0.0, abs_tol=1e-6)
    assert math.isclose(dialog.parameters.omega_k, 1.0 - 0.321 - 0.640, rel_tol=0.0, abs_tol=1e-6)

    stored = CosmologyParameters(
        h0=_settings_float(isolated_settings.value("settings/cosmology/H0", 0.0)),
        omega_m=_settings_float(isolated_settings.value("settings/cosmology/Om", 0.0)),
        omega_lambda=_settings_float(isolated_settings.value("settings/cosmology/Ol", 0.0)),
    )
    assert math.isclose(stored.h0, 70.1, rel_tol=0.0, abs_tol=1e-6)
    assert math.isclose(stored.omega_m, 0.321, rel_tol=0.0, abs_tol=1e-6)
    assert math.isclose(stored.omega_lambda, 0.640, rel_tol=0.0, abs_tol=1e-6)
    assert status_messages[-1] == (
        "Applied cosmology parameters (H₀=70.1, Ωm=0.321, ΩΛ=0.640, Ωk=0.039)",
        3000,
        "success",
    )


def test_ok_emits_parameters_applied(qtbot: QtBot, isolated_settings: QSettings) -> None:
    """Emit the applied signal once persistence succeeds on OK."""
    dialog = CosmologyDialog(None, settings=isolated_settings)
    _ensure_visible(dialog, qtbot)

    with qtbot.waitSignal(dialog.parameters_applied, timeout=1000):
        _click_button(dialog, "okButton")


def test_japanese_translator_updates_existing_dialog(
    qtbot: QtBot, isolated_settings: QSettings, qt_translator_installer: QtTranslatorInstaller
) -> None:
    """Retranslate an already visible CosmologyDialog with a Qt catalog."""
    status_messages: list[tuple[str, int, str]] = []

    def _capture_status(message: str, timeout_ms: int, level: str) -> None:
        """Record emitted status messages.

        Args:
            message: Status message text.
            timeout_ms: Display duration in milliseconds.
            level: Visual status level.
        """
        status_messages.append((message, timeout_ms, level))

    dialog = CosmologyDialog(None, settings=isolated_settings, status_callback=_capture_status)
    _ensure_visible(dialog, qtbot)

    assert dialog.windowTitle() == "Cosmology Parameters"
    assert _extract_label(dialog, "label_h0").text() == "Hubble Constant H₀"
    assert _extract_label(dialog, "unit_omega_m").text() == "(dimensionless)"
    assert dialog._defaults_button.text() == "Apply Planck2018"

    spin_h0 = _extract_spin(dialog, "spin_h0")
    line_edit = spin_h0.lineEdit()
    line_edit.setText("30")
    ok_button = dialog.findChild(QPushButton, "okButton")
    assert ok_button is not None
    qtbot.waitUntil(lambda: not ok_button.isEnabled(), timeout=1000)

    state = qt_translator_installer.install_language("ja")
    assert state.app_translator_loaded
    qtbot.waitUntil(lambda: dialog.windowTitle() == "宇宙論パラメータ", timeout=1000)

    description = dialog.findChild(QLabel, "cosmologyDescription")
    assert description is not None
    assert description.text() == (
        "ΛCDM宇宙論の計算に用いるパラメータを設定します。\n"
        "H₀, Ωm, ΩΛ から Ωk=1−Ωm−ΩΛ を導出し、共動距離とルックバックタイムの計算に使用します。\n"
    )
    assert _extract_label(dialog, "label_h0").text() == "ハッブル定数 H₀"
    assert _extract_label(dialog, "label_omega_m").text() == "物質密度 Ωm"
    assert _extract_label(dialog, "label_omega_lambda").text() == "ダークエネルギー密度 ΩΛ"
    assert _extract_label(dialog, "unit_h0").text() == "km/s/Mpc"
    assert _extract_label(dialog, "unit_omega_m").text() == "（無次元）"
    assert dialog._omega_k_label is not None
    assert dialog._omega_k_label.text() == "導出: Ωk"
    assert dialog._omega_k_info_icon is not None
    assert dialog._omega_k_info_icon.toolTip() == "Ωkは情報表示のみ（非平坦ΛCDMを許容）"
    assert dialog._flat_badge.text() == "flat"
    assert dialog._flat_badge.accessibleDescription() == "平坦宇宙とみなせる範囲です"
    assert dialog._defaults_button.text() == "Planck2018 を適用"
    assert dialog._cancel_button.text() == "キャンセル"
    assert dialog._ok_button.text() == "OK"
    assert spin_h0.lineEdit().placeholderText() == "67.4"

    error_label = _extract_label(dialog, "error_h0")
    assert error_label.text() == "H₀は 50.0～100.0 km/s/Mpc の範囲で入力してください"
    assert spin_h0.accessibleDescription() == error_label.text()

    line_edit.setText("67.4")
    qtbot.waitUntil(ok_button.isEnabled, timeout=1000)
    _click_button(dialog, "defaultsButton")
    assert status_messages[-1] == ("Planck2018の既定値を適用しました", 3000, "success")

    qt_translator_installer.install_language("en")
    qtbot.waitUntil(lambda: dialog.windowTitle() == "Cosmology Parameters", timeout=1000)
    assert _extract_label(dialog, "label_h0").text() == "Hubble Constant H₀"
    assert _extract_label(dialog, "unit_omega_m").text() == "(dimensionless)"
    assert dialog._defaults_button.text() == "Apply Planck2018"


def test_lupdate_extracts_cosmology_dialog_sources(tmp_path: Path) -> None:
    """Verify lupdate can extract the migrated CosmologyDialog sources.

    Args:
        tmp_path: Temporary directory for generated TS output.
    """
    if shutil.which("pyside6-lupdate") is None:
        pytest.skip("pyside6-lupdate is not available")

    ts_path = tmp_path / "chappy_ja.ts"
    run_lupdate(
        source_dirs=[Path("src/chappy/gui/dialogs/cosmology_dialog.py")], ts_output=ts_path
    )

    root = ET.parse(ts_path).getroot()
    sources = {
        source.text
        for source in root.findall("./context/message/source")
        if source.text is not None
    }
    expected_sources = {
        "Cosmology Parameters",
        (
            "Set parameters for ΛCDM cosmology.\n"
            "Ωk is derived as 1−Ωm−ΩΛ from H₀, Ωm, ΩΛ and used to compute "
            "comoving distance and lookback time.\n"
        ),
        "Hubble Constant H₀",
        "km/s/Mpc",
        "Matter Density Ωm",
        "Dark Energy Density ΩΛ",
        "(dimensionless)",
        "67.4",
        "Ωk is informational (non-flat ΛCDM allowed)",
        "Derived: Ωk",
        "flat",
        "Apply Planck2018",
        "Cancel",
        "OK",
        "Universe is within flat tolerance",
        "Applied Planck2018 defaults",
        "Applied cosmology parameters (H₀={H0}, Ωm={Om}, ΩΛ={Ol}, Ωk={Ok})",
        "Please enter a valid number",
        "H₀ must be between 50.0 and 100.0 km/s/Mpc",
        "Ωm must be between 0.0 and 1.0",
        "ΩΛ must be between 0.0 and 1.0",
    }
    assert expected_sources <= sources
    assert not any("GUI__" in source for source in sources)
