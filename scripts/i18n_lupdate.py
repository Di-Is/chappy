#!/usr/bin/env python3
"""Run PySide6 lupdate for Chappy Qt translation catalogs."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


def _parse_extensions(extensions: str) -> tuple[str, ...]:
    """Parse a comma-separated extension option.

    Args:
        extensions: Comma-separated source file extensions.

    Returns:
        Normalized extensions without leading dots.
    """
    return tuple(
        extension.strip().removeprefix(".")
        for extension in extensions.split(",")
        if extension.strip()
    )


def _expand_source_dirs(source_dirs: Sequence[Path], extensions: str) -> list[Path]:
    """Expand directory inputs to matching source files.

    Args:
        source_dirs: Source files or directories to scan.
        extensions: Comma-separated source file extensions to scan.

    Returns:
        Source files passed to lupdate.
    """
    extension_names = _parse_extensions(extensions)
    source_paths: list[Path] = []
    for source_dir in source_dirs:
        if not source_dir.is_dir():
            source_paths.append(source_dir)
            continue
        for extension_name in extension_names:
            source_paths.extend(sorted(source_dir.rglob(f"*.{extension_name}")))
    return source_paths


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Command-line arguments without the executable name.

    Returns:
        Parsed command-line namespace.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source_dirs",
        nargs="+",
        type=Path,
        help="Python source files or directories passed to pyside6-lupdate.",
    )
    parser.add_argument("--ts-output", required=True, type=Path, help="Output .ts catalog path.")
    parser.add_argument(
        "--tool", default="pyside6-lupdate", help="lupdate executable name or path."
    )
    parser.add_argument(
        "--extensions",
        default="py",
        help="Comma-separated source file extensions passed to pyside6-lupdate.",
    )
    return parser.parse_args(argv)


def build_lupdate_command(
    *,
    source_dirs: Sequence[Path],
    ts_output: Path,
    tool: str = "pyside6-lupdate",
    extensions: str = "py",
) -> list[str]:
    """Build the PySide6 lupdate command.

    Args:
        source_dirs: Source files or directories to scan.
        ts_output: Output .ts catalog path.
        tool: lupdate executable name or path.
        extensions: Comma-separated source file extensions to scan.

    Returns:
        Subprocess command arguments.
    """
    source_paths = _expand_source_dirs(source_dirs, extensions)
    return [
        tool,
        *(str(path) for path in source_paths),
        "-extensions",
        extensions,
        "-ts",
        str(ts_output),
    ]


def run_lupdate(
    *,
    source_dirs: Sequence[Path],
    ts_output: Path,
    tool: str = "pyside6-lupdate",
    extensions: str = "py",
) -> subprocess.CompletedProcess[str]:
    """Run PySide6 lupdate and create the output directory when needed.

    Args:
        source_dirs: Source files or directories to scan.
        ts_output: Output .ts catalog path.
        tool: lupdate executable name or path.
        extensions: Comma-separated source file extensions to scan.

    Returns:
        Completed subprocess result.

    Raises:
        subprocess.CalledProcessError: When lupdate exits with a non-zero status.
    """
    ts_output.parent.mkdir(parents=True, exist_ok=True)
    command = build_lupdate_command(
        source_dirs=source_dirs, ts_output=ts_output, tool=tool, extensions=extensions
    )
    return subprocess.run(command, check=True, capture_output=True, text=True)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface.

    Args:
        argv: Optional command-line arguments without the executable name.

    Returns:
        Process exit code.
    """
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result = run_lupdate(
            source_dirs=args.source_dirs,
            ts_output=args.ts_output,
            tool=args.tool,
            extensions=args.extensions,
        )
    except subprocess.CalledProcessError as error:
        if error.stdout:
            sys.stdout.write(error.stdout)
        if error.stderr:
            sys.stderr.write(error.stderr)
        return error.returncode

    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
