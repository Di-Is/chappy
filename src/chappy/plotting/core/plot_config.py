"""Plot configuration constants and defaults.

This module contains all plotting configuration constants extracted from
the monolithic plot classes to improve maintainability and consistency.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PlotColors:
    """Standard colors for spectrum plotting."""

    OBSERVED_DATA: str = "#FFFFFF"  # White - observed spectrum data


@dataclass
class PlotStyles:
    """Plot line and marker styles."""

    DATA_LINE_WIDTH: int = 1


class PlotConfig:
    """Central configuration for plotting.

    This class provides access to all plot configuration values.
    It can be extended to support loading from config files or
    environment variables.
    """

    def __init__(self) -> None:
        """Initialize plot configuration with defaults."""
        self.colors = PlotColors()
        self.styles = PlotStyles()
