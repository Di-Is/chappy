"""Renderer abstraction for plotting backends."""

from __future__ import annotations

from .base_renderer import AxisConfig, PlotStyle, PlotType
from .curve_display_resolution import CurveDisplayResolutionOwner
from .matplotlib_renderer import MatplotlibRenderer
from .range_policy import ObservedRangePolicy, YAxisBounds
from .spectrum_curves import SpectrumCurveOwner
from .style_registry import PlotTheme, StyleRegistry, ThemeColors, ThemeConfig, get_style_registry

__all__ = [
    "AxisConfig",
    "CurveDisplayResolutionOwner",
    "MatplotlibRenderer",
    "ObservedRangePolicy",
    "PlotStyle",
    "PlotTheme",
    "PlotType",
    "SpectrumCurveOwner",
    "StyleRegistry",
    "ThemeColors",
    "ThemeConfig",
    "YAxisBounds",
    "get_style_registry",
]
