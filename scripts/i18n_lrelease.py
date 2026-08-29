#!/usr/bin/env python3
"""Run PySide6 lrelease for Chappy Qt translation catalogs."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Command-line arguments without the executable name.

    Returns:
        Parsed command-line namespace.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ts_input", type=Path, help="Input .ts catalog path.")
    parser.add_argument("--qm-output", required=True, type=Path, help="Output .qm catalog path.")
    parser.add_argument(
        "--tool", default="pyside6-lrelease", help="lrelease executable name or path."
    )
    return parser.parse_args(argv)


def build_lrelease_command(
    *, ts_input: Path, qm_output: Path, tool: str = "pyside6-lrelease"
) -> list[str]:
    """Build the PySide6 lrelease command.

    Args:
        ts_input: Input .ts catalog path.
        qm_output: Output .qm catalog path.
        tool: lrelease executable name or path.

    Returns:
        Subprocess command arguments.
    """
    return [tool, str(ts_input), "-qm", str(qm_output)]


def run_lrelease(
    *, ts_input: Path, qm_output: Path, tool: str = "pyside6-lrelease"
) -> subprocess.CompletedProcess[str]:
    """Run PySide6 lrelease and create the output directory when needed.

    Args:
        ts_input: Input .ts catalog path.
        qm_output: Output .qm catalog path.
        tool: lrelease executable name or path.

    Returns:
        Completed subprocess result.

    Raises:
        subprocess.CalledProcessError: When lrelease exits with a non-zero status.
    """
    qm_output.parent.mkdir(parents=True, exist_ok=True)
    command = build_lrelease_command(ts_input=ts_input, qm_output=qm_output, tool=tool)
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
        result = run_lrelease(ts_input=args.ts_input, qm_output=args.qm_output, tool=args.tool)
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
