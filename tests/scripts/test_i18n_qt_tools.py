"""Tests for PySide6 Qt translation tool wrappers."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

import pytest


def _import_script(module_name: str, script_name: str) -> ModuleType:
    """Import a script module from the repository scripts directory.

    Args:
        module_name: Temporary module name used for import isolation.
        script_name: Script file name.

    Returns:
        Loaded script module.
    """
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    module_path = scripts_dir / script_name
    loader = importlib.machinery.SourceFileLoader(module_name, str(module_path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None:
        raise RuntimeError(f"Failed to load module spec for {script_name}")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(scripts_dir))
    sys.modules[loader.name] = module
    try:
        loader.exec_module(module)
    finally:
        sys.modules.pop(loader.name, None)
        sys.path.remove(str(scripts_dir))
    return module


def _write_safe_pattern_source(path: Path) -> None:
    """Write a minimal Python source file containing lupdate-safe patterns.

    Args:
        path: Output Python file path.
    """
    path.write_text(
        "\n".join(
            [
                "from PySide6.QtCore import QCoreApplication",
                "from PySide6.QtWidgets import QWidget",
                "",
                "class ExampleWidget(QWidget):",
                "    def refresh(self) -> None:",
                '        self.setWindowTitle(self.tr("Example"))',
                '        self.setToolTip(self.tr("Failed to load file: {path}"))',
                ('        self.setStatusTip(QCoreApplication.translate("MainWindow", "Open"))'),
                '        self.setWhatsThis(self.tr("%n selected item(s)", None, 2))',
            ]
        ),
        encoding="utf-8",
    )


def test_lupdate_command_and_output_directory_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify lupdate command construction and output directory creation.

    Args:
        tmp_path: Temporary directory provided by pytest.
        monkeypatch: Pytest monkeypatch fixture.
    """
    lupdate = _import_script("chappy_i18n_lupdate", "i18n_lupdate.py")
    source_file = tmp_path / "src" / "example.py"
    source_file.parent.mkdir()
    _write_safe_pattern_source(source_file)
    ts_output = tmp_path / "translations" / "ja" / "chappy_ja.ts"
    calls: list[list[str]] = []

    def fake_run(
        command: Sequence[str], *, check: bool, capture_output: bool, text: bool
    ) -> subprocess.CompletedProcess[str]:
        """Record the subprocess command instead of running it.

        Args:
            command: Command arguments.
            check: Whether subprocess should raise on failure.
            capture_output: Whether output should be captured.
            text: Whether output should be decoded as text.

        Returns:
            Successful subprocess result.
        """
        calls.append(list(command))
        assert check is True
        assert capture_output is True
        assert text is True
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(lupdate.subprocess, "run", fake_run)

    result = lupdate.run_lupdate(
        source_dirs=[source_file], ts_output=ts_output, tool="pyside6-lupdate"
    )

    assert result.returncode == 0
    assert ts_output.parent.is_dir()
    assert calls == [
        ["pyside6-lupdate", str(source_file), "-extensions", "py", "-ts", str(ts_output)]
    ]
    assert lupdate.build_lupdate_command(source_dirs=[source_file], ts_output=ts_output) == [
        "pyside6-lupdate",
        str(source_file),
        "-extensions",
        "py",
        "-ts",
        str(ts_output),
    ]
    assert lupdate.build_lupdate_command(
        source_dirs=[source_file], ts_output=ts_output, extensions="py,ui"
    ) == ["pyside6-lupdate", str(source_file), "-extensions", "py,ui", "-ts", str(ts_output)]


def test_lupdate_directory_input_expands_to_matching_sources(tmp_path: Path) -> None:
    """Verify directory input is expanded before invoking lupdate.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """
    lupdate = _import_script("chappy_i18n_lupdate_directory", "i18n_lupdate.py")
    source_dir = tmp_path / "src"
    nested_dir = source_dir / "nested"
    nested_dir.mkdir(parents=True)
    source_file = source_dir / "example.py"
    nested_source_file = nested_dir / "example_nested.py"
    ignored_file = source_dir / "ignored.txt"
    _write_safe_pattern_source(source_file)
    _write_safe_pattern_source(nested_source_file)
    ignored_file.write_text("self.tr('Ignored')", encoding="utf-8")
    ts_output = tmp_path / "translations" / "chappy_ja.ts"

    assert lupdate.build_lupdate_command(source_dirs=[source_dir], ts_output=ts_output) == [
        "pyside6-lupdate",
        str(source_file),
        str(nested_source_file),
        "-extensions",
        "py",
        "-ts",
        str(ts_output),
    ]


