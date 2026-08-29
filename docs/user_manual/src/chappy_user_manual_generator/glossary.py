"""Glossary generator: single-source terms → per-language Markdown pages.

This module reads a YAML file that defines domain terms and writes language-
specific glossary pages used by the user manual. It is intentionally simple to
avoid adding heavy dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from chappy_user_manual_generator.markdown import MarkdownTableBuilder, format_markdown_text


@dataclass(slots=True)
class Term:
    """Container for a localized glossary entry and its metadata."""

    key: str
    label_ja: str
    label_en: str
    def_ja: str
    def_en: str
    aliases_ja: list[str]
    aliases_en: list[str]
    avoid_ja: list[str]
    avoid_en: list[str]
    # Optional metadata for ordering/grouping
    category: str = ""
    stage: int = 0
    weight: int = 0


def _load_yaml(path: Path) -> list[Term]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [
        Term(
            key=str(entry.get("key", "")),
            label_ja=str(entry.get("label", {}).get("ja", "")),
            label_en=str(entry.get("label", {}).get("en", "")),
            def_ja=str(entry.get("definition", {}).get("ja", "")),
            def_en=str(entry.get("definition", {}).get("en", "")),
            aliases_ja=[str(x) for x in entry.get("aliases", {}).get("ja", [])],
            aliases_en=[str(x) for x in entry.get("aliases", {}).get("en", [])],
            avoid_ja=[str(x) for x in entry.get("do_not_use", {}).get("ja", [])],
            avoid_en=[str(x) for x in entry.get("do_not_use", {}).get("en", [])],
            category=str(entry.get("category", "")),
            stage=int(entry.get("stage", 0) or 0),
            weight=int(entry.get("weight", 0) or 0),
        )
        for entry in data.get("terms", [])
    ]


def _resolve_terms_file(custom_path: Path | None) -> Path:
    if custom_path is not None and custom_path.exists():
        return custom_path
    # Fallback to packaged default
    return Path(__file__).with_name("data").joinpath("terms.yaml")


def _alias_cell(aliases: list[str], avoid: list[str]) -> str:
    parts: list[str] = []
    if aliases:
        parts.append(", ".join(aliases))
    if avoid:
        parts.append("非推奨: " + ", ".join(avoid))
    return "―" if not parts else "; ".join(parts)


def _categories_display_labels() -> dict[str, dict[str, str]]:
    """Mapping from category key to localized display labels.

    Keys here are stable identifiers referenced from `terms.yaml` (category field).
    """
    return {
        "data": {"ja": "データ/保存", "en": "Data / Storage"},
        "display": {"ja": "表示/確認", "en": "View / Inspect"},
        "prep_common": {"ja": "連続光", "en": "Continuum"},
        "detect": {"ja": "同定", "en": "Identification"},
        "analyze": {"ja": "解析", "en": "Analysis"},
        "objects": {"ja": "解析単位", "en": "Analysis Units"},
        "settings": {"ja": "設定", "en": "Settings"},
    }


def _group_and_sort(terms: list[Term]) -> list[tuple[str, int, list[Term]]]:
    """Return a list of (category, stage, terms_in_that_group) ordered for output.

    - Order by ascending stage (0 last), then by category label for stability.
    - Terms within a group are sorted by Japanese label (fallback to English).
    - Terms without category are grouped under "" with stage 0.
    """
    groups: dict[tuple[str, int], list[Term]] = {}
    for t in terms:
        key = (t.category, t.stage)
        groups.setdefault(key, []).append(t)
    ordered_keys = sorted(groups.keys(), key=lambda k: (k[1] or 999, k[0]))
    result: list[tuple[str, int, list[Term]]] = []
    for cat, stage in ordered_keys:
        items = sorted(
            groups[(cat, stage)], key=lambda x: (x.weight or 50, x.label_ja or x.label_en)
        )
        result.append((cat, stage, items))
    return result


def export_glossary(
    *, out_dir: Path, version: str, terms_path: Path | None = None
) -> dict[str, Path]:
    """Write `glossary.ja.md` and `glossary.en.md` under `out_dir`.

    Returns a mapping from language code to the generated path.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    source = _resolve_terms_file(terms_path)
    terms = _load_yaml(source)

    outputs: dict[str, Path] = {}
    # Grouping and ordering
    groups = _group_and_sort(terms)

    # Japanese
    labels = _categories_display_labels()
    ja_lines: list[str] = [
        "# 用語集",
        "",
        "このページでは、アプリで使う主な用語の意味をまとめています。",
        "",
    ]
    if version:
        ja_lines.extend([f"> バージョン: {version}", ""])
    for cat, _stage, items in groups:
        if cat:
            ja_lines.append(f"## {labels.get(cat, {}).get('ja', cat)}")
            ja_lines.append("")
        table = MarkdownTableBuilder(["用語", "説明", "別名"])
        for t in items:
            table.add_row((t.label_ja, t.def_ja, _alias_cell(t.aliases_ja, t.avoid_ja)))
        ja_lines.extend(table.lines())
        ja_lines.append("")
    ja_path = out_dir / "glossary.ja.md"
    formatted_ja = format_markdown_text("\n".join(ja_lines) + "\n")
    if not formatted_ja.endswith("\n"):
        formatted_ja += "\n"
    ja_path.write_text(formatted_ja, encoding="utf-8")
    outputs["ja"] = ja_path

    # English
    en_lines: list[str] = [
        "# Glossary",
        "",
        "This page defines common terms used in the application.",
        "",
    ]
    if version:
        en_lines.extend([f"> Version: {version}", ""])
    for cat, _stage, items in groups:
        if cat:
            en_lines.append(f"## {labels.get(cat, {}).get('en', cat)}")
            en_lines.append("")
        table = MarkdownTableBuilder(["Term", "Definition", "Aliases"])
        for t in items:
            aliases = ", ".join(t.aliases_en) if t.aliases_en else "—"
            avoid = "; Do not use: " + ", ".join(t.avoid_en) if t.avoid_en else ""
            if aliases == "—" and avoid:
                aliases = avoid.removeprefix("; ")
            elif avoid:
                aliases = aliases + avoid
            table.add_row((t.label_en, t.def_en, aliases))
        en_lines.extend(table.lines())
        en_lines.append("")
    en_path = out_dir / "glossary.en.md"
    formatted_en = format_markdown_text("\n".join(en_lines) + "\n")
    if not formatted_en.endswith("\n"):
        formatted_en += "\n"
    en_path.write_text(formatted_en, encoding="utf-8")
    outputs["en"] = en_path

    return outputs
