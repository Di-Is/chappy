"""User-controlled spectrum display toggles shared across shell and plot layers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class SpectrumDisplayOptions:
    """Describe which optional spectrum curves the user wants rendered.

    Attributes:
        show_error_spectrum: Whether the observed error curve is drawn.
        show_component_profiles: Whether per-component profile curves are drawn.
    """

    show_error_spectrum: bool = True
    show_component_profiles: bool = False


DEFAULT_SPECTRUM_DISPLAY_OPTIONS: Final = SpectrumDisplayOptions()
