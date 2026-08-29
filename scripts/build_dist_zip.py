#!/usr/bin/env -S uv run python
# /// script
# requires-python = "~=3.13.0"
# ///
"""Generate release zip file."""

from __future__ import annotations

import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = ROOT / "pyproject.toml"
DIST_DIR = ROOT / "dist"
INCLUDE_PATHS = [
    ROOT / "pyproject.toml",
    ROOT / "uv.lock",
    ROOT / "src",
    ROOT / "INSTALL.md",
    ROOT / "INSTALL.en.md",
    ROOT / "spectral_database" / "db_file" / "spectral_lines.csv",
    ROOT / "sample_data",
    ROOT / "docs" / "user_manual" / "dist" / "html_ja",
    ROOT / "docs" / "user_manual" / "dist" / "html_en",
    ROOT / ".python-version",
    ROOT / "scripts" / "run.sh",
    ROOT / "scripts" / "run.cmd",
    ROOT / "scripts" / "run.command",
    ROOT / "scripts" / "install-desktop.sh",
]


def get_project_metadata() -> tuple[str, str]:
    """Read the project name and version from pyproject.toml.

    Returns:
        プロジェクト名とバージョン文字列のタプル。
    """
    with PYPROJECT_PATH.open("rb") as file_handle:
        data = tomllib.load(file_handle)

    project = data.get("project")
    if not isinstance(project, dict):
        msg = "[project] table is missing in pyproject.toml."
        raise SystemExit(msg)

    name = project.get("name")
    version = project.get("version")
    if not name:
        msg = "project.name is missing in pyproject.toml."
        raise SystemExit(msg)
    if not version:
        msg = "project.version is missing in pyproject.toml."
        raise SystemExit(msg)

    return str(name), str(version)


def ensure_include_paths() -> None:
    """Verify that every required path for the archive exists.

    Raises:
        SystemExit: 必須パスが存在しない場合。
    """
    missing = [path for path in INCLUDE_PATHS if not path.exists()]
    if missing:
        missing_list = ", ".join(str(path.relative_to(ROOT)) for path in missing)
        msg = f"Required paths are missing: {missing_list}"
        raise SystemExit(msg)


def should_skip(path: Path) -> bool:
    """Decide whether a filesystem entry should be omitted from the archive.

    Args:
        path: 確認するファイルまたはディレクトリのパス。

    Returns:
        キャッシュ生成物などを除外する場合はTrueを返す。
    """
    parts = set(path.parts)
    return "__pycache__" in parts or path.suffix == ".pyc"


def add_path(zip_file: zipfile.ZipFile, path: Path) -> None:
    """Add a file or directory tree to the distribution archive.

    Args:
        zip_file: 出力アーカイブのZipFileハンドル。
        path: 追加対象のパス。
    """
    if path.is_dir():
        for item in path.rglob("*"):
            if should_skip(item):
                continue
            if item.is_dir():
                continue
            arcname = item.relative_to(ROOT)
            zip_file.write(item, arcname.as_posix())
    else:
        if should_skip(path):
            return
        arcname = path.relative_to(ROOT)
        zip_file.write(path, arcname.as_posix())


def build_zip() -> Path:
    """Create the distributable ZIP archive under dist/.

    Returns:
        生成されたZIPファイルへのパス。
    """
    app_name, version = get_project_metadata()
    ensure_include_paths()
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    archive_name = f"{app_name}-{version}.zip"
    archive_path = DIST_DIR / archive_name

    with zipfile.ZipFile(
        archive_path, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as zip_file:
        for path in INCLUDE_PATHS:
            add_path(zip_file, path)

    return archive_path


def main() -> None:
    """CLI entry point that builds the release archive."""
    build_zip()


if __name__ == "__main__":
    main()
