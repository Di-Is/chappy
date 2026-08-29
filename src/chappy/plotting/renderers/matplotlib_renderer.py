"""Matplotlib implementation of the renderer interface."""

from __future__ import annotations

import copy
import logging
import platform
from collections.abc import Callable
from typing import TYPE_CHECKING

from matplotlib import font_manager, rcParams
from matplotlib.backend_bases import FigureCanvasBase
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from .base_renderer import AxisConfig, CurveArtist, PlotStyle, PlotType
from .style_registry import get_style_registry

if TYPE_CHECKING:
    import numpy as np
    from matplotlib.axes import Axes
    from matplotlib.collections import PolyCollection
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)

# Display margin constants
# These margins ensure data is not drawn at the exact edges of the plot
DEFAULT_X_MARGIN = 0.02  # 2% margin for wavelength (X) axis
DEFAULT_Y_MARGIN = 0.06  # 6% margin for flux (Y) axis


MatplotlibCanvasFactory = Callable[[Figure], FigureCanvasBase]


class MatplotlibRenderer:
    """Matplotlib implementation of the renderer interface."""

    def __init__(
        self,
        *,
        canvas_factory: MatplotlibCanvasFactory | None = None,
        axis_label_font: str | None = None,
        constrained_layout: bool = False,
        tick_labelsize: float | None = None,
    ) -> None:
        """Initialize the Matplotlib renderer.

        Args:
            canvas_factory: Optional factory that binds a Matplotlib canvas to a figure.
            axis_label_font: Optional GUI-selected font family for axis labels.
            constrained_layout: Size the plot margins from rendered tick labels
                instead of fixed figure-relative fractions.
            tick_labelsize: Optional tick label font size in points.
        """
        super().__init__()
        self.figure: Figure | None = None
        self.canvas: FigureCanvasBase | None = None
        self.axes: Axes | None = None
        self._region_items: dict[str, PolyCollection | Patch] = {}
        self.axvline_items: dict[str, Line2D] = {}
        self.plot_items: dict[str, object] = {}
        self._axis_configs: dict[str, AxisConfig] = {}
        self._canvas_factory = canvas_factory or self._create_agg_canvas
        self._axis_label_font = axis_label_font or self._determine_axis_label_font()
        self._constrained_layout = constrained_layout
        self._tick_labelsize = tick_labelsize
        # Full-resolution steps-mid spectra redraw ~3x faster at the maximum
        # sub-pixel simplification threshold (default 1/9 px).
        rcParams["path.simplify_threshold"] = 1.0

    def create_plot_widget(self) -> FigureCanvasBase:
        """Create and return the Matplotlib canvas.

        Returns:
            Matplotlib canvas instance.
        """
        self.figure = Figure(
            figsize=(10, 6),
            facecolor="black",
            layout="constrained" if self._constrained_layout else None,
        )
        self.canvas = self._canvas_factory(self.figure)
        self.axes = self.figure.add_subplot(111)
        if not self._constrained_layout:
            # Reduce surrounding whitespace while keeping roughly balanced framing.
            self.figure.subplots_adjust(left=0.08, right=0.98, bottom=0.1, top=0.985)
        # Set default display margins (View layer responsibility)
        self.axes.margins(x=DEFAULT_X_MARGIN, y=DEFAULT_Y_MARGIN)

        # Configure default appearance
        self._apply_default_axes_style()

        return self.canvas

    def _create_agg_canvas(self, figure: Figure) -> FigureCanvasBase:
        """Create the default Qt-free Matplotlib canvas."""
        return FigureCanvasAgg(figure)

    def require_figure(self) -> Figure:
        """Return the initialized figure or raise a composition error."""
        if self.figure is None:
            msg = "Matplotlib figure is not initialized. Call create_plot_widget first."
            raise RuntimeError(msg)
        return self.figure

    def require_canvas(self) -> FigureCanvasBase:
        """Return the initialized canvas or raise a composition error."""
        if self.canvas is None:
            msg = "Matplotlib canvas is not initialized. Call create_plot_widget first."
            raise RuntimeError(msg)
        return self.canvas

    def require_axes(self) -> Axes:
        """Return the initialized axes or raise a composition error."""
        if self.axes is None:
            msg = "Matplotlib axes are not initialized. Call create_plot_widget first."
            raise RuntimeError(msg)
        return self.axes

    def get_style(self, plot_type: PlotType) -> PlotStyle:
        """Return the default style for ``plot_type``."""
        return get_style_registry().get_plot_style(plot_type)

    def add_curve(
        self,
        name: str,
        x: NDArray[np.float64],
        y: NDArray[np.float64],
        plot_type: PlotType = PlotType.SPECTRUM,
        style: PlotStyle | None = None,
    ) -> Line2D:
        """Add a curve to the plot.

        Args:
            name: Unique identifier for the curve
            x: X-axis data
            y: Y-axis data
            plot_type: Type of plot
            style: Style configuration (uses default if None)

        Returns:
            The created Line2D object
        """
        axes = self.require_axes()

        # Use provided style or default for plot type
        if style is None:
            style = self.get_style(plot_type)

        # Convert style to Matplotlib parameters
        color = self._parse_color(style.color)
        linestyle = style.line_style
        linewidth = style.line_width
        alpha = style.alpha
        drawstyle = style.drawstyle

        # Create line with zorder for layer control
        (line,) = axes.plot(
            x,
            y,
            color=color,
            linestyle=linestyle,
            linewidth=linewidth,
            alpha=alpha,
            label=name,
            zorder=style.zorder,
        )

        if drawstyle:
            line.set_drawstyle(drawstyle)

        # Add markers if specified
        if style.marker_style:
            line.set_marker(style.marker_style)
            line.set_markersize(style.marker_size)

        # Store reference
        self.plot_items[name] = line

        self.require_canvas().draw_idle()
        return line

    def update_curve(
        self, name: str, x: NDArray[np.float64] | None = None, y: NDArray[np.float64] | None = None
    ) -> None:
        """Update an existing curve's data.

        Args:
            name: Identifier of the curve to update
            x: New X-axis data (if None, keeps existing)
            y: New Y-axis data (if None, keeps existing)
        """
        if name not in self.plot_items:
            msg = f"Curve '{name}' is not registered"
            raise KeyError(msg)

        line = self.plot_items[name]
        if not isinstance(line, CurveArtist):
            msg = f"Curve '{name}' does not support line updates"
            raise TypeError(msg)

        if x is not None and y is not None:
            line.set_data(x, y)
        elif x is not None:
            # Update only X data
            line.set_xdata(x)
        elif y is not None:
            # Update only Y data
            line.set_ydata(y)

        # Update axes limits if needed
        axes = self.require_axes()
        axes.relim()
        axes.autoscale_view()

        self.require_canvas().draw_idle()

    def set_curve_display_data(
        self, name: str, x: NDArray[np.float64], y: NDArray[np.float64]
    ) -> None:
        """Replace a curve's displayed vertices without rescaling axes.

        Unlike ``update_curve`` this performs no relim/autoscale and schedules
        no draw, so it is safe to call from axis-limit change callbacks.

        Args:
            name: Identifier of the curve to update.
            x: Display-resolution x data.
            y: Display-resolution y data.
        """
        if name not in self.plot_items:
            msg = f"Curve '{name}' is not registered"
            raise KeyError(msg)

        line = self.plot_items[name]
        if not isinstance(line, CurveArtist):
            msg = f"Curve '{name}' does not support line updates"
            raise TypeError(msg)

        line.set_data(x, y)

    def remove_curve(self, name: str) -> None:
        """Remove a curve from the plot.

        Args:
            name: Identifier of the curve to remove
        """
        if name not in self.plot_items:
            msg = f"Curve '{name}' is not registered"
            raise KeyError(msg)

        line = self.plot_items[name]
        if not isinstance(line, CurveArtist):
            msg = f"Curve '{name}' does not support line removal"
            raise TypeError(msg)
        line.remove()
        del self.plot_items[name]

        self.require_canvas().draw_idle()

    def add_vertical_line(
        self, name: str, x: float, style: PlotStyle | None = None, label: str | None = None
    ) -> Line2D:
        """Add a vertical line marker.

        Args:
            name: Unique identifier for the line
            x: X-coordinate of the line
            style: Style configuration
            label: Optional label for the line

        Returns:
            The created Line2D
        """
        axes = self.require_axes()

        if style is None:
            style = self.get_style(PlotType.MARKER)

        color = self._parse_color(style.color)
        linestyle = style.line_style
        linewidth = style.line_width
        alpha = style.alpha

        line = axes.axvline(
            x=x, color=color, linestyle=linestyle, linewidth=linewidth, alpha=alpha, label=label
        )

        self.axvline_items[name] = line

        self.require_canvas().draw_idle()
        return line

    def update_vertical_line_position(self, name: str, x: float) -> bool:
        """Update the position of a vertical line.

        Args:
            name: Name of the vertical line
            x: New x-coordinate

        Returns:
            True if line was found and updated, False otherwise
        """
        line = self.axvline_items.get(name)
        if line:
            line.set_xdata([x])
            return True
        return False

    def remove_vertical_line(self, name: str) -> bool:
        """Remove a vertical line if present."""
        line = self.axvline_items.pop(name, None)
        if line is None:
            return False
        line.remove()
        self.require_canvas().draw_idle()
        return True

    def get_vertical_line(self, name: str) -> Line2D | None:
        """Return a vertical line by name."""
        return self.axvline_items.get(name)

    def add_region(
        self,
        name: str,
        x_min: float,
        x_max: float,
        style: PlotStyle | None = None,
        label: str | None = None,
    ) -> PolyCollection | Patch:
        """Add a shaded region.

        Args:
            name: Unique identifier for the region
            x_min: Left boundary
            x_max: Right boundary
            style: Style configuration
            label: Optional label

        Returns:
            The created Matplotlib patch for the region
        """
        axes = self.require_axes()

        if style is None:
            style = PlotStyle(color="yellow", alpha=0.3)

        color = self._parse_color(style.color)
        alpha = style.alpha * style.fill_alpha
        zorder = style.zorder or 1

        region = axes.axvspan(
            x_min, x_max, facecolor=color, alpha=alpha, label=label, zorder=zorder
        )

        self._region_items[name] = region

        self.require_canvas().draw_idle()
        return region

    def remove_region(self, name: str) -> None:
        """Remove a previously added shaded region."""
        region = self._region_items.pop(name, None)
        if region is None:
            return
        region.remove()
        self.require_canvas().draw_idle()

    def remove_regions_with_prefix(self, prefix: str) -> None:
        """Remove all regions whose identifiers start with ``prefix``."""
        for key in list(self._region_items.keys()):
            if key.startswith(prefix):
                self.remove_region(key)

    def get_region(self, name: str) -> PolyCollection | Patch | None:
        """Return a shaded region by name.

        Args:
            name: Region identifier.

        Returns:
            Region artist when present.
        """
        return self._region_items.get(name)

    def set_axis_config(self, axis: str, config: AxisConfig) -> None:
        """Configure an axis.

        Args:
            axis: Axis identifier ('x', 'y', 'x2', 'y2')
            config: Axis configuration
        """
        axes = self.require_axes()

        # Set label
        label = config.label
        if config.units:
            label = f"{label} ({config.units})"

        if axis == "x":
            axes.set_xlabel(label)
            if config.scale:
                axes.set_xscale(config.scale)
            if config.min_value is not None and config.max_value is not None:
                axes.set_xlim(config.min_value, config.max_value)
        elif axis == "y":
            axes.set_ylabel(label)
            if config.scale:
                axes.set_yscale(config.scale)
            if config.min_value is not None and config.max_value is not None:
                axes.set_ylim(config.min_value, config.max_value)

        # Configure grid
        axes.grid(config.grid, alpha=config.grid_alpha)

        # Persist configuration for later restoration (e.g., after clear()).
        self._axis_configs[axis] = copy.copy(config)

        self._apply_axis_label_font(axis)

        self.require_canvas().draw_idle()

    def set_range(
        self,
        x_min: float | None = None,
        x_max: float | None = None,
        y_min: float | None = None,
        y_max: float | None = None,
    ) -> None:
        """Set the visible range of the plot.

        Args:
            x_min: Minimum X value
            x_max: Maximum X value
            y_min: Minimum Y value
            y_max: Maximum Y value
        """
        axes = self.require_axes()

        if x_min is not None and x_max is not None:
            axes.set_xlim(x_min, x_max)
        if y_min is not None and y_max is not None:
            axes.set_ylim(y_min, y_max)

        self.require_canvas().draw_idle()

    def get_range(self) -> tuple[float, float, float, float]:
        """Get the current visible range.

        Returns:
            Tuple of (x_min, x_max, y_min, y_max)
        """
        axes = self.require_axes()
        x_min, x_max = axes.get_xlim()
        y_min, y_max = axes.get_ylim()
        return (x_min, x_max, y_min, y_max)

    def auto_range(self) -> None:
        """Automatically set range based on data.

        This method applies display margins to the raw data range received from
        the SpectrumPlotDataStore (Model layer). Both axes now lock their margin to 0%
        to honor the raw min/max range without expansion.

        Args:
            padding: Fraction of range to add as padding to the Y axis.
        """
        axes = self.require_axes()
        axes.autoscale(enable=True, tight=False)
        axes.margins(x=0.0, y=0.0)
        self.require_canvas().draw_idle()

    def clear(self) -> None:
        """Clear all plot items."""
        axes = self.require_axes()
        axes.clear()
        self.plot_items.clear()
        self._region_items.clear()
        self.axvline_items.clear()

        # Restore default appearance
        self._apply_default_axes_style()

        # Restore previously configured axis labels, scales, and limits.
        self._restore_axis_configs()

        self.require_canvas().draw_idle()

    def dispose(self) -> None:
        """Release Matplotlib figure resources owned by this renderer."""
        if self.figure is not None:
            self.figure.clear()
        self.figure = None
        self.canvas = None
        self.axes = None
        self.plot_items.clear()
        self._region_items.clear()
        self.axvline_items.clear()
        self._axis_configs.clear()

    def _apply_default_axes_style(self) -> None:
        axes = self.require_axes()

        axes.set_facecolor("black")
        axes.grid(True, alpha=0.3, color="gray")
        axes.spines["bottom"].set_color("white")
        axes.spines["top"].set_color("white")
        axes.spines["left"].set_color("white")
        axes.spines["right"].set_color("white")
        axes.tick_params(colors="white")
        if self._tick_labelsize is not None:
            axes.tick_params(labelsize=self._tick_labelsize)
            if self._axis_label_font:
                axes.tick_params(labelfontfamily=self._axis_label_font)
        axes.xaxis.label.set_color("white")
        axes.yaxis.label.set_color("white")

        if self._axis_label_font:
            axes.xaxis.label.set_fontfamily(self._axis_label_font)
            axes.yaxis.label.set_fontfamily(self._axis_label_font)

    def _restore_axis_configs(self) -> None:
        for axis in ("x", "y", "x2", "y2"):
            config = self._axis_configs.get(axis)
            if config is not None:
                self.set_axis_config(axis, config)

    def _apply_axis_label_font(self, axis: str) -> None:
        axes = self.require_axes()

        if self._axis_label_font is None:
            self._axis_label_font = self._determine_axis_label_font()

        if not self._axis_label_font:
            return

        if axis == "x":
            axes.xaxis.label.set_fontfamily(self._axis_label_font)
        elif axis == "y":
            axes.yaxis.label.set_fontfamily(self._axis_label_font)

    def _determine_axis_label_font(self) -> str | None:
        """Return a font family that reliably renders Japanese glyphs."""
        for family in self._ordered_font_candidates():
            try:
                font_manager.findfont(
                    font_manager.FontProperties(family=family), fallback_to_default=False
                )
            except ValueError:
                logger.debug("Font '%s' not found in matplotlib, trying next candidate", family)
                continue
            rcParams["font.sans-serif"] = [family, *rcParams.get("font.sans-serif", [])]
            return family

        return None

    def _ordered_font_candidates(self) -> list[str]:
        """Return an ordered list of font families to validate for axis labels."""
        system_name = platform.system().lower()
        os_candidates = self._platform_font_candidates(system_name)
        common_candidates = self._common_font_candidates()

        candidates: list[str] = []
        candidates.extend(os_candidates)
        candidates.extend(common_candidates)

        unique_candidates: list[str] = []
        for family in candidates:
            if family and family not in unique_candidates:
                unique_candidates.append(family)
        return unique_candidates

    def _platform_font_candidates(self, system_name: str) -> list[str]:
        """Return preferred Japanese-capable fonts for the active platform."""
        if system_name == "darwin":
            return ["Hiragino Sans", "Hiragino Kaku Gothic ProN", "Yu Gothic", "Yu Gothic UI"]
        if system_name == "windows":
            return ["Yu Gothic UI", "Yu Gothic", "Meiryo"]
        if system_name == "linux":
            return ["Noto Sans CJK JP", "Noto Sans JP", "IPAGothic", "IPAexGothic"]
        return []

    def _common_font_candidates(self) -> list[str]:
        """Return cross-platform CJK fallback fonts."""
        return [
            "Noto Sans CJK JP",
            "Noto Sans JP",
            "Yu Gothic UI",
            "Yu Gothic",
            "Meiryo",
            "Hiragino Sans",
            "Hiragino Kaku Gothic ProN",
            "IPAGothic",
            "IPAexGothic",
        ]

    def _parse_color(self, color: str | tuple[int, int, int]) -> str | tuple[float, float, float]:
        """Parse color specification to Matplotlib format.

        Args:
            color: Color specification

        Returns:
            Color in Matplotlib format
        """
        if isinstance(color, tuple):
            # Convert RGB 0-255 to 0-1
            return (color[0] / 255.0, color[1] / 255.0, color[2] / 255.0)
        return str(color)
