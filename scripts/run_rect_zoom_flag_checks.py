#!/usr/bin/env python3
"""Command-line helper to run rectangle zoom regression tests."""

from __future__ import annotations

import argparse
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

DEFAULT_TEST_TARGETS: tuple[str, ...] = (
    "tests/gui/actions/test_spectrum_interactor.py",
    "tests/gui/interactor/test_interaction_state_controller.py",
    "tests/gui/controllers/test_mode_coordinator_interaction.py",
    "tests/gui/spectrum/test_spectrum_presenter.py",
)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run rectangle zoom regression tests with the state controller enabled."
    )
    parser.add_argument(
        "--tests", nargs="*", help="Optional explicit list of pytest targets to execute."
    )
    parser.add_argument(
        "--pytest-args", nargs="*", default=(), help="Additional arguments forwarded to pytest."
    )
    return parser.parse_args(argv if argv is not None else None)


def _run_pytest(*, tests: Sequence[str], extra_args: Sequence[str]) -> int:
    """Run pytest against the provided targets.

    The command enforces ``--no-cov`` so that coverage collectors stay disabled even if
    global pytest configuration enables them.
    """
    command = [sys.executable, "-m", "pytest", "--no-cov", *tests, *extra_args]
    completed = subprocess.run(command, check=False)
    return completed.returncode


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the regression checks entrypoint."""
    args = _parse_args(argv)
    tests = tuple(args.tests) if args.tests else DEFAULT_TEST_TARGETS
    extra_args = tuple(args.pytest_args)
    return _run_pytest(tests=tests, extra_args=extra_args)


if __name__ == "__main__":
    raise SystemExit(main())
