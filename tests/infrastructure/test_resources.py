"""Tests for runtime data path resolution adapters."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

import chappy.infrastructure.resources as resources


def _reloaded_resources() -> ModuleType:
    """Reload the module so environment-sensitive path caches are rebuilt.

    Returns:
        Reloaded resource path module.
    """
    return importlib.reload(resources)


def test_runtime_dirs_start_with_env_override(monkeypatch, tmp_path) -> None:
    """Ensure `CHAPPY_DATA_DIR` override is prioritised."""

    custom_dir = tmp_path / "custom"
    custom_dir.mkdir()
    marker_name = "marker.txt"
    env_marker = custom_dir / marker_name
    env_marker.write_text("env", encoding="utf-8")

    monkeypatch.setenv("CHAPPY_DATA_DIR", str(custom_dir))
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    resources_module = _reloaded_resources()
    resolved = resources_module.resolve_data_path(marker_name)

    assert resolved == env_marker.resolve()


def test_runtime_dirs_include_module_root_when_not_frozen(monkeypatch) -> None:
    """Fallback to the project root when running from source."""

    monkeypatch.delenv("CHAPPY_DATA_DIR", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)

    expected_root = Path(resources.__file__).resolve().parents[3]
    expected_file = expected_root / "pyproject.toml"

    resources_module = _reloaded_resources()
    resolved = resources_module.resolve_data_path("pyproject.toml")

    assert resolved == expected_file.resolve()


def test_runtime_dirs_include_frozen_bundle(monkeypatch, tmp_path) -> None:
    """Packaged executables expose their own directories as search roots."""

    exe_dir = tmp_path / "bundle" / "MacOS"
    exe_dir.mkdir(parents=True)
    staging_dir = tmp_path / "bundle" / "staging"
    staging_dir.mkdir()
    exe_marker = exe_dir / "exe-marker.dat"
    staging_marker = staging_dir / "staging-marker.dat"
    exe_marker.write_text("exe", encoding="utf-8")
    staging_marker.write_text("staging", encoding="utf-8")

    monkeypatch.delenv("CHAPPY_DATA_DIR", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "Chappy"), raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(staging_dir), raising=False)

    resources_module = _reloaded_resources()

    assert resources_module.resolve_data_path(exe_marker.name) == exe_marker.resolve()
    assert resources_module.resolve_data_path(staging_marker.name) == staging_marker.resolve()


def test_runtime_resource_resolver_raises_for_missing_resource(tmp_path) -> None:
    """Runtime resolver fails fast for missing resources."""
    resolver = resources.RuntimeResourcePathResolver()
    missing = tmp_path / "missing.txt"

    try:
        resolver.resolve_data_path(missing)
    except FileNotFoundError as exc:
        assert str(missing) in str(exc)
    else:
        raise AssertionError("Expected missing resource to raise FileNotFoundError")
