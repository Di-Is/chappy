"""Absorption line region overlay support for Matplotlib spectrum plots."""

from __future__ import annotations

import contextlib
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, TypedDict

from matplotlib import transforms

from chappy.plotting.renderers import PlotStyle

if TYPE_CHECKING:
    from collections.abc import Sequence

    from matplotlib.axes import Axes
    from matplotlib.backend_bases import FigureCanvasBase
    from matplotlib.text import Text


class AbsorptionLineRegion(TypedDict, total=False):
    """Payload describing a labelled absorption line region."""

    id: str
    lambda_start: float
    lambda_end: float
    color: str
    alpha: float
    category: str
    label: str
    edge_color: str
    edge_alpha: float
    line_style: str
    line_width: float
    zorder: int
    label_visible: bool
    lambda_center: float
    label_weight: str
    label_color: str
    label_font_size: float
    label_font_weight: str
    label_y: float
    label_zorder: float
    label_box_alpha: float
    label_box_color: str
    label_box_pad: float
    status: str
    sigma: float


class LineRegionArtist(Protocol):
    """Matplotlib artist API used by line region overlays."""

    def set_edgecolor(self, color: str) -> None:
        """Set artist edge color."""
        ...

    def set_alpha(self, alpha: float) -> None:
        """Set artist opacity."""
        ...


class LineRegionRenderer(Protocol):
    """Renderer methods required by absorption line region overlays."""

    def add_region(
        self,
        name: str,
        x_min: float,
        x_max: float,
        style: PlotStyle | None = None,
        label: str | None = None,
    ) -> LineRegionArtist:
        """Add a shaded wavelength region."""
        ...

    def remove_regions_with_prefix(self, prefix: str) -> None:
        """Remove all regions with a matching prefix."""
        ...


@dataclass
class LineRegionOverlay:
    """Draw labelled absorption line wavelength regions."""

    renderer: LineRegionRenderer
    axes: Axes
    canvas: FigureCanvasBase
    prefix: str
    labels: list[Text] = field(default_factory=list, init=False)

    def set_regions(self, regions: Sequence[AbsorptionLineRegion], *, render_labels: bool) -> None:
        """Display identified absorption lines as wavelength overlays."""
        self.clear_labels()
        self.renderer.remove_regions_with_prefix(self.prefix)

        if not regions:
            self.canvas.draw_idle()
            return

        for index, region in enumerate(regions, start=1):
            self._draw_region(index, region, render_labels=render_labels)

        self.canvas.draw_idle()

    def clear(self) -> None:
        """Clear region patches and labels."""
        self.clear_labels()
        self.renderer.remove_regions_with_prefix(self.prefix)
        self.canvas.draw_idle()

    def label_band_bottom(self) -> float | None:
        """Return the lowest axes-fraction y of the drawn line labels, or ``None`` when unlabelled."""
        if not self.labels:
            return None
        return min(float(label.get_position()[1]) for label in self.labels)

    def clear_labels(self) -> None:
        """Remove previously drawn absorption line text labels."""
        for label in self.labels:
            with contextlib.suppress(NotImplementedError, ValueError):
                label.remove()
        self.labels.clear()

    def _draw_region(
        self, index: int, region: AbsorptionLineRegion, *, render_labels: bool
    ) -> None:
        """Draw one region and optionally its label."""
        bounds = self._region_bounds(region)
        if bounds is None:
            return
        start, end = bounds

        color = str(region.get("color", "#2ecc71"))
        edge_color = str(region.get("edge_color", color))
        fill_alpha = float(region.get("alpha", 0.18))
        edge_alpha = float(region.get("edge_alpha", 0.0))
        line_style = str(region.get("line_style", "-"))
        line_width = float(region.get("line_width", 0.0))
        zorder = int(region.get("zorder", -6))
        label = region.get("label")

        style = PlotStyle(
            color=color,
            alpha=1.0,
            fill_alpha=fill_alpha,
            line_style=line_style,
            line_width=line_width,
            zorder=zorder,
        )

        patch = self.renderer.add_region(
            f"{self.prefix}{index}",
            start,
            end,
            style=style,
            label=label if isinstance(label, str) else None,
        )

        if edge_alpha <= 0.0:
            patch.set_edgecolor("none")
        else:
            patch.set_edgecolor(edge_color)
            patch.set_alpha(fill_alpha)

        if render_labels:
            self._draw_label(region, start=start, end=end, color=color, zorder=zorder)

    def _region_bounds(self, region: AbsorptionLineRegion) -> tuple[float, float] | None:
        """Return normalized finite region bounds."""
        lambda_start = region.get("lambda_start")
        lambda_end = region.get("lambda_end")
        if lambda_start is None or lambda_end is None:
            return None

        try:
            start = float(lambda_start)
            end = float(lambda_end)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return None

        if not math.isfinite(start) or not math.isfinite(end):
            return None
        if start == end:
            return None
        if end < start:
            start, end = end, start
        return start, end

    def _draw_label(
        self, region: AbsorptionLineRegion, *, start: float, end: float, color: str, zorder: int
    ) -> None:
        """Draw one label when the payload requests a visible label."""
        if not bool(region.get("label_visible", True)):
            return

        text_value = region.get("label")
        if not isinstance(text_value, str) or not text_value.strip():
            return

        center = self._label_center(region, start, end)
        if center is None:
            return

        label_y = self._label_y(region)
        label_weight = str(
            region.get(
                "label_weight", "bold" if region.get("category") == "confirmed" else "normal"
            )
        )
        label_color = str(region.get("label_color", color))
        label_font_size = float(region.get("label_font_size", 9.0))
        label_zorder = float(region.get("label_zorder", zorder + 1))
        box_alpha = float(region.get("label_box_alpha", 0.65))
        box_color = str(region.get("label_box_color", "black"))
        box_pad = float(region.get("label_box_pad", 1.4))

        bbox: dict[str, float | str] | None = None
        if box_alpha > 0.0:
            bbox = {
                "facecolor": box_color,
                "alpha": max(0.0, min(box_alpha, 1.0)),
                "edgecolor": "none",
                "pad": box_pad,
            }

        self.labels.append(
            self.axes.text(
                center,
                label_y,
                text_value,
                color=label_color,
                fontsize=label_font_size,
                fontweight=label_weight,
                ha="center",
                va="bottom",
                transform=transforms.blended_transform_factory(
                    self.axes.transData, self.axes.transAxes
                ),
                zorder=label_zorder,
                bbox=bbox,
            )
        )

    @staticmethod
    def _label_center(region: AbsorptionLineRegion, start: float, end: float) -> float | None:
        """Return finite label center position."""
        lambda_center = region.get("lambda_center")
        if lambda_center is None:
            return (start + end) / 2.0

        try:
            center = float(lambda_center)
        except (TypeError, ValueError):
            center = (start + end) / 2.0

        if not math.isfinite(center):
            center = (start + end) / 2.0
        if not math.isfinite(center):  # pragma: no cover - defensive
            return None
        return center

    @staticmethod
    def _label_y(region: AbsorptionLineRegion) -> float:
        """Return clamped label y-position in axes coordinates."""
        label_y = region.get("label_y", 0.94)
        try:
            value = float(label_y)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            value = 0.94
        return min(max(value, 0.0), 1.0)
