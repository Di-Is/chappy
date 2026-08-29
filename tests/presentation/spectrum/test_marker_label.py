"""Unit tests for absorber component marker label formatting."""

from __future__ import annotations

from chappy.presentation.spectrum import (
    format_abbreviated_component_marker_label,
    format_component_marker_label,
)


def test_plain_name_without_tie_label() -> None:
    """Return the bare name when no tie label is set."""
    assert format_component_marker_label("c1", None) == "c1"


def test_appends_bracketed_tie_label() -> None:
    """Append the bracketed tie label when present."""
    assert format_component_marker_label("c1", "A") == "c1 [A]"


def test_abbreviation_keeps_only_the_rounded_wavelength() -> None:
    """Drop the species and decimals from a transition name."""
    assert format_abbreviated_component_marker_label("MgII 2796.35", None) == "2796"


def test_abbreviation_keeps_the_tie_label() -> None:
    """Keep the bracketed tie label alongside the rounded wavelength."""
    assert format_abbreviated_component_marker_label("HI 1215.67", "A") == "1216 [A]"


def test_abbreviation_leaves_names_without_a_trailing_wavelength() -> None:
    """Return the name unchanged when its last token is not a number."""
    assert format_abbreviated_component_marker_label("c1", None) == "c1"
