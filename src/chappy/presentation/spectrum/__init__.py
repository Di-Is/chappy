"""Presentation helpers for spectrum workflows."""

from chappy.presentation.spectrum.display_options import (
    DEFAULT_SPECTRUM_DISPLAY_OPTIONS,
    SpectrumDisplayOptions,
)
from chappy.presentation.spectrum.marker_label import (
    format_abbreviated_component_marker_label,
    format_component_marker_label,
)
from chappy.presentation.spectrum.model_window_builder import ModelWindowBuilder
from chappy.presentation.spectrum.plot_display_command import SpectrumPlotDisplayCommand
from chappy.presentation.spectrum.plot_inputs import AbsorptionMarkerInput
from chappy.presentation.spectrum.spectrum_render_dto import (
    SpectrumComponentCurve,
    SpectrumRenderDTO,
    SpectrumRenderDTOAssembler,
)
from chappy.presentation.spectrum.visual_tokens import (
    COMPONENT_CURVE_COLORS,
    ComponentCurveVisuals,
    component_curve_color,
)

__all__ = [
    "COMPONENT_CURVE_COLORS",
    "DEFAULT_SPECTRUM_DISPLAY_OPTIONS",
    "AbsorptionMarkerInput",
    "ComponentCurveVisuals",
    "ModelWindowBuilder",
    "SpectrumComponentCurve",
    "SpectrumDisplayOptions",
    "SpectrumPlotDisplayCommand",
    "SpectrumRenderDTO",
    "SpectrumRenderDTOAssembler",
    "component_curve_color",
    "format_abbreviated_component_marker_label",
    "format_component_marker_label",
]
