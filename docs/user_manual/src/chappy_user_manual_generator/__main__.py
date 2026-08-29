"""Command line entry point for UI documentation exports."""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import shutil
import subprocess
import tomllib
from importlib import metadata as importlib_metadata
from pathlib import Path

from PySide6.QtWidgets import QApplication

from chappy.gui.application_font import (
    FontConfigurationError,
    configure_application_font,
    configure_offscreen_font_environment,
)
from chappy.i18n import get_language_switcher
from chappy_user_manual_generator.exporter import ensure_high_dpi_mode
from chappy_user_manual_generator.pipeline import RuntimeOptions, run_manifest
from chappy_user_manual_generator.profiles import available_profiles, load_profile
from chappy_user_manual_generator.translations import install_language as install_manual_language

logger = logging.getLogger(__name__)


def _project_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").exists():
            return candidate
    return Path.cwd()


def _get_env_flag(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _resolve_package_version() -> str:
    with contextlib.suppress(importlib_metadata.PackageNotFoundError):
        return importlib_metadata.version("chappy")

    with contextlib.suppress(OSError, tomllib.TOMLDecodeError):
        with (_project_root() / "pyproject.toml").open("rb") as fp:
            data = tomllib.load(fp)
        project = data.get("project", {})
        version = project.get("version")
        if isinstance(version, str) and version:
            return version
    return "0.0.0"


def _resolve_commit_id() -> str:
    git_path = shutil.which("git")
    if git_path is None:
        return ""

    try:
        result = subprocess.run(
            [git_path, "rev-parse", "--short=8", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            cwd=_project_root(),
        )
    except (OSError, ValueError):
        return ""

    commit = (result.stdout or "").strip()
    return commit[:8] if commit else ""


def _default_version_label() -> str:
    base_version = _resolve_package_version()
    commit = _resolve_commit_id()
    if commit:
        return f"{base_version} ({commit})"
    return base_version


def _derive_html_out_dir(markdown_dir: Path) -> Path:
    name = markdown_dir.name
    candidate = name.replace("markdown", "html") if "markdown" in name else f"{name}_html"
    return markdown_dir.parent / candidate


def parse_args() -> argparse.Namespace:
    """Parse command-line options for the user manual generator.

    Returns:
        パーサーが解釈した実行時オプション。
    """
    parser = argparse.ArgumentParser(
        description="Capture annotated screenshots and Markdown tables for chappy UI."
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Destination directory for generated docs (default: dist/markdown_<language>).",
    )
    parser.add_argument(
        "--html-out-dir",
        type=Path,
        help="Destination directory for generated HTML docs (default: derived from --out-dir).",
    )
    parser.add_argument(
        "--skip-html", action="store_true", help="Disable HTML conversion after Markdown export."
    )
    parser.add_argument(
        "--qt-platform",
        default=os.environ.get("QT_QPA_PLATFORM"),
        help="Override QT_QPA_PLATFORM for headless runs (example: offscreen).",
    )
    parser.add_argument(
        "--language", help="UI language code used for doc labels (example: ja, en)."
    )
    parser.add_argument(
        "--scale-width",
        type=int,
        default=1600,
        help="Target width for annotated screenshots (default: 1600).",
    )
    parser.add_argument(
        "--show-internal-id",
        action="store_true",
        help="Include internal widget identifiers in the generated Markdown header.",
    )
    return parser.parse_args()


def main() -> int:
    """Entrypoint for rendering annotated documentation assets.

    Returns:
        終了コード。成功時は0、失敗時は非ゼロを返す。
    """
    args = parse_args()
    version = _get_env_flag("CHAPPY_BUILD_VERSION") or _default_version_label()

    # Resolve out_dir based on language if not explicitly provided
    language = args.language or "ja"
    out_dir: Path = args.out_dir or _project_root() / f"dist/markdown_{language}"

    html_out_dir: Path | None = None
    if not args.skip_html:
        html_out_dir = args.html_out_dir or _derive_html_out_dir(out_dir)

    profile_choices = available_profiles()
    if not profile_choices:
        logger.error("No profiles available. Cannot generate documentation.")
        return 1

    profile_name = profile_choices[0]

    if args.qt_platform:
        os.environ["QT_QPA_PLATFORM"] = args.qt_platform
    else:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    configure_offscreen_font_environment()

    existing_app = QApplication.instance()
    app = existing_app if isinstance(existing_app, QApplication) else QApplication([])
    ensure_high_dpi_mode()

    try:
        configure_application_font(app, strict=True)
    except FontConfigurationError:
        logger.exception("Cannot generate user manual screenshots")
        app.quit()
        return 1

    if args.language:
        language_switcher = get_language_switcher()
        language_switcher.set_language(args.language)
        install_manual_language(args.language)

    manifest = load_profile(profile_name, version=version)
    options = RuntimeOptions(
        out_dir=out_dir,
        html_out_dir=html_out_dir,
        version=version,
        scale_width=args.scale_width,
        show_internal_id=args.show_internal_id,
        language=language,
        headless=True,
    )
    run_manifest(app, manifest, options)
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
