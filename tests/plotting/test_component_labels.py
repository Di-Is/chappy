"""Unit tests for shared rotated component label placement."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from matplotlib.figure import Figure

from chappy.plotting.component_labels import ComponentLabelEntry, place_rotated_component_labels

if TYPE_CHECKING:
    from matplotlib.axes import Axes


def _axes(xlim: tuple[float, float]) -> Axes:
    axes = Figure(figsize=(10.0, 6.0)).subplots()
    axes.set_xlim(*xlim)
    return axes


def _anchor_y(axes: Axes) -> float:
    return float(axes.texts[0].xy[1])


def test_empty_entries_place_nothing() -> None:
    """No entries should produce no annotations."""
    axes = _axes((0.0, 100.0))
    assert place_rotated_component_labels(axes, [], color="#2E7D32") == []
    assert len(axes.texts) == 0


def test_returns_annotations_in_input_order_rotated() -> None:
    """Annotations keep input order and are rotated vertically."""
    axes = _axes((-300.0, 300.0))
    entries = [
        ComponentLabelEntry(x=58.0, text="c8"),
        ComponentLabelEntry(x=-120.0, text="c1 [A]"),
    ]

    annotations = place_rotated_component_labels(axes, entries, color="#2E7D32")

    assert [annotation.get_text() for annotation in annotations] == ["c8", "c1 [A]"]
    assert all(annotation.get_rotation() == 90.0 for annotation in annotations)


def test_distant_neighbors_are_not_shifted() -> None:
    """Well-separated labels stay exactly on their own x positions."""
    axes = _axes((0.0, 100.0))
    entries = [
        ComponentLabelEntry(x=10.0, text="a"),
        ComponentLabelEntry(x=50.0, text="b"),
        ComponentLabelEntry(x=90.0, text="c"),
    ]

    annotations = place_rotated_component_labels(axes, entries, color="#2E7D32")

    assert {annotation.xyann for annotation in annotations} == {(0.0, -3.0)}


def test_near_neighbors_are_pushed_apart_horizontally() -> None:
    """Overlapping labels separate sideways while staying on one row."""
    axes = _axes((0.0, 100.0))
    entries = [ComponentLabelEntry(x=50.0, text="a"), ComponentLabelEntry(x=50.1, text="b")]

    annotations = place_rotated_component_labels(axes, entries, color="#2E7D32")

    left, right = annotations
    assert left.xyann[0] < 0.0 < right.xyann[0]
    assert {annotation.xyann[1] for annotation in annotations} == {-3.0}


def test_pushed_cluster_stays_centered_on_its_original_span() -> None:
    """A dodged cluster is balanced, so its shifts cancel out."""
    axes = _axes((0.0, 100.0))
    entries = [
        ComponentLabelEntry(x=50.0, text="a"),
        ComponentLabelEntry(x=50.1, text="b"),
        ComponentLabelEntry(x=50.2, text="c"),
    ]

    annotations = place_rotated_component_labels(axes, entries, color="#2E7D32")

    assert sum(annotation.xyann[0] for annotation in annotations) == pytest.approx(0.0)


def test_band_top_moves_the_anchor_without_changing_offsets() -> None:
    """The band top is the axes fraction the labels hang from."""
    axes = _axes((0.0, 100.0))

    place_rotated_component_labels(
        axes, [ComponentLabelEntry(x=50.0, text="a")], color="#2E7D32", band_top=0.91
    )

    assert _anchor_y(axes) == 0.91


def test_crowding_falls_back_to_short_text_and_a_second_row() -> None:
    """A tight cluster abbreviates non-selected labels and alternates onto a second row."""
    axes = _axes((0.0, 100.0))
    entries = [
        ComponentLabelEntry(
            x=50.0 + 0.1 * index, text=f"MgII 279{index}.4", short_text=f"279{index}"
        )
        for index in range(8)
    ]

    annotations = place_rotated_component_labels(axes, entries, color="#2E7D32")

    assert [annotation.get_text() for annotation in annotations] == [
        f"279{index}" for index in range(8)
    ]
    assert len({annotation.xyann[1] for annotation in annotations}) == 2


def test_short_text_is_kept_when_the_band_is_too_shallow() -> None:
    """A band shorter than the full text abbreviates even without horizontal crowding."""
    axes = _axes((0.0, 100.0))
    entries = [ComponentLabelEntry(x=50.0, text="MgII 2796.4", short_text="2796")]

    annotations = place_rotated_component_labels(axes, entries, color="#2E7D32", band_top=0.76)

    assert annotations[0].get_text() == "2796"


def test_selected_entry_stays_full_text_bold_on_the_first_row() -> None:
    """Selection survives crowding: full text, first row, bold, above the others."""
    axes = _axes((0.0, 100.0))
    entries = [
        ComponentLabelEntry(
            x=50.0 + 0.1 * index,
            text=f"MgII 279{index}.4",
            short_text=f"279{index}",
            selected=index == 3,
        )
        for index in range(8)
    ]

    annotations = place_rotated_component_labels(axes, entries, color="#2E7D32")

    selected = annotations[3]
    assert selected.get_text() == "MgII 2793.4"
    assert selected.xyann[1] == -3.0
    assert selected.get_fontweight() == "bold"
    assert selected.get_zorder() > annotations[0].get_zorder()
