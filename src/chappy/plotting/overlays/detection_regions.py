"""Detection region overlay support for Matplotlib spectrum plots."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from chappy.plotting.renderers import PlotStyle

if TYPE_CHECKING:
    from chappy.presentation.identify import DetectionOverlayPayload


class DetectionRegionArtist(Protocol):
    """Matplotlib artist methods used by detection overlays."""

    def set_edgecolor(self, color: str) -> None:
        """Set artist edge color."""
        ...


class DetectionRegionRenderer(Protocol):
    """Renderer methods required by detection overlays."""

    def add_region(
        self,
        name: str,
        x_min: float,
        x_max: float,
        style: PlotStyle | None = None,
        label: str | None = None,
    ) -> DetectionRegionArtist:
        """Add a shaded wavelength region."""
        ...

    def remove_regions_with_prefix(self, prefix: str) -> None:
        """Remove all regions with a matching prefix."""
        ...


class DetectionRegionCanvas(Protocol):
    """Canvas methods required by detection overlays."""

    def draw_idle(self) -> None:
        """Schedule a canvas redraw."""
        ...


@dataclass
class DetectionRegionOverlay:
    """Own detection region validation and rendering."""

    renderer: DetectionRegionRenderer
    canvas: DetectionRegionCanvas
    prefix: str

    def set_regions(self, regions: list[DetectionOverlayPayload]) -> None:
        """Validate and render detection regions."""
        self.renderer.remove_regions_with_prefix(self.prefix)

        for index, region in enumerate(regions, start=1):
            lambda_start, lambda_end = self._validate_bounds(region, index=index)
            color = self._required_color(region, index=index)
            fill_alpha = self._required_alpha(region, index=index)
            style = PlotStyle(
                color=color,
                alpha=1.0,
                fill_alpha=fill_alpha,
                line_style="-",
                line_width=0.0,
                zorder=-1,
            )

            patch = self.renderer.add_region(
                f"{self.prefix}{index}", lambda_start, lambda_end, style=style, label=None
            )
            patch.set_edgecolor("none")

        self.canvas.draw_idle()

    def clear(self) -> None:
        """Clear rendered detection regions."""
        self.renderer.remove_regions_with_prefix(self.prefix)
        self.canvas.draw_idle()

    @staticmethod
    def _required_float(value: object, field: str, *, index: int) -> float:
        """Convert and validate a finite detection-region numeric field."""
        if isinstance(value, bool):
            msg = f"Detection region #{index} field '{field}' must be a finite number."
            raise TypeError(msg)
        if not isinstance(value, int | float | str):
            msg = f"Detection region #{index} field '{field}' must be a finite number."
            raise TypeError(msg)
        try:
            converted = float(value)
        except (TypeError, ValueError) as exc:
            msg = f"Detection region #{index} field '{field}' must be a finite number."
            raise ValueError(msg) from exc
        if not math.isfinite(converted):
            msg = f"Detection region #{index} field '{field}' must be finite."
            raise ValueError(msg)
        return converted

    @classmethod
    def _required_color(cls, region: DetectionOverlayPayload, *, index: int) -> str:
        """Return a validated optional detection region color."""
        if "color" not in region:
            return "#5dade2"
        color = region["color"]
        if not isinstance(color, str) or not color:
            msg = f"Detection region #{index} field 'color' must be a non-empty string."
            raise TypeError(msg)
        return color

    @classmethod
    def _required_alpha(cls, region: DetectionOverlayPayload, *, index: int) -> float:
        """Return a validated optional detection region alpha."""
        if "alpha" not in region:
            return 0.18
        alpha = region["alpha"]
        if isinstance(alpha, bool):
            msg = f"Detection region #{index} field 'alpha' must be a finite number."
            raise TypeError(msg)
        try:
            converted_alpha = float(alpha)
        except (TypeError, ValueError):
            msg = f"Detection region #{index} field 'alpha' must be a finite number."
            raise ValueError(msg) from None
        if not math.isfinite(converted_alpha):
            msg = f"Detection region #{index} field 'alpha' must be finite."
            raise ValueError(msg)
        if not 0.0 <= converted_alpha <= 1.0:
            msg = f"Detection region #{index} field 'alpha' must be between 0.0 and 1.0."
            raise ValueError(msg)
        return converted_alpha

    @classmethod
    def _validate_bounds(
        cls, region: DetectionOverlayPayload, *, index: int
    ) -> tuple[float, float]:
        """Validate required numeric bounds for one detection region."""
        if "lambda_start" not in region or "lambda_end" not in region:
            msg = f"Detection region #{index} requires both 'lambda_start' and 'lambda_end'."
            raise ValueError(msg)

        lambda_start = cls._required_float(region["lambda_start"], "lambda_start", index=index)
        lambda_end = cls._required_float(region["lambda_end"], "lambda_end", index=index)

        if lambda_start >= lambda_end:
            msg = f"Detection region #{index} requires lambda_start < lambda_end."
            raise ValueError(msg)

        return (lambda_start, lambda_end)
