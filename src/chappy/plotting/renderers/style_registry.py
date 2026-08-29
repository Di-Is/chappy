"""Style registry for plot themes and configurations.

This module provides a centralized registry of styles for different plot themes
(default, dark, publication, etc.) and maintains consistency across renderers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto

from chappy.presentation.spectrum.visual_tokens import (
    ContinuumControlPointVisuals,
    SpectrumVisuals,
)

from .base_renderer import MatplotlibDrawStyle, PlotStyle, PlotType

logger = logging.getLogger(__name__)


class PlotTheme(Enum):
    """Available plot themes."""

    DEFAULT = auto()  # Default dark theme
    DARK = auto()  # High contrast dark theme
    LIGHT = auto()  # Light theme
    PUBLICATION = auto()  # Publication-ready black & white
    COLORBLIND = auto()  # Colorblind-friendly palette
    CUSTOM = auto()  # User-defined theme


@dataclass
class ThemeColors:
    """Color definitions for a theme."""

    background: str = "black"
    foreground: str = "white"
    grid: str = "gray"

    # Plot element colors
    spectrum: str = "white"
    model: str = "red"
    residual: str = "yellow"
    continuum: str = "cyan"
    marker: str = "blue"

    # UI element colors
    selection: str = "yellow"
    error: str = "red"
    warning: str = "orange"
    info: str = "cyan"


@dataclass
class ThemeConfig:
    """Complete theme configuration."""

    name: str
    colors: ThemeColors
    line_widths: dict[str, float] = field(default_factory=dict)
    alpha_values: dict[str, float] = field(default_factory=dict)
    grid_alpha: float = 0.3


class StyleRegistry:
    """Registry of plot styles and themes."""

    def __init__(self) -> None:
        """Initialize the style registry."""
        self._themes: dict[PlotTheme, ThemeConfig] = self._create_default_themes()
        self._current_theme = PlotTheme.DEFAULT
        self._custom_themes: dict[str, ThemeConfig] = {}
        self._active_custom_theme: str | None = None

    def get_theme_config(self, theme: PlotTheme | None = None) -> ThemeConfig:
        """Get configuration for a theme.

        Args:
            theme: Theme to get config for (uses current if None)

        Returns:
            Theme configuration
        """
        if theme is None:
            theme = self._current_theme

        # Check if using custom theme
        if (
            theme == PlotTheme.CUSTOM
            and self._active_custom_theme
            and self._active_custom_theme in self._custom_themes
        ):
            return self._custom_themes[self._active_custom_theme]

        return self._themes.get(theme, self._themes[PlotTheme.DEFAULT])

    def get_plot_style(self, plot_type: PlotType, theme: PlotTheme | None = None) -> PlotStyle:
        """Get plot style for a specific plot type.

        Args:
            plot_type: Type of plot
            theme: Theme to use (uses current if None)

        Returns:
            Plot style configuration
        """
        config = self.get_theme_config(theme)
        colors = config.colors

        # Map plot types to color attributes
        color_map = {
            PlotType.SPECTRUM: colors.spectrum,
            PlotType.MODEL: colors.model,
            PlotType.RESIDUAL: colors.residual,
            PlotType.CONTINUUM: colors.continuum,
            PlotType.MARKER: colors.marker,
        }

        color = color_map.get(plot_type, colors.foreground)

        # Get line width
        width_key = plot_type.name.lower()
        line_width = config.line_widths.get(width_key, 1.0)

        # Get alpha
        alpha_key = plot_type.name.lower()
        alpha = config.alpha_values.get(alpha_key, 1.0)

        # Special styling for certain plot types
        line_style = "-"  # solid
        if plot_type == PlotType.MARKER:
            line_style = "--"  # dashed

        drawstyle: MatplotlibDrawStyle | None = None
        if plot_type == PlotType.RESIDUAL:
            drawstyle = SpectrumVisuals.RESIDUAL_DRAWSTYLE

        # Set drawing order (zorder) - higher values drawn on top
        # Drawing order from bottom to top: SPECTRUM, RESIDUAL, CONTINUUM, MODEL, MARKER
        zorder_map = {
            PlotType.MODEL: 4,  # Model (red) - top layer
            PlotType.RESIDUAL: 1,  # Residual - above observed data
            PlotType.SPECTRUM: SpectrumVisuals.OBSERVED_Z_ORDER,
            PlotType.CONTINUUM: SpectrumVisuals.CONTINUUM_Z_ORDER,
            PlotType.MARKER: 6,  # Markers - highest
        }
        zorder = zorder_map.get(plot_type, 0)

        return PlotStyle(
            color=color,
            line_width=line_width,
            line_style=line_style,
            alpha=alpha,
            drawstyle=drawstyle,
            zorder=zorder,
        )

    def _create_default_themes(self) -> dict[PlotTheme, ThemeConfig]:
        """Create default theme configurations.

        Returns:
            Dictionary of themes
        """
        themes = {}

        # Default dark theme
        themes[PlotTheme.DEFAULT] = ThemeConfig(
            name="Default",
            colors=ThemeColors(
                background="#000000",
                foreground="#FFFFFF",
                grid="#444444",
                spectrum=SpectrumVisuals.OBSERVED_COLOR,
                model="#FF0000",
                residual="#FFFF00",
                continuum=SpectrumVisuals.CONTINUUM_COLOR,
                marker=ContinuumControlPointVisuals.MARKER_COLOR,
            ),
            line_widths={
                "spectrum": SpectrumVisuals.OBSERVED_LINE_WIDTH,
                "model": 2.0,
                "residual": 1.0,
                "continuum": SpectrumVisuals.CONTINUUM_LINE_WIDTH,
                "marker": 1.0,
            },
            alpha_values={
                "spectrum": 1.0,
                "model": 1.0,
                "residual": 1.0,
                "continuum": 1.0,
                "marker": 0.8,
            },
        )

        # High contrast dark theme
        themes[PlotTheme.DARK] = ThemeConfig(
            name="Dark",
            colors=ThemeColors(
                background="#000000",
                foreground="#FFFFFF",
                spectrum="#FFFFFF",
                model="#FF0000",
                residual="#FFFF00",  # Changed from green to yellow
                continuum="#00FFFF",
                marker="#0080FF",
            ),
            line_widths={
                "spectrum": 1.5,
                "model": 2.5,
                "residual": 1.5,
                "continuum": 2.0,
                "marker": 1.5,
            },
            alpha_values={
                "spectrum": 1.0,
                "model": 1.0,
                "residual": 1.0,
                "continuum": 1.0,
                "marker": 0.8,
            },
            grid_alpha=0.4,
        )

        # Light theme
        themes[PlotTheme.LIGHT] = ThemeConfig(
            name="Light",
            colors=ThemeColors(
                background="white",
                foreground="black",
                grid="#CCCCCC",
                spectrum="black",
                model="#DC143C",
                residual="#FFD700",  # Changed from green to gold/yellow
                continuum="#4682B4",
                marker="#9370DB",
            ),
            line_widths={
                "spectrum": 1.0,
                "model": 2.0,
                "residual": 1.0,
                "continuum": 1.5,
                "marker": 1.0,
            },
        )

        # Publication theme (black & white)
        themes[PlotTheme.PUBLICATION] = ThemeConfig(
            name="Publication",
            colors=ThemeColors(
                background="white",
                foreground="black",
                grid="black",
                spectrum="black",
                model="black",
                residual="black",
                continuum="black",
                marker="black",
            ),
            line_widths={
                "spectrum": 1.0,
                "model": 2.0,
                "residual": 1.0,
                "continuum": 1.5,
                "marker": 1.0,
            },
            alpha_values={
                "spectrum": 1.0,
                "model": 1.0,
                "residual": 0.7,
                "continuum": 0.8,
                "marker": 0.6,
            },
            grid_alpha=0.2,
        )

        # Colorblind-friendly theme
        themes[PlotTheme.COLORBLIND] = ThemeConfig(
            name="Colorblind",
            colors=ThemeColors(
                background="#FFFFFF",
                foreground="#000000",
                grid="#999999",
                spectrum="#000000",
                model="#E69F00",  # Orange
                residual="#56B4E9",  # Sky blue
                continuum="#009E73",  # Bluish green
                marker="#0072B2",  # Blue
            ),
            line_widths={
                "spectrum": 1.5,
                "model": 2.0,
                "residual": 1.5,
                "continuum": 1.5,
                "marker": 1.5,
            },
        )

        return themes


# Singleton instance
_style_registry = StyleRegistry()


def get_style_registry() -> StyleRegistry:
    """Get the global style registry instance.

    Returns:
        StyleRegistry instance
    """
    return _style_registry
