"""Assemble the generated manual pages into the single-page manual entry.

The combined document is written as the manual index (``index.md``) to the
Markdown output root after all individual pages exist, so the manual opens as
one searchable page. Chapter order follows the manual index specification;
entries pointing outside the output tree (for example the work-in-progress
troubleshooting notes) are excluded. Pages linked from an included page but
absent from the index (dialog pages) are appended right after the page that
links them. Cross-page links are rewritten to in-document anchors and image
paths are rebased onto the output root so the document renders standalone.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QT_TRANSLATE_NOOP

from chappy_user_manual_generator.templates import doc_version_line
from chappy_user_manual_generator.translations import translate_manual_text

if TYPE_CHECKING:
    from pathlib import Path

    from chappy_user_manual_generator.models import ManualIndexSpec

_EXPORTER_CONTEXT = "ManualExporter"
_CONTENTS_HEADING_SOURCE = QT_TRANSLATE_NOOP("ManualExporter", "Contents")

_LINK_PATTERN = re.compile(r"(?P<bang>!?)\[(?P<text>[^\]]*)\]\((?P<target>[^)]+)\)")
_EXTERNAL_SCHEMES = ("http://", "https://", "mailto:")


@dataclass(frozen=True)
class _SinglePageSection:
    number: str
    anchor: str
    title: str
    page_path: str


@dataclass(frozen=True)
class _SinglePageChapter:
    number: str
    anchor: str
    heading: str
    intro: str | None
    sections: tuple[_SinglePageSection, ...]


def write_single_page_manual(spec: ManualIndexSpec, *, out_dir: Path, version: str) -> Path:
    """Write the manual as one combined index page and return its path."""
    chapters = _collect_chapters(spec, out_dir)
    anchors = {
        section.page_path: section.anchor for chapter in chapters for section in chapter.sections
    }

    lines: list[str] = []
    title = spec.title or "Chappy User Manual"
    lines.extend((f"# {title}", "", doc_version_line(version), ""))
    for paragraph in spec.overview:
        lines.extend((paragraph, ""))
    lines.extend(_render_toc(chapters))
    for chapter in chapters:
        lines.extend(_render_chapter(chapter, out_dir=out_dir, anchors=anchors))

    target = out_dir / spec.filename
    target.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    return target


def _collect_chapters(spec: ManualIndexSpec, out_dir: Path) -> tuple[_SinglePageChapter, ...]:
    listed_pages = _listed_index_pages(spec, out_dir)
    included = set(listed_pages)

    chapters: list[_SinglePageChapter] = []
    for section in spec.sections:
        pages: list[tuple[str, str]] = []
        for entry in section.entries:
            if entry.path is None:
                continue
            page_path = posixpath.normpath(entry.path)
            if page_path not in listed_pages:
                continue
            pages.append((entry.title, page_path))
            for attached in _linked_subtree_pages(out_dir, page_path):
                if attached in included:
                    continue
                included.add(attached)
                pages.append((_page_title(out_dir / attached), attached))
        if not pages:
            continue
        chapter_number = str(len(chapters) + 1)
        sections = tuple(
            _SinglePageSection(
                number=f"{chapter_number}.{index}",
                anchor=f"sec-{chapter_number}-{index}",
                title=title,
                page_path=page_path,
            )
            for index, (title, page_path) in enumerate(pages, start=1)
        )
        chapters.append(
            _SinglePageChapter(
                number=chapter_number,
                anchor=f"sec-{chapter_number}",
                heading=section.heading,
                intro=section.intro,
                sections=sections,
            )
        )
    return tuple(chapters)


def _listed_index_pages(spec: ManualIndexSpec, out_dir: Path) -> set[str]:
    pages: set[str] = set()
    for section in spec.sections:
        for entry in section.entries:
            if entry.path is None:
                continue
            page_path = posixpath.normpath(entry.path)
            if page_path.startswith(".."):
                continue
            if not (out_dir / page_path).is_file():
                continue
            pages.add(page_path)
    return pages


def _linked_subtree_pages(out_dir: Path, page_path: str) -> tuple[str, ...]:
    """Return pages under ``page_path``'s directory that the page links to."""
    page_dir = posixpath.dirname(page_path)
    text = (out_dir / page_path).read_text(encoding="utf-8")
    linked: list[str] = []
    seen: set[str] = set()
    for match in _LINK_PATTERN.finditer(text):
        if match.group("bang"):
            continue
        target = match.group("target").partition("#")[0]
        if not target.endswith(".md") or target.startswith(("/", "#")) or "://" in target:
            continue
        resolved = posixpath.normpath(posixpath.join(page_dir, target))
        if resolved == page_path or resolved in seen or resolved.startswith(".."):
            continue
        if not resolved.startswith(f"{page_dir}/"):
            continue
        if not (out_dir / resolved).is_file():
            continue
        seen.add(resolved)
        linked.append(resolved)
    return tuple(linked)


def _render_toc(chapters: tuple[_SinglePageChapter, ...]) -> list[str]:
    heading = translate_manual_text(_EXPORTER_CONTEXT, _CONTENTS_HEADING_SOURCE)
    lines = [f"## {heading}", ""]
    for chapter in chapters:
        lines.append(f"- [{chapter.number}. {chapter.heading}](#{chapter.anchor})")
        lines.extend(
            f"    - [{section.number} {section.title}](#{section.anchor})"
            for section in chapter.sections
        )
    lines.append("")
    return lines


def _render_chapter(
    chapter: _SinglePageChapter, *, out_dir: Path, anchors: dict[str, str]
) -> list[str]:
    lines = [f"# {chapter.number}. {chapter.heading} {{: #{chapter.anchor} }}", ""]
    if chapter.intro:
        lines.extend((chapter.intro, ""))
    for section in chapter.sections:
        lines.extend((f"## {section.number} {section.title} {{: #{section.anchor} }}", ""))
        body = _render_page_body(out_dir, section.page_path, anchors)
        if body:
            lines.extend((body, ""))
    return lines


def _render_page_body(out_dir: Path, page_path: str, anchors: dict[str, str]) -> str:
    text = (out_dir / page_path).read_text(encoding="utf-8")
    body = _drop_leading_h1(text)
    body = _demote_headings(body)
    body = _rewrite_links(body, page_dir=posixpath.dirname(page_path), anchors=anchors)
    return body.strip("\n")


def _drop_leading_h1(text: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# "):
            return "\n".join(lines[index + 1 :])
        break
    return text


def _demote_headings(text: str) -> str:
    lines: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        demoted = f"#{line}" if not in_fence and line.startswith("#") else line
        lines.append(demoted)
    return "\n".join(lines)


def _rewrite_links(text: str, *, page_dir: str, anchors: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        bang = match.group("bang")
        link_text = match.group("text")
        target = match.group("target")
        if target.startswith("#") or target.startswith(_EXTERNAL_SCHEMES):
            return match.group(0)
        path_part = target.partition("#")[0]
        resolved = posixpath.normpath(posixpath.join(page_dir, path_part))
        if not bang and resolved in anchors:
            return f"[{link_text}](#{anchors[resolved]})"
        if resolved.startswith("..") or path_part.endswith(".md"):
            return link_text
        return f"{bang}[{link_text}]({resolved})"

    return _LINK_PATTERN.sub(replace, text)


def _page_title(page_file: Path) -> str:
    for line in page_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return page_file.stem
