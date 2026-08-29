"""HTML conversion utilities for the generated user manual."""

from __future__ import annotations

import re
import shutil
from typing import TYPE_CHECKING

import markdown

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

_MARKDOWN_EXTENSIONS: Iterable[str] = ("extra", "toc")

_BASE_STYLES = """\
:root {
  color-scheme: light;
  font-size: 16px;
}
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.6;
  margin: 0;
  padding: 2.5rem 1.25rem 3rem;
  background: #f9fafb;
  color: #1f2933;
}
main {
  max-width: 960px;
  margin: 0 auto;
  background: #ffffff;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.1);
  padding: 2.5rem;
}
@media (max-width: 640px) {
  main {
    padding: 1.5rem;
  }
}
h1, h2, h3, h4 {
  line-height: 1.25;
  color: #111827;
}
a {
  color: #2563eb;
  text-decoration: none;
}
a:hover,
a:focus {
  text-decoration: underline;
}
table {
  width: 100%;
  border-collapse: collapse;
  margin: 1.5rem 0;
  font-size: 0.95rem;
}
th, td {
  border: 1px solid #d1d5db;
  padding: 0.6rem 0.75rem;
  vertical-align: top;
}
th {
  background: #eef2ff;
  text-align: left;
  font-weight: 600;
}
tbody tr:nth-child(even) {
  background: #f3f4f6;
}
img {
  max-width: 100%;
  height: auto;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.12);
}
code {
  font-family: SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  background: #f3f4f6;
  padding: 0.125rem 0.375rem;
  border-radius: 6px;
  font-size: 0.9rem;
}
pre code {
  display: block;
  padding: 1rem;
  overflow-x: auto;
}
blockquote {
  border-left: 4px solid #c7d2fe;
  padding: 0.5rem 1rem;
  color: #374151;
  background: #eef2ff;
  border-radius: 0 12px 12px 0;
}
ul, ol {
  padding-inline-start: 1.5rem;
}
.back-to-top {
  position: fixed;
  right: 1.25rem;
  bottom: 1.25rem;
  padding: 0.5rem 0.875rem;
  border-radius: 999px;
  background: #2563eb;
  color: #ffffff;
  font-size: 0.85rem;
  box-shadow: 0 2px 6px rgba(15, 23, 42, 0.25);
}
.back-to-top:hover,
.back-to-top:focus {
  background: #1d4ed8;
  color: #ffffff;
  text-decoration: none;
}
@media print {
  body {
    background: #ffffff;
    padding: 0;
  }
  main {
    max-width: none;
    border-radius: 0;
    box-shadow: none;
    padding: 0;
  }
  a {
    color: inherit;
  }
  h1 {
    break-before: page;
  }
  h1:first-of-type {
    break-before: auto;
  }
  h2, h3, h4 {
    break-after: avoid;
  }
  tr, img, blockquote {
    break-inside: avoid;
  }
  .back-to-top {
    display: none;
  }
}
"""

_HREF_MD_PATTERN = re.compile(r'href="(?P<path>[^":]+?)\.md(?P<fragment>#[^"]*)?"')


def convert_markdown_tree(
    markdown_root: Path, html_root: Path, *, language: str | None = None
) -> None:
    """Convert the entire Markdown tree into HTML files under ``html_root``."""
    if not markdown_root.exists():
        return

    if html_root.exists():
        shutil.rmtree(html_root)
    html_root.mkdir(parents=True, exist_ok=True)

    for path in sorted(markdown_root.rglob("*")):
        relative_path = path.relative_to(markdown_root)
        target_path = html_root / relative_path

        if path.is_dir():
            target_path.mkdir(parents=True, exist_ok=True)
            continue

        if path.suffix.lower() != ".md":
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target_path)
            continue

        markdown_text = path.read_text(encoding="utf-8")
        title = _extract_title(markdown_text)
        html_content = _render_html(markdown_text, title=title, language=language)

        html_target = target_path.with_suffix(".html")
        html_target.parent.mkdir(parents=True, exist_ok=True)
        html_target.write_text(html_content, encoding="utf-8")


def _extract_title(markdown_text: str) -> str:
    for line in markdown_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return "Chappy User Manual"


def _render_html(markdown_text: str, *, title: str, language: str | None) -> str:
    converter = markdown.Markdown(extensions=_MARKDOWN_EXTENSIONS, output_format="html5")
    body = converter.convert(markdown_text)
    body = _rewrite_internal_links(body)

    lang_attr = _normalise_lang(language)
    back_to_top_label = "目次へ戻る" if lang_attr == "ja" else "Back to contents"
    return "\n".join(
        [
            "<!DOCTYPE html>",
            f'<html lang="{lang_attr}">',
            "<head>",
            '  <meta charset="utf-8" />',
            '  <meta name="viewport" content="width=device-width, initial-scale=1" />',
            f"  <title>{title}</title>",
            "  <style>",
            _BASE_STYLES,
            "  </style>",
            "</head>",
            "<body>",
            '  <main id="top">',
            body,
            "  </main>",
            f'  <a class="back-to-top" href="#top">▲ {back_to_top_label}</a>',
            "</body>",
            "</html>",
        ]
    )


def _rewrite_internal_links(html_text: str) -> str:
    """Rewrite ``.md`` hyperlink targets to ``.html`` counterparts."""

    def _replace(match: re.Match[str]) -> str:
        path = match.group("path")
        fragment = match.group("fragment") or ""
        return f'href="{path}.html{fragment}"'

    return _HREF_MD_PATTERN.sub(_replace, html_text)


def _normalise_lang(language: str | None) -> str:
    if not language:
        return "ja"
    return language.split("-", 1)[0] or "ja"
