"""Tests for the find_unused_code analyzer helpers."""

from __future__ import annotations

from pathlib import Path
import sys

import textwrap

import pytest


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from scripts.find_unused_code import CodeAnalyzer


@pytest.fixture(autouse=True)
def disable_test_file_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent the analyzer from skipping files located in temporary test paths."""

    def _no_skip(self: CodeAnalyzer, symbol) -> bool:  # type: ignore[override]
        if symbol.is_dunder:
            return True
        if symbol.name.startswith("test_"):
            return True
        skip_names = {"main", "setUp", "tearDown", "__all__", "logger"}
        return symbol.name in skip_names

    monkeypatch.setattr(CodeAnalyzer, "_should_skip_symbol", _no_skip, raising=False)


def _write_module(path: Path, content: str) -> Path:
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


def test_imported_symbol_without_usage_is_reported(tmp_path: Path) -> None:
    module_dir = tmp_path / "package"
    module_dir.mkdir()

    defined_module = _write_module(
        module_dir / "defined_module.py",
        """
        def unused_function():
            pass
        """,
    )

    _write_module(
        module_dir / "consumer.py",
        """
        from defined_module import unused_function
        """,
    )

    analyzer = CodeAnalyzer()
    analyzer.analyze_file(defined_module)
    analyzer.analyze_file(module_dir / "consumer.py")

    unused = analyzer.find_unused_symbols()
    unused_function_names = {symbol.name for symbol in unused["functions"]}
    assert "unused_function" in unused_function_names


def test_imported_symbol_with_usage_is_not_reported(tmp_path: Path) -> None:
    module_dir = tmp_path / "package"
    module_dir.mkdir()

    defined_module = _write_module(
        module_dir / "defined_module.py",
        """
        def used_function():
            pass
        """,
    )

    _write_module(
        module_dir / "consumer.py",
        """
        from defined_module import used_function as alias

        alias()
        """,
    )

    analyzer = CodeAnalyzer()
    analyzer.analyze_file(defined_module)
    analyzer.analyze_file(module_dir / "consumer.py")

    unused = analyzer.find_unused_symbols()
    used_function_names = {symbol.name for symbol in unused["functions"]}
    assert "used_function" not in used_function_names


def test_import_alias_counts_as_reference(tmp_path: Path) -> None:
    module_dir = tmp_path / "alias_usage"
    module_dir.mkdir()

    _write_module(
        module_dir / "module_a.py",
        """
        class MyClass:
            pass
        """,
    )

    _write_module(
        module_dir / "module_b.py",
        """
        from module_a import MyClass as Renamed

        print(Renamed)
        """,
    )

    analyzer = CodeAnalyzer()
    analyzer.analyze_directory(module_dir)

    unused = analyzer.find_unused_symbols()
    unused_class_names = {symbol.name for symbol in unused["classes"]}
    assert "MyClass" not in unused_class_names
