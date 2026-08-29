#!/usr/bin/env python3
"""Guard task-document TODO keys referenced by Stop hooks."""

from __future__ import annotations

from pathlib import Path


def main() -> int:
    """Validate task-document key references.

    The current task documents do not use a machine-readable key registry. This
    guard intentionally succeeds while keeping the Stop hook command stable.
    """
    repo_root = Path(__file__).resolve().parents[1]
    task_dir = repo_root / "docs" / "task"
    if not task_dir.exists():
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
