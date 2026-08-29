"""Protocol definitions for GUI module."""

from .common import MainWindowShellPort, MouseEvent, ViewWithSettings
from .interaction_overlay import (
    AbsorberDragBeginOverlayProtocol,
    AbsorberDragFinishOverlayProtocol,
    AbsorberDragOverlayProtocol,
    AbsorberDragUpdateOverlayProtocol,
    InteractionOverlayProtocol,
    MaskSelectionOverlayProtocol,
    RectZoomOverlayProtocol,
)
from .plotting import PlotItemProtocol, PlotWidgetProtocol, RendererProtocol, SpectrumPlotWidget
from .velocity_mode import VelocityInteractionProvider

__all__ = [
    "AbsorberDragBeginOverlayProtocol",
    "AbsorberDragFinishOverlayProtocol",
    "AbsorberDragOverlayProtocol",
    "AbsorberDragUpdateOverlayProtocol",
    "InteractionOverlayProtocol",
    "MainWindowShellPort",
    "MaskSelectionOverlayProtocol",
    "MouseEvent",
    "PlotItemProtocol",
    "PlotWidgetProtocol",
    "RectZoomOverlayProtocol",
    "RendererProtocol",
    "SpectrumPlotWidget",
    "VelocityInteractionProvider",
    "ViewWithSettings",
]