def test_lrelease_command_and_output_directory_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify lrelease command construction and output directory creation.

    Args:
        tmp_path: Temporary directory provided by pytest.
        monkeypatch: Pytest monkeypatch fixture.
    """
    lrelease = _import_script("chappy_i18n_lrelease", "i18n_lrelease.py")
    ts_input = tmp_path / "translations" / "ja" / "chappy_ja.ts"
    ts_input.parent.mkdir(parents=True)
    ts_input.write_text('<TS version="2.1" language="ja_JP" />', encoding="utf-8")
    qm_output = tmp_path / "build" / "i18n" / "chappy_ja.qm"
    calls: list[list[str]] = []

    def fake_run(
        command: Sequence[str], *, check: bool, capture_output: bool, text: bool
    ) -> subprocess.CompletedProcess[str]:
        """Record the subprocess command instead of running it.

        Args:
            command: Command arguments.
            check: Whether subprocess should raise on failure.
            capture_output: Whether output should be captured.
            text: Whether output should be decoded as text.

        Returns:
            Successful subprocess result.
        """
        calls.append(list(command))
        assert check is True
        assert capture_output is True
        assert text is True
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(lrelease.subprocess, "run", fake_run)

    result = lrelease.run_lrelease(ts_input=ts_input, qm_output=qm_output, tool="pyside6-lrelease")

    assert result.returncode == 0
    assert qm_output.parent.is_dir()
    assert calls == [["pyside6-lrelease", str(ts_input), "-qm", str(qm_output)]]
    assert lrelease.build_lrelease_command(ts_input=ts_input, qm_output=qm_output) == [
        "pyside6-lrelease",
        str(ts_input),
        "-qm",
        str(qm_output),
    ]


def test_wrapper_main_returns_subprocess_failure_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verify wrapper CLI reports subprocess failures without traceback.

    Args:
        tmp_path: Temporary directory provided by pytest.
        monkeypatch: Pytest monkeypatch fixture.
        capsys: Pytest capture fixture.
    """
    lupdate = _import_script("chappy_i18n_lupdate_failure", "i18n_lupdate.py")
    source_file = tmp_path / "example.py"
    source_file.write_text("class Example: pass", encoding="utf-8")
    ts_output = tmp_path / "out" / "chappy_ja.ts"

    def fake_run(
        command: Sequence[str], *, check: bool, capture_output: bool, text: bool
    ) -> subprocess.CompletedProcess[str]:
        """Raise a deterministic subprocess failure.

        Args:
            command: Command arguments.
            check: Whether subprocess should raise on failure.
            capture_output: Whether output should be captured.
            text: Whether output should be decoded as text.

        Raises:
            subprocess.CalledProcessError: Always raised for this test.
        """
        raise subprocess.CalledProcessError(
            returncode=7, cmd=list(command), output="stdout message\n", stderr="stderr message\n"
        )

    monkeypatch.setattr(lupdate.subprocess, "run", fake_run)

    exit_code = lupdate.main(
        [str(source_file), "--ts-output", str(ts_output), "--tool", "bad-lupdate"]
    )
    captured = capsys.readouterr()

    assert exit_code == 7
    assert "stdout message" in captured.out
    assert "stderr message" in captured.err


def test_qt_check_reports_finished_catalog(tmp_path: Path) -> None:
    """Verify Qt catalog validation accepts completed translations.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """
    qt_check = _import_script("chappy_i18n_qt_check", "i18n_qt_check.py")
    ts_path = tmp_path / "chappy_ja.ts"
    ts_path.write_text(
        "\n".join(
            [
                '<?xml version="1.0" encoding="utf-8"?>',
                '<TS version="2.1" language="ja_JP">',
                "<context>",
                "<name>ExampleWidget</name>",
                "<message>",
                "<source>Open</source>",
                "<translation>開く</translation>",
                "</message>",
                "</context>",
                "</TS>",
            ]
        ),
        encoding="utf-8",
    )

    report, errors = qt_check.validate_catalog_translations(ts_path)

    assert report.messages == 1
    assert report.unfinished == 0
    assert report.empty == 0
    assert report.obsolete == 0
    assert errors == []


def test_qt_check_flags_unfinished_empty_and_obsolete_messages(tmp_path: Path) -> None:
    """Verify Qt catalog validation rejects incomplete translations.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """
    qt_check = _import_script("chappy_i18n_qt_check_incomplete", "i18n_qt_check.py")
    ts_path = tmp_path / "chappy_ja.ts"
    ts_path.write_text(
        "\n".join(
            [
                '<?xml version="1.0" encoding="utf-8"?>',
                '<TS version="2.1" language="ja_JP">',
                "<context>",
                "<name>ExampleWidget</name>",
                "<message>",
                "<source>Open</source>",
                '<translation type="unfinished"></translation>',
                "</message>",
                "<message>",
                "<source>Close</source>",
                '<translation type="obsolete">閉じる</translation>',
                "</message>",
                "</context>",
                "</TS>",
            ]
        ),
        encoding="utf-8",
    )

    report, errors = qt_check.validate_catalog_translations(ts_path)

    assert report.messages == 2
    assert report.unfinished == 1
    assert report.empty == 1
    assert report.obsolete == 1
    assert errors == [
        "unfinished translation: ExampleWidget: Open",
        "empty translation: ExampleWidget: Open",
        "obsolete translation remains: ExampleWidget: Close",
    ]


