"""Core components for plotting functionality.

This module contains core components extracted from the monolithic plot classes
to improve maintainability and code reuse.
"""

from __future__ import annotations

from chappy.plotting.core.plot_config import PlotConfig
from chappy.plotting.core.spectrum_data_store import SpectrumPlotDataStore

__all__ = ["PlotConfig", "SpectrumPlotDataStore"]
