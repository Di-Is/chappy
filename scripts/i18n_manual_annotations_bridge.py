#!/usr/bin/env python3
"""Regenerate the lupdate extraction bridge for annotations_map.yaml.

``pyside6-lupdate`` only scans Python (and other supported) source files, so
English strings declared as data in ``annotations_map.yaml`` are invisible to
it. This script walks the YAML, collects every literal string stored under a
``text:`` node, and writes a generated Python module that lists each string
wrapped in ``QT_TRANSLATE_NOOP("ManualAnnotations", ...)``. lupdate then picks
these calls up like any other source string, keeping ``manual_ja.ts`` in sync
with the YAML content.

The generated module is never imported by the manual generator itself; it
exists solely to be scanned by lupdate and is committed alongside the other
Qt catalog artifacts. Regenerate it whenever ``annotations_map.yaml`` changes,
before running ``i18n_lupdate.py``.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from collections.abc import Sequence

DEFAULT_ANNOTATIONS_MAP = Path(
    "docs/user_manual/src/chappy_user_manual_generator/annotations_map.yaml"
)
DEFAULT_OUTPUT = Path(
    "docs/user_manual/src/chappy_user_manual_generator/i18n/_annotations_extraction_bridge.py"
)
CONTEXT = "ManualAnnotations"

_HEADER = '''"""Generated lupdate extraction bridge for annotations_map.yaml.

Do not edit manually: regenerate with
``uv run python scripts/i18n_manual_annotations_bridge.py``.
This module is never imported at runtime; it only exists so that
``pyside6-lupdate`` can discover the English strings declared as data in
``annotations_map.yaml``.
"""

from __future__ import annotations

from PySide6.QtCore import QT_TRANSLATE_NOOP

_SOURCE_STRINGS = (
'''

_FOOTER = ")\n"


def _collect_text_strings(node: object, collected: list[str]) -> None:
    """Recursively collect every string found under a ``text`` key.

    Args:
        node: Current YAML node (list, mapping, or scalar).
        collected: Accumulator list receiving discovered strings in order.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "text" and isinstance(value, str):
                collected.append(value)
                continue
            _collect_text_strings(value, collected)
    elif isinstance(node, list):
        for item in node:
            _collect_text_strings(item, collected)


def extract_source_strings(annotations_map: Path) -> list[str]:
    """Return the deduplicated, sorted list of translatable strings.

    Args:
        annotations_map: Path to ``annotations_map.yaml``.

    Returns:
        Deduplicated source strings sorted for a stable diff.
    """
    data: Any = yaml.safe_load(annotations_map.read_text(encoding="utf-8")) or []
    collected: list[str] = []
    _collect_text_strings(data, collected)
    return sorted(set(collected))


def render_bridge_module(source_strings: Sequence[str]) -> str:
    """Render the generated bridge module source.

    Args:
        source_strings: Translatable strings to embed as ``QT_TRANSLATE_NOOP`` calls.

    Returns:
        Full Python module source text.
    """
    lines = [f"    QT_TRANSLATE_NOOP({CONTEXT!r}, {text!r}),\n" for text in source_strings]
    return _HEADER + "".join(lines) + _FOOTER


def read_bridge_strings(bridge_path: Path) -> list[str]:
    """Return the source strings currently listed in the generated bridge module.

    Parsing the AST (instead of comparing raw text) keeps the check stable
    against formatter rewrites of the generated file.

    Args:
        bridge_path: Path to the generated extraction bridge module.

    Returns:
        Source strings passed as the second ``QT_TRANSLATE_NOOP`` argument.
    """
    tree = ast.parse(bridge_path.read_text(encoding="utf-8"))
    return [
        node.args[1].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "QT_TRANSLATE_NOOP"
        and len(node.args) == 2
        and isinstance(node.args[1], ast.Constant)
        and isinstance(node.args[1].value, str)
    ]


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Command-line arguments without the executable name.

    Returns:
        Parsed command-line namespace.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--annotations-map",
        type=Path,
        default=DEFAULT_ANNOTATIONS_MAP,
        help="Path to annotations_map.yaml.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output path for the generated extraction bridge module.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the committed bridge matches annotations_map.yaml instead of writing.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Regenerate or verify the extraction bridge module.

    Args:
        argv: Command-line arguments without the executable name.

    Returns:
        Process exit code.
    """
    args = parse_args(sys.argv[1:] if argv is None else argv)
    source_strings = extract_source_strings(args.annotations_map)

    if args.check:
        if not args.output.exists():
            sys.stderr.write(f"[i18n] extraction bridge missing: {args.output}\n")
            return 1
        existing = read_bridge_strings(args.output)
        if existing != source_strings:
            expected = set(source_strings)
            actual = set(existing)
            for text in sorted(expected - actual):
                sys.stderr.write(f"[i18n] missing from bridge: {text!r}\n")
            for text in sorted(actual - expected):
                sys.stderr.write(f"[i18n] stale in bridge: {text!r}\n")
            sys.stderr.write(
                "[i18n] extraction bridge is out of date; run "
                "`uv run python scripts/i18n_manual_annotations_bridge.py`\n"
            )
            return 1
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_bridge_module(source_strings), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
