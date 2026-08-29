"""Display-text formatting for absorber component markers."""

from __future__ import annotations


def format_component_marker_label(name: str, tie_label: str | None) -> str:
    """Return the on-screen marker text, appending the bracketed tie label when present."""
    if tie_label is None:
        return name
    return f"{name} [{tie_label}]"


def format_abbreviated_component_marker_label(name: str, tie_label: str | None) -> str:
    """Return the crowded-view marker text, keeping only the rounded wavelength when parseable."""
    abbreviated = _abbreviated_name(name)
    if not abbreviated:
        return ""
    if tie_label is None:
        return abbreviated
    return f"{abbreviated} [{tie_label}]"


def _abbreviated_name(name: str) -> str:
    """Return the rounded trailing wavelength of a component name, or the name unchanged."""
    tokens = name.split()
    if not tokens:
        return ""
    try:
        wavelength = float(tokens[-1])
    except ValueError:
        return name
    return str(round(wavelength))
