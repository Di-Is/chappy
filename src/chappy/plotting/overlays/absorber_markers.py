"""Absorber marker overlay owner for Matplotlib spectrum plots."""

from __future__ import annotations

import math
from contextlib import suppress
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, TypedDict

from chappy.plotting.component_labels import ComponentLabelEntry, place_rotated_component_labels
from chappy.plotting.renderers import PlotStyle
from chappy.presentation.spectrum import (
    format_abbreviated_component_marker_label,
    format_component_marker_label,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from matplotlib.axes import Axes
    from matplotlib.backend_bases import FigureCanvasBase
    from matplotlib.lines import Line2D
    from matplotlib.text import Annotation

    from chappy.presentation.spectrum import AbsorptionMarkerInput

_LABEL_COLOR = "#7a6000"
_MARKER_LINE_COLOR = "yellow"


class AbsorptionMarkerPayload(TypedDict):
    """Stored parameters for an absorption marker."""

    name: str
    rest_wavelength: float
    redshift: float
    column_density: float
    b_parameter: float
    oscillator_strength: float
    gamma: float
    tie_label: str | None
    color: str | None


class MarkerRenderer(Protocol):
    """Renderer API required by absorber marker overlays."""

    def add_vertical_line(
        self, name: str, x: float, style: PlotStyle | None = None, label: str | None = None
    ) -> Line2D:
        """Add a vertical line marker."""
        ...

    def update_vertical_line_position(self, name: str, x: float) -> bool:
        """Update the position of a vertical line."""
        ...

    def remove_vertical_line(self, name: str) -> bool:
        """Remove a vertical line if present."""
        ...

    def get_vertical_line(self, name: str) -> Line2D | None:
        """Return a vertical line by name."""
        ...


@dataclass
class AbsorberMarkerOverlay:
    """Own absorber marker state and drag-line rendering."""

    renderer: MarkerRenderer
    canvas: FigureCanvasBase
    axes: Axes
    band_top_provider: Callable[[], float]
    markers: dict[str, AbsorptionMarkerPayload] = field(default_factory=dict)
    _labels: dict[str, Annotation] = field(default_factory=dict)
    _selected_component_id: str | None = None
    _labels_visible: bool = True

    def add_marker(self, marker: AbsorptionMarkerInput, *, component_id: str) -> None:
        """Store one marker and render its vertical line (labels via refresh_component_labels)."""
        self.markers[component_id] = {
            "name": marker.name,
            "rest_wavelength": marker.rest_wavelength,
            "redshift": marker.redshift,
            "column_density": marker.column_density,
            "b_parameter": marker.b_parameter,
            "oscillator_strength": marker.oscillator_strength,
            "gamma": marker.gamma,
            "tie_label": marker.tie_label,
            "color": marker.color,
        }
        self.renderer.add_vertical_line(
            self._marker_name(component_id),
            marker.rest_wavelength * (1.0 + marker.redshift),
            style=self._line_style(component_id),
            label=None,
        )

    def refresh_component_labels(self) -> None:
        """Re-place all component name labels once for the current marker set."""
        self._clear_labels()
        component_ids = list(self.markers)
        entries = [self._label_entry(component_id) for component_id in component_ids]
        annotations = place_rotated_component_labels(
            self.axes, entries, color=_LABEL_COLOR, band_top=self.band_top_provider()
        )
        if not self._labels_visible:
            for annotation in annotations:
                annotation.set_visible(False)
        self._labels = dict(zip(component_ids, annotations, strict=True))
        self.canvas.draw_idle()

    def _label_entry(self, component_id: str) -> ComponentLabelEntry:
        """Return the label request for one stored marker."""
        data = self.markers[component_id]
        return ComponentLabelEntry(
            x=data["rest_wavelength"] * (1.0 + data["redshift"]),
            text=format_component_marker_label(data["name"], data["tie_label"]),
            short_text=format_abbreviated_component_marker_label(data["name"], data["tie_label"]),
            selected=component_id == self._selected_component_id,
            color=data["color"],
        )

    def _line_style(self, component_id: str) -> PlotStyle:
        """Return the vertical-line style for one marker, stored or not yet added."""
        marker = self.markers.get(component_id)
        color = (marker["color"] if marker is not None else None) or _MARKER_LINE_COLOR
        return PlotStyle(color=color, line_style="--", alpha=0.7)

    def set_selected_component_id(self, component_id: str | None) -> None:
        """Emphasise the named component's label and re-place the current label set."""
        self._selected_component_id = component_id
        self.refresh_component_labels()

    def _clear_labels(self) -> None:
        for annotation in self._labels.values():
            with suppress(Exception):
                annotation.remove()
        self._labels.clear()

    def update_redshift(self, component_id: str, redshift: float) -> None:
        """Update one marker redshift and redraw its vertical line."""
        marker_data = self.markers.get(component_id)
        if marker_data is None:
            return
        marker_data["redshift"] = redshift
        observed_wavelength = marker_data["rest_wavelength"] * (1.0 + redshift)
        if self.renderer.update_vertical_line_position(
            self._marker_name(component_id), observed_wavelength
        ):
            annotation = self._labels.get(component_id)
            if annotation is not None:
                annotation.xy = (observed_wavelength, annotation.xy[1])
            self.canvas.draw_idle()

    def absorber_at_position(self, wavelength: float, tolerance: float) -> str | None:
        """Return the marker identifier near the given wavelength."""
        for component_id, data in self.markers.items():
            observed_wavelength = data["rest_wavelength"] * (1.0 + data["redshift"])
            if math.fabs(wavelength - observed_wavelength) <= tolerance:
                return component_id
        return None

    def begin_drag(self, component_id: str, wavelength: float) -> None:
        """Create or refresh a temporary drag line while hiding the original marker."""
        marker_name = self._marker_name(component_id)
        temp_name = self._temp_name(component_id)
        original_line = self.renderer.get_vertical_line(marker_name)
        if original_line is not None and original_line.get_visible():
            original_line.set_visible(False)
        annotation = self._labels.get(component_id)
        if annotation is not None:
            annotation.set_visible(False)

        temp_line = self.renderer.get_vertical_line(temp_name)
        if temp_line is not None:
            temp_line.set_xdata([wavelength])
        else:
            self.renderer.add_vertical_line(
                temp_name, wavelength, style=self._line_style(component_id), label=None
            )
        self.canvas.draw_idle()

    def update_drag(self, component_id: str, wavelength: float) -> None:
        """Update or create a temporary drag line while hiding the original marker."""
        self.begin_drag(component_id, wavelength)

    def finish_drag(self, component_id: str) -> None:
        """Remove the temporary drag line and show the original marker."""
        temp_name = self._temp_name(component_id)
        self.renderer.remove_vertical_line(temp_name)

        original_line = self.renderer.get_vertical_line(self._marker_name(component_id))
        if original_line is not None:
            original_line.set_visible(True)
        self.refresh_component_labels()

    def toggle(self, show: bool) -> None:
        """Set marker visibility for all rendered markers."""
        self._labels_visible = show
        for component_id in self.markers:
            line = self.renderer.get_vertical_line(self._marker_name(component_id))
            if line is not None:
                line.set_visible(show)
        for annotation in self._labels.values():
            annotation.set_visible(show)
        self.canvas.draw_idle()

    def clear(self) -> None:
        """Remove all rendered markers and temporary drag lines."""
        for component_id in list(self.markers.keys()):
            self.renderer.remove_vertical_line(self._marker_name(component_id))
            self.renderer.remove_vertical_line(self._temp_name(component_id))

        self._clear_labels()
        self.markers.clear()
        self.canvas.draw_idle()

    @staticmethod
    def _marker_name(component_id: str) -> str:
        return f"marker_{component_id}"

    @staticmethod
    def _temp_name(component_id: str) -> str:
        return f"_temp_drag_{component_id}"
