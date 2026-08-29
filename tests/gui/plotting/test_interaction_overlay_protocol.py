"""Protocol compliance tests for interaction overlays."""

from __future__ import annotations

from chappy.gui.protocols import InteractionOverlayProtocol
from chappy.gui.adapters.plotting import MatplotlibSpectrumPlot


def test_matplotlib_plot_implements_interaction_overlay_protocol() -> None:
    """Ensure MatplotlibSpectrumPlot implements InteractionOverlayProtocol."""
    assert issubclass(MatplotlibSpectrumPlot, InteractionOverlayProtocol)
