"""Consistency checks between tutorial documentation and runtime chapters."""

from __future__ import annotations

from chappy_user_manual_generator.tutorial_guide import (
    _BOTH_WALKTHROUGHS,
    _CHAPTERS,
    _PREREQUISITES,
    _WALKTHROUGHS,
)

from chappy.gui.shell.tutorial_chapters import (
    build_full_walkthrough_chapters,
    build_short_walkthrough_chapters,
)


def test_walkthrough_chapter_counts_match_runtime() -> None:
    """Keep both displayed chapter counts synchronized with the builders."""
    short_chapters = build_short_walkthrough_chapters()
    full_chapters = build_full_walkthrough_chapters()

    assert len(short_chapters) == _WALKTHROUGHS[0].chapter_count
    assert len(full_chapters) == _WALKTHROUGHS[1].chapter_count


def test_chapter_ids_and_order_match_runtime() -> None:
    """Keep the documented chapter rows synchronized with both walkthroughs."""
    documented_full_ids = tuple(chapter.chapter_id for chapter in _CHAPTERS)
    documented_short_ids = tuple(
        chapter.chapter_id
        for chapter in _CHAPTERS
        if chapter.included_source == _BOTH_WALKTHROUGHS
    )

    assert (
        tuple(chapter.chapter_id for chapter in build_short_walkthrough_chapters())
        == documented_short_ids
    )
    assert (
        tuple(chapter.chapter_id for chapter in build_full_walkthrough_chapters())
        == documented_full_ids
    )


def test_chapter_prerequisite_presence_matches_runtime() -> None:
    """Keep prerequisite rows and per-chapter markers synchronized with runtime."""
    full_chapters = build_full_walkthrough_chapters()
    runtime_presence = tuple(
        (chapter.chapter_id, chapter.prerequisite is not None) for chapter in full_chapters
    )
    documented_presence = tuple(
        (chapter.chapter_id, chapter.has_prerequisite) for chapter in _CHAPTERS
    )
    runtime_prerequisite_ids = tuple(
        chapter.chapter_id for chapter in full_chapters if chapter.prerequisite is not None
    )
    documented_prerequisite_ids = tuple(prerequisite.chapter_id for prerequisite in _PREREQUISITES)

    assert runtime_presence == documented_presence
    assert runtime_prerequisite_ids == documented_prerequisite_ids
