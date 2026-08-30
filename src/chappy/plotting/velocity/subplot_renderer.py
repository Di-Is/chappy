"""Rendering adapter for velocity subplot widgets."""

from __future__ import annotations

import math
from contextlib import suppress
from typing import TYPE_CHECKING

from matplotlib.layout_engine import ConstrainedLayoutEngine

from chappy.plotting.component_labels import place_rotated_component_labels
from chappy.plotting.renderers.base_renderer import PlotStyle

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    import numpy as np
    from matplotlib.axes import Axes
    from matplotlib.backend_bases import Event
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from matplotlib.text import Annotation
    from numpy.typing import NDArray

    from chappy.plotting.component_labels import ComponentLabelEntry
    from chappy.plotting.matplotlib_spectrum_plot_facade import MatplotlibSpectrumPlotFacade
    from chappy.presentation.spectrum import SpectrumComponentCurve
    from chappy.presentation.velocity import VelocityAnalysisBounds

_COMPONENT_MARKER_COLOR = "#2E7D32"


class VelocitySubplotRenderer:
    """Own Matplotlib rendering details for a velocity subplot."""

    def __init__(self, plot_widget: MatplotlibSpectrumPlotFacade) -> None:
        """Create a renderer adapter for the supplied plot widget."""
        self._plot_widget = plot_widget
        layout_engine = plot_widget.renderer.require_figure().get_layout_engine()
        if isinstance(layout_engine, ConstrainedLayoutEngine):
            layout_engine.set(w_pad=0.02, h_pad=0.02)
        self._mask_patches: list[Patch] = []
        self._center_lines: list[Line2D] = []
        self._component_markers: list[tuple[Line2D, Annotation]] = []
        self._analysis_boundary_lines: list[Line2D] = []
        self._analysis_out_of_view_annotation: Annotation | None = None
        self._drag_overlay_line: Line2D | None = None
        self._connection_ids: list[int] = []
        self._tick_labels_x = True
        self._tick_labels_y = True

    def connect_mouse_events(
        self,
        on_press: Callable[[Event], None],
        on_move: Callable[[Event], None],
        on_release: Callable[[Event], None],
    ) -> bool:
        """Connect Matplotlib mouse events to callbacks."""
        self.disconnect_mouse_events()
        canvas = self._plot_widget.renderer.require_figure().canvas
        self._connection_ids = [
            canvas.mpl_connect("button_press_event", on_press),
            canvas.mpl_connect("motion_notify_event", on_move),
            canvas.mpl_connect("button_release_event", on_release),
        ]
        return True

    def disconnect_mouse_events(self) -> None:
        """Disconnect Matplotlib mouse callbacks."""
        canvas = self._plot_widget.renderer.require_figure().canvas
        for connection_id in self._connection_ids:
            canvas.mpl_disconnect(connection_id)
        self._connection_ids.clear()

    def clear_mask_patches(self) -> None:
        """Clear previously rendered mask patches."""
        for patch in self._mask_patches:
            with suppress(Exception):
                patch.remove()
        self._mask_patches.clear()

    def add_mask_region(
        self,
        velocity_min: float,
        velocity_max: float,
        color: str,
        *,
        alpha: float = 0.25,
        zorder: int = -5,
    ) -> None:
        """Draw a masked velocity span."""
        axes = self._require_axes()
        patch = axes.axvspan(velocity_min, velocity_max, alpha=alpha, color=color, zorder=zorder)
        self._mask_patches.append(patch)

    def add_center_line(
        self,
        velocity: float,
        *,
        color: str = "yellow",
        linestyle: str = "--",
        alpha: float = 0.7,
        linewidth: float = 1.0,
        zorder: int = 10,
        label: str | None = None,
    ) -> None:
        """Add a vertical center line at the specified velocity."""
        line = self._plot_widget.renderer.add_vertical_line(
            f"center_{velocity:.2f}",
            velocity,
            style=PlotStyle(color=color, line_style=linestyle, alpha=alpha, line_width=linewidth),
            label=label,
        )
        line.set_zorder(zorder)
        self._center_lines.append(line)

    def clear_center_lines(self) -> None:
        """Remove all center lines from the subplot."""
        self.clear_drag_overlay()
        for line in self._center_lines:
            with suppress(Exception):
                line.remove()
        self._center_lines.clear()

    def set_analysis_bounds(
        self, bounds: VelocityAnalysisBounds | None, *, out_of_view_message: str | None
    ) -> None:
        """Render analysis boundaries separately from the display X range."""
        self.clear_analysis_bounds()
        if bounds is None:
            return

        axes = self._require_axes()
        for boundary in (bounds.lower_kms, bounds.upper_kms):
            line = axes.axvline(
                boundary,
                color="#7E57C2",
                linestyle="--",
                alpha=0.8,
                linewidth=1.0,
                zorder=4,
                label="Analysis boundary",
            )
            line.set_gid("velocity-analysis-boundary")
            self._analysis_boundary_lines.append(line)

        if out_of_view_message is not None:
            self._analysis_out_of_view_annotation = axes.annotate(
                f"↔ {out_of_view_message}",
                xy=(0.5, 0.98),
                xycoords="axes fraction",
                ha="center",
                va="top",
                fontsize=7,
                color="#5E35B1",
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.8, "pad": 1.5},
                zorder=20,
            )
        self._plot_widget.renderer.require_figure().canvas.draw_idle()

    def clear_analysis_bounds(self) -> None:
        """Remove analysis boundary and out-of-view artists."""
        for line in self._analysis_boundary_lines:
            with suppress(Exception):
                line.remove()
        self._analysis_boundary_lines.clear()
        if self._analysis_out_of_view_annotation is not None:
            with suppress(Exception):
                self._analysis_out_of_view_annotation.remove()
        self._analysis_out_of_view_annotation = None

    def analysis_boundary_count(self) -> int:
        """Return the number of rendered analysis boundary artists."""
        return len(self._analysis_boundary_lines)

    def analysis_out_of_view_text(self) -> str | None:
        """Return the current textual out-of-view indication."""
        if self._analysis_out_of_view_annotation is None:
            return None
        return self._analysis_out_of_view_annotation.get_text()

    def center_lines(self) -> tuple[Line2D, ...]:
        """Return center-line artists owned by this renderer."""
        return tuple(self._center_lines)

    def set_component_markers(self, markers: Sequence[ComponentLabelEntry]) -> None:
        """Draw a vertical marker and label for each absorber component."""
        self.clear_component_markers()
        axes = self._require_axes()
        lines = [
            axes.axvline(
                marker.x,
                color=marker.color or _COMPONENT_MARKER_COLOR,
                linestyle=":",
                alpha=0.6,
                linewidth=1.0,
                zorder=5,
            )
            for marker in markers
        ]
        annotations = place_rotated_component_labels(axes, markers, color=_COMPONENT_MARKER_COLOR)
        self._component_markers = list(zip(lines, annotations, strict=True))
        self._plot_widget.renderer.require_figure().canvas.draw_idle()

    def set_component_profile_curves(self, curves: Sequence[SpectrumComponentCurve]) -> None:
        """Draw one transmission curve per absorber component."""
        self._plot_widget.set_component_profile_spectra(tuple(curves))

    def clear_component_profile_curves(self) -> None:
        """Remove all component transmission curves from the subplot."""
        self._plot_widget.clear_component_profiles()

    def component_marker_count(self) -> int:
        """Return the number of currently rendered component markers."""
        return len(self._component_markers)

    def emphasized_marker_labels(self) -> tuple[str, ...]:
        """Return the marker label texts currently drawn with selection emphasis."""
        return tuple(
            annotation.get_text()
            for _line, annotation in self._component_markers
            if annotation.get_fontweight() == "bold"
        )

    def clear_component_markers(self) -> None:
        """Remove all component markers from the subplot."""
        for line, annotation in self._component_markers:
            with suppress(Exception):
                line.remove()
            with suppress(Exception):
                annotation.remove()
        self._component_markers.clear()

    def set_data(
        self,
        velocity: NDArray[np.float64],
        flux: NDArray[np.float64],
        error: NDArray[np.float64] | None,
        display_half_width_kms: float,
    ) -> bool:
        """Render observed velocity-space data and return whether it was drawn."""
        self._plot_widget.clear_residual()
        if velocity.size == 0:
            return False

        self._plot_widget.set_observed_spectrum(velocity, flux, error)

        limit = abs(display_half_width_kms) if math.isfinite(display_half_width_kms) else None
        if limit:
            self._require_axes().set_xlim(-limit, limit)
        self._apply_tick_label_visibility()
        return True

    def set_tick_labels_visible(self, *, x: bool, y: bool) -> None:
        """Show or hide the axis tick labels for this subplot."""
        self._tick_labels_x = x
        self._tick_labels_y = y
        self._apply_tick_label_visibility()
        self._plot_widget.renderer.require_figure().canvas.draw_idle()

    def _apply_tick_label_visibility(self) -> None:
        self._require_axes().tick_params(
            labelbottom=self._tick_labels_x, labelleft=self._tick_labels_y
        )

    def set_model_spectrum(self, velocity: NDArray[np.float64], flux: NDArray[np.float64]) -> None:
        """Render model velocity-space data."""
        self._plot_widget.set_model_spectrum(velocity, flux)

    def set_residual(self, velocity: NDArray[np.float64], residual: NDArray[np.float64]) -> None:
        """Render residual velocity-space data."""
        self._plot_widget.set_residual_data(velocity, residual)

    def get_observed_y_range(self) -> tuple[float, float] | None:
        """Return the observed-data Y range."""
        return self._plot_widget.get_observed_y_range()

    def set_flux_range(self, min_flux: float, max_flux: float) -> None:
        """Set the Y-axis flux range."""
        self._plot_widget.set_flux_range(min_flux, max_flux)

    def get_flux_range(self) -> tuple[float, float]:
        """Return the current Y-axis flux range."""
        _, _, min_flux, max_flux = self._plot_widget.renderer.get_range()
        return min_flux, max_flux

    def get_display_velocity_range(self) -> tuple[float, float]:
        """Return the current plot-local velocity X range."""
        lower, upper = self._require_axes().get_xlim()
        return float(lower), float(upper)

    def update_drag_overlay(self, velocity: float) -> None:
        """Update the drag overlay line position."""
        axes = self._plot_widget.renderer.require_axes()
        if self._drag_overlay_line is None:
            self._drag_overlay_line = axes.axvline(
                velocity, color="yellow", linestyle="--", alpha=0.7, zorder=100
            )
        else:
            self._drag_overlay_line.set_xdata([velocity, velocity])

        self._plot_widget.renderer.require_figure().canvas.draw_idle()

    def clear_drag_overlay(self) -> None:
        """Remove the drag overlay line."""
        if self._drag_overlay_line is None:
            return

        with suppress(Exception):
            self._drag_overlay_line.remove()
        self._drag_overlay_line = None

        with suppress(Exception):
            self._plot_widget.renderer.require_figure().canvas.draw_idle()

    def has_drag_overlay(self) -> bool:
        """Return whether a drag overlay is currently visible."""
        return self._drag_overlay_line is not None

    def _require_axes(self) -> Axes:
        """Return initialized Matplotlib axes or raise an invariant error."""
        return self._plot_widget.renderer.require_axes()
