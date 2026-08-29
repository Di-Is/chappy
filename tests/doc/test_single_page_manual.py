from __future__ import annotations

from typing import TYPE_CHECKING

from chappy_user_manual_generator.models import IndexEntry, IndexSection, ManualIndexSpec
from chappy_user_manual_generator.single_page import write_single_page_manual

if TYPE_CHECKING:
    from pathlib import Path


def _write(root: Path, relative: str, text: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _build_tree(root: Path) -> ManualIndexSpec:
    _write(
        root,
        "operations/flow.md",
        "# Flow Title\n\n"
        "Intro paragraph.\n\n"
        "## Steps\n\n"
        "See [screen page](../screens/page.md) and "
        "[dialog](../menus/dialogs/DialogA.md).\n"
        "External [site](https://example.com) stays. "
        "Excluded [notes](../notes.md) becomes text.\n\n"
        "![shot](images/flow.png)\n",
    )
    _write(root, "operations/images/flow.png", "png")
    _write(root, "screens/page.md", "# Generic Title\n\nScreen body.\n")
    _write(
        root,
        "menus/menus.md",
        "# Menus\n\nSee [Dialog A](dialogs/DialogA.md) and [Dialog A](dialogs/DialogA.md).\n",
    )
    _write(root, "menus/dialogs/DialogA.md", "# Dialog A Title\n\nDialog body.\n")
    return ManualIndexSpec(
        title="Manual",
        overview=("Overview paragraph.",),
        sections=(
            IndexSection(
                heading="Flows",
                intro="Flow intro.",
                entries=(IndexEntry(title="Flow", path="operations/flow.md"),),
            ),
            IndexSection(
                heading="Screens", entries=(IndexEntry(title="Screen", path="screens/page.md"),)
            ),
            IndexSection(
                heading="Menus", entries=(IndexEntry(title="Menu List", path="menus/menus.md"),)
            ),
            IndexSection(
                heading="Excluded",
                entries=(
                    IndexEntry(title="Outside", path="../notes.md"),
                    IndexEntry(title="Missing", path="operations/missing.md"),
                ),
            ),
        ),
    )


def test_single_page_manual_numbers_sections_and_skips_unavailable_entries(tmp_path: Path) -> None:
    spec = _build_tree(tmp_path)

    target = write_single_page_manual(spec, out_dir=tmp_path, version="test-version")
    text = target.read_text(encoding="utf-8")

    assert target.name == "index.md"
    assert "# 1. Flows {: #sec-1 }" in text
    assert "## 1.1 Flow {: #sec-1-1 }" in text
    assert "# 2. Screens {: #sec-2 }" in text
    assert "# 4." not in text, "empty chapters must be dropped entirely"
    assert "Outside" not in text
    assert "test-version" in text


def test_single_page_manual_appends_linked_dialog_pages_once(tmp_path: Path) -> None:
    spec = _build_tree(tmp_path)

    text = write_single_page_manual(spec, out_dir=tmp_path, version="v").read_text(
        encoding="utf-8"
    )

    assert "## 3.2 Dialog A Title {: #sec-3-2 }" in text
    assert text.count("Dialog body.") == 1, "linked dialog page must be included exactly once"


def test_single_page_manual_rewrites_links_and_asset_paths(tmp_path: Path) -> None:
    spec = _build_tree(tmp_path)

    text = write_single_page_manual(spec, out_dir=tmp_path, version="v").read_text(
        encoding="utf-8"
    )

    assert "[screen page](#sec-2-1)" in text
    assert "[dialog](#sec-3-2)" in text
    assert "[Dialog A](#sec-3-2)" in text
    assert "[site](https://example.com)" in text
    assert "![shot](operations/images/flow.png)" in text
    assert "(../notes.md)" not in text
    assert "Excluded notes becomes text." in text


def test_single_page_manual_demotes_page_headings_and_drops_page_h1(tmp_path: Path) -> None:
    spec = _build_tree(tmp_path)

    text = write_single_page_manual(spec, out_dir=tmp_path, version="v").read_text(
        encoding="utf-8"
    )

    assert "### Steps" in text
    assert "# Flow Title" not in text
    assert "# Generic Title" not in text