def test_qt_check_compares_extracted_sources(tmp_path: Path) -> None:
    """Verify Qt catalog source comparison reports missing and stale messages.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """
    if shutil.which("pyside6-lupdate") is None:
        pytest.skip("pyside6-lupdate is not available")

    qt_check = _import_script("chappy_i18n_qt_check_compare", "i18n_qt_check.py")
    source_file = tmp_path / "example.py"
    _write_safe_pattern_source(source_file)
    committed_ts = tmp_path / "committed.ts"
    committed_ts.write_text(
        "\n".join(
            [
                '<?xml version="1.0" encoding="utf-8"?>',
                '<TS version="2.1" language="ja_JP">',
                "<context>",
                "<name>ExampleWidget</name>",
                "<message>",
                "<source>Example</source>",
                "<translation>例</translation>",
                "</message>",
                "<message>",
                "<source>Removed</source>",
                "<translation>削除済み</translation>",
                "</message>",
                "</context>",
                "</TS>",
            ]
        ),
        encoding="utf-8",
    )

    errors = qt_check.compare_catalog_sources(
        source_dirs=[source_file], ts_input=committed_ts, extensions="py"
    )

    assert "stale TS entry not found in sources: ExampleWidget: Removed" in errors
    assert (
        "missing TS entry for extracted source: ExampleWidget: Failed to load file: {path}"
        in errors
    )


def test_qt_check_flags_legacy_runtime_references_and_yaml(tmp_path: Path) -> None:
    """Verify Qt catalog validation rejects legacy runtime resources.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """
    qt_check = _import_script("chappy_i18n_qt_check_legacy", "i18n_qt_check.py")
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    source_file = source_dir / "sample.py"
    source_file.write_text("from chappy.i18n.keys import GuiKey\n", encoding="utf-8")
    locales_dir = tmp_path / "i18n"
    (locales_dir / "ja" / "doc").mkdir(parents=True)
    (locales_dir / "ja" / "doc" / "manual.yaml").write_text(
        "DOC__TITLE: Manual\n", encoding="utf-8"
    )
    (locales_dir / "ja" / "gui").mkdir(parents=True)
    legacy_yaml = locales_dir / "ja" / "gui" / "button.yaml"
    legacy_yaml.write_text("GUI__OK: OK\n", encoding="utf-8")

    reference_errors = qt_check.collect_legacy_runtime_references([source_dir])
    yaml_errors = qt_check.collect_legacy_gui_yaml(locales_dir)

    assert reference_errors == [f"legacy runtime i18n token 'GuiKey' found in {source_file}"]
    assert yaml_errors == [f"legacy GUI YAML remains: {legacy_yaml}"]


@pytest.mark.skipif(shutil.which("pyside6-lupdate") is None, reason="pyside6-lupdate not found")
def test_lupdate_smoke_with_real_tool_when_available(tmp_path: Path) -> None:
    """Smoke test real pyside6-lupdate when the executable is available.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """
    lupdate = _import_script("chappy_i18n_lupdate_smoke", "i18n_lupdate.py")
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    source_file = source_dir / "example.py"
    _write_safe_pattern_source(source_file)
    ts_output = tmp_path / "i18n" / "chappy_ja.ts"

    lupdate.run_lupdate(source_dirs=[source_file], ts_output=ts_output)

    file_ts_text = ts_output.read_text(encoding="utf-8")
    assert "Example" in file_ts_text
    assert "Failed to load file: {path}" in file_ts_text
    assert "Open" in file_ts_text
    assert "%n selected item(s)" in file_ts_text

    directory_ts_output = tmp_path / "i18n" / "chappy_ja_from_directory.ts"
    lupdate.run_lupdate(source_dirs=[source_dir], ts_output=directory_ts_output)

    directory_ts_text = directory_ts_output.read_text(encoding="utf-8")
    assert "Example" in directory_ts_text
    assert "Failed to load file: {path}" in directory_ts_text
    assert "Open" in directory_ts_text
    assert "%n selected item(s)" in directory_ts_text


@pytest.mark.skipif(shutil.which("pyside6-lrelease") is None, reason="pyside6-lrelease not found")
def test_lrelease_smoke_with_real_tool_when_available(tmp_path: Path) -> None:
    """Smoke test real pyside6-lrelease when the executable is available.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """
    lrelease = _import_script("chappy_i18n_lrelease_smoke", "i18n_lrelease.py")
    ts_input = tmp_path / "chappy_ja.ts"
    ts_input.write_text(
        "\n".join(
            [
                '<?xml version="1.0" encoding="utf-8"?>',
                "<!DOCTYPE TS>",
                '<TS version="2.1" language="ja_JP">',
                "<context>",
                "<name>ExampleWidget</name>",
                "<message>",
                "<source>Example</source>",
                "<translation>例</translation>",
                "</message>",
                "</context>",
                "</TS>",
            ]
        ),
        encoding="utf-8",
    )
    qm_output = tmp_path / "qm" / "chappy_ja.qm"

    lrelease.run_lrelease(ts_input=ts_input, qm_output=qm_output)

    assert qm_output.is_file()
    assert qm_output.stat().st_size > 0
