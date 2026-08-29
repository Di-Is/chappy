#!/usr/bin/env python3
"""Validate Qt runtime translation catalogs."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from chappy.i18n.languages import require_language

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


DEFAULT_SOURCE_DIR = Path("src/chappy")
DEFAULT_TS_INPUT = Path("src/chappy/i18n/qt/chappy_ja.ts")
DEFAULT_QM_OUTPUT = Path(tempfile.gettempdir()) / "chappy_ja.qm"
DEFAULT_TARGET_LANGUAGE = "ja"
EXPECTED_TS_LANGUAGE = require_language(DEFAULT_TARGET_LANGUAGE).qt_locale
DEFAULT_LUPDATE_TOOL = "pyside6-lupdate"
DEFAULT_LRELEASE_TOOL = "pyside6-lrelease"
LEGACY_RUNTIME_TOKENS = frozenset({"GuiKey", "DlgKey", "MessagesKey", "TranslationSpec"})


@dataclass(frozen=True, order=True)
class QtMessageKey:
    """Uniquely identify a Qt catalog message."""

    context: str
    source: str
    comment: str = ""


@dataclass(frozen=True)
class QtCatalogReport:
    """Summarize validation results for a Qt TS catalog."""

    messages: int
    unfinished: int
    empty: int
    obsolete: int


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
        nargs="*",
        type=Path,
        default=[DEFAULT_SOURCE_DIR],
        help="Python source files or directories scanned by pyside6-lupdate.",
    )
    parser.add_argument(
        "--ts-input",
        type=Path,
        default=DEFAULT_TS_INPUT,
        help="Committed .ts catalog to validate.",
    )
    parser.add_argument(
        "--qm-output",
        type=Path,
        default=DEFAULT_QM_OUTPUT,
        help="Temporary .qm output path used to verify lrelease.",
    )
    parser.add_argument(
        "--expected-qm",
        type=Path,
        default=None,
        help="Committed .qm catalog that must match the generated lrelease output.",
    )
    parser.add_argument(
        "--extensions",
        default="py",
        help="Comma-separated source file extensions passed to pyside6-lupdate.",
    )
    parser.add_argument(
        "--lupdate-tool", default=DEFAULT_LUPDATE_TOOL, help="lupdate executable name or path."
    )
    parser.add_argument(
        "--lrelease-tool", default=DEFAULT_LRELEASE_TOOL, help="lrelease executable name or path."
    )
    parser.add_argument(
        "--skip-lupdate",
        action="store_true",
        help="Skip source extraction comparison against a temporary lupdate output.",
    )
    parser.add_argument("--skip-lrelease", action="store_true", help="Skip lrelease verification.")
    return parser.parse_args(argv)


def collect_catalog_messages(ts_path: Path) -> set[QtMessageKey]:
    """Collect context/source message keys from a Qt TS catalog.

    Args:
        ts_path: TS catalog path.

    Returns:
        Set of catalog message keys.
    """
    root = ET.parse(ts_path).getroot()  # noqa: S314
    messages: set[QtMessageKey] = set()
    for context_element in root.findall("context"):
        name_element = context_element.find("name")
        context = name_element.text if name_element is not None and name_element.text else ""
        for message_element in context_element.findall("message"):
            source_element = message_element.find("source")
            comment_element = message_element.find("comment")
            source = (
                source_element.text if source_element is not None and source_element.text else ""
            )
            comment = (
                comment_element.text
                if comment_element is not None and comment_element.text is not None
                else ""
            )
            if context and source:
                messages.add(QtMessageKey(context=context, source=source, comment=comment))
    return messages


def validate_catalog_translations(ts_path: Path) -> tuple[QtCatalogReport, list[str]]:
    """Validate translation state inside a committed TS catalog.

    Args:
        ts_path: TS catalog path.

    Returns:
        Catalog report and human-readable validation errors.
    """
    root = ET.parse(ts_path).getroot()  # noqa: S314
    errors: list[str] = []
    language = root.get("language", "")
    if language != EXPECTED_TS_LANGUAGE:
        errors.append(f"unexpected TS language '{language}', expected {EXPECTED_TS_LANGUAGE}")
    messages = 0
    unfinished = 0
    empty = 0
    obsolete = 0

    for context_element in root.findall("context"):
        name_element = context_element.find("name")
        context = (
            name_element.text if name_element is not None and name_element.text else "<unknown>"
        )
        for message_element in context_element.findall("message"):
            messages += 1
            source_element = message_element.find("source")
            translation_element = message_element.find("translation")
            source = (
                source_element.text if source_element is not None and source_element.text else ""
            )
            label = f"{context}: {source}"
            if not source:
                errors.append(f"empty source text in context: {context}")
            message_type = message_element.get("type")
            translation_type = (
                translation_element.get("type") if translation_element is not None else None
            )
            if message_type == "obsolete" or translation_type == "obsolete":
                obsolete += 1
                errors.append(f"obsolete translation remains: {label}")
                continue
            if translation_type == "unfinished":
                unfinished += 1
                errors.append(f"unfinished translation: {label}")
            if translation_element is None or not _translation_has_text(translation_element):
                empty += 1
                errors.append(f"empty translation: {label}")

    report = QtCatalogReport(
        messages=messages, unfinished=unfinished, empty=empty, obsolete=obsolete
    )
    return report, errors


def _translation_has_text(element: ET.Element) -> bool:
    """Return whether a translation element contains text.

    Args:
        element: TS translation element.

    Returns:
        True when the translation contains direct text or plural forms.
    """
    if element.text and element.text.strip():
        return True
    return any(child.text and child.text.strip() for child in element)


def compare_catalog_sources(
    *,
    source_dirs: Sequence[Path],
    ts_input: Path,
    extensions: str,
    lupdate_tool: str = DEFAULT_LUPDATE_TOOL,
) -> list[str]:
    """Compare committed TS sources with a fresh lupdate extraction.

    Args:
        source_dirs: Source files or directories scanned by lupdate.
        ts_input: Committed TS catalog path.
        extensions: Source file extensions passed to lupdate.
        lupdate_tool: lupdate executable name or path.

    Returns:
        Human-readable validation errors.
    """
    with tempfile.TemporaryDirectory(prefix="chappy-i18n-qt-") as temp_dir:
        extracted_ts = Path(temp_dir) / "chappy_ja.ts"
        run_lupdate_check(
            source_dirs=source_dirs,
            ts_output=extracted_ts,
            extensions=extensions,
            tool=lupdate_tool,
        )
        committed = collect_catalog_messages(ts_input)
        extracted = collect_catalog_messages(extracted_ts)

    missing = sorted(extracted - committed)
    stale = sorted(committed - extracted)
    errors = [
        f"missing TS entry for extracted source: {_format_message_key(key)}" for key in missing
    ]
    errors.extend(
        f"stale TS entry not found in sources: {_format_message_key(key)}" for key in stale
    )
    return errors


def run_lupdate_check(
    *,
    source_dirs: Sequence[Path],
    ts_output: Path,
    extensions: str,
    tool: str = DEFAULT_LUPDATE_TOOL,
) -> subprocess.CompletedProcess[str]:
    """Run pyside6-lupdate for validation.

    Args:
        source_dirs: Source files or directories scanned by lupdate.
        ts_output: Output TS path.
        extensions: Source file extensions passed to lupdate.
        tool: lupdate executable name or path.

    Returns:
        Completed subprocess result.

    Raises:
        subprocess.CalledProcessError: When lupdate exits with a non-zero status.
    """
    source_paths = list(_iter_source_files(source_dirs))
    ts_output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        tool,
        *(str(path) for path in source_paths),
        "-extensions",
        extensions,
        "-ts",
        str(ts_output),
    ]
    return subprocess.run(command, check=True, capture_output=True, text=True)


def run_lrelease_check(
    *, ts_input: Path, qm_output: Path, tool: str = DEFAULT_LRELEASE_TOOL
) -> subprocess.CompletedProcess[str]:
    """Run pyside6-lrelease for validation.

    Args:
        ts_input: Input TS path.
        qm_output: Output QM path.
        tool: lrelease executable name or path.

    Returns:
        Completed subprocess result.

    Raises:
        subprocess.CalledProcessError: When lrelease exits with a non-zero status.
    """
    qm_output.parent.mkdir(parents=True, exist_ok=True)
    command = [tool, str(ts_input), "-qm", str(qm_output)]
    return subprocess.run(command, check=True, capture_output=True, text=True)


def compare_qm_catalogs(*, generated_qm: Path, expected_qm: Path, ts_input: Path) -> list[str]:
    """Compare generated and committed QM catalogs.

    Args:
        generated_qm: QM catalog generated during validation.
        expected_qm: Committed QM catalog expected to match.
        ts_input: TS catalog used to generate the QM output.

    Returns:
        Human-readable validation errors.
    """
    if not expected_qm.is_file():
        return [f"expected QM catalog is missing: {expected_qm}"]

    if generated_qm.read_bytes() == expected_qm.read_bytes():
        return []

    command = f"uv run python scripts/i18n_lrelease.py {ts_input} --qm-output {expected_qm}"
    return [f"expected QM catalog is stale: {expected_qm}", f"regenerate with: {command}"]


def _format_message_key(key: QtMessageKey) -> str:
    """Format a message key for diagnostics.

    Args:
        key: Message key to format.

    Returns:
        Human-readable message key.
    """
    if key.comment:
        return f"{key.context}: {key.source} [{key.comment}]"
    return f"{key.context}: {key.source}"


def collect_legacy_runtime_references(source_dirs: Sequence[Path]) -> list[str]:
    """Collect legacy runtime key references from Python sources.

    Args:
        source_dirs: Source files or directories to inspect.

    Returns:
        Human-readable validation errors.
    """
    errors: list[str] = []
    for path in _iter_source_files(source_dirs):
        text = path.read_text(encoding="utf-8")
        errors.extend(
            f"legacy runtime i18n token '{token}' found in {path}"
            for token in sorted(LEGACY_RUNTIME_TOKENS)
            if token in text
        )
    return errors


def collect_legacy_gui_yaml(locales_dir: Path) -> list[str]:
    """Collect non-documentation YAML resources that should no longer exist.

    Args:
        locales_dir: Root directory containing language subdirectories.

    Returns:
        Human-readable validation errors.
    """
    errors: list[str] = []
    for language in ("en", "ja"):
        language_dir = locales_dir / language
        if not language_dir.exists():
            continue
        for yaml_path in sorted(language_dir.rglob("*.yaml")):
            relative = yaml_path.relative_to(language_dir)
            if relative.parts and relative.parts[0] == "doc":
                continue
            errors.append(f"legacy GUI YAML remains: {yaml_path}")
    return errors


def _iter_source_files(paths: Sequence[Path]) -> Iterable[Path]:
    """Yield Python source files from files or directories.

    Args:
        paths: Source files or directories.

    Yields:
        Python files found under the provided paths.
    """
    for path in paths:
        if path.is_file() and path.suffix == ".py":
            yield path
            continue
        if path.is_dir():
            yield from sorted(file_path for file_path in path.rglob("*.py") if file_path.is_file())


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface.

    Args:
        argv: Optional command-line arguments without the executable name.

    Returns:
        Process exit code.
    """
    args = parse_args(sys.argv[1:] if argv is None else argv)
    errors: list[str] = []

    try:
        report, translation_errors = validate_catalog_translations(args.ts_input)
        errors.extend(translation_errors)
        if not args.skip_lupdate:
            errors.extend(
                compare_catalog_sources(
                    source_dirs=args.source_dirs,
                    ts_input=args.ts_input,
                    extensions=args.extensions,
                    lupdate_tool=args.lupdate_tool,
                )
            )
        if not args.skip_lrelease:
            run_lrelease_check(
                ts_input=args.ts_input, qm_output=args.qm_output, tool=args.lrelease_tool
            )
            if args.expected_qm is not None:
                errors.extend(
                    compare_qm_catalogs(
                        generated_qm=args.qm_output,
                        expected_qm=args.expected_qm,
                        ts_input=args.ts_input,
                    )
                )
        elif args.expected_qm is not None:
            errors.append("--expected-qm requires lrelease verification")
    except (ET.ParseError, OSError, subprocess.CalledProcessError) as error:
        sys.stderr.write(f"[error] Qt i18n validation failed: {error}\n")
        return 1

    errors.extend(collect_legacy_runtime_references(args.source_dirs))
    errors.extend(collect_legacy_gui_yaml(args.ts_input.parents[1]))

    sys.stdout.write(
        "[i18n] Qt catalog: "
        f"{report.messages} messages, "
        f"{report.unfinished} unfinished, "
        f"{report.empty} empty, "
        f"{report.obsolete} obsolete\n"
    )

    if errors:
        for validation_error in errors:
            sys.stderr.write(f"[error] {validation_error}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
