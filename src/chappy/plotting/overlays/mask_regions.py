"""Persistent mask region overlay support for Matplotlib spectrum plots."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from matplotlib import colors as mcolors

from chappy.plotting.renderers import PlotStyle

if TYPE_CHECKING:
    from collections.abc import Iterable

    from chappy.core.masking import MaskDefinition

RgbaColor = tuple[float, float, float, float]


class RegionArtist(Protocol):
    """Matplotlib artist methods used by mask region overlays."""

    def set_facecolor(self, color: RgbaColor) -> None:
        """Set artist fill color."""
        ...

    def set_edgecolor(self, color: str) -> None:
        """Set artist edge color."""
        ...

    def set_linewidth(self, width: float) -> None:
        """Set artist line width."""
        ...

    def set_zorder(self, level: float) -> None:
        """Set artist draw order."""
        ...


class MaskRegionRenderer(Protocol):
    """Renderer methods required by persistent mask overlays."""

    def add_region(
        self,
        name: str,
        x_min: float,
        x_max: float,
        style: PlotStyle | None = None,
        label: str | None = None,
    ) -> RegionArtist:
        """Add a shaded wavelength region.

        Args:
            name: Region identifier.
            x_min: Left wavelength bound.
            x_max: Right wavelength bound.
            style: Region style.
            label: Optional region label.

        Returns:
            Created region artist.
        """
        ...

    def remove_regions_with_prefix(self, prefix: str) -> None:
        """Remove all regions with a matching prefix.

        Args:
            prefix: Region name prefix.
        """
        ...

    def get_region(self, name: str) -> RegionArtist | None:
        """Return a region artist by name.

        Args:
            name: Region identifier.

        Returns:
            Region artist when present.
        """
        ...


class MaskRegionCanvas(Protocol):
    """Canvas methods required by persistent mask overlays."""

    def draw_idle(self) -> None:
        """Schedule a canvas redraw."""
        ...


@dataclass
class MaskRegionOverlay:
    """Draw and highlight persistent wavelength mask regions.

    Args:
        renderer: Renderer used to create and look up region artists.
        canvas: Canvas used to schedule redraws.
        prefix: Prefix used for mask region artist identifiers.
        color: Base color used for mask regions.
    """

    renderer: MaskRegionRenderer
    canvas: MaskRegionCanvas
    prefix: str
    color: str
    _definitions: dict[str, MaskDefinition] = field(default_factory=dict, init=False)
    _active_id: str | None = field(default=None, init=False)

    def set_regions(self, masks: Iterable[MaskDefinition]) -> None:
        """Display wavelength masks as shaded bands.

        Args:
            masks: Mask definitions to display.
        """
        self._definitions = {mask.identifier: mask for mask in masks}
        self.renderer.remove_regions_with_prefix(self.prefix)

        for mask in self._definitions.values():
            if not mask.enabled:
                continue
            self._draw_region(mask)

        self._update_styles()
        self.canvas.draw_idle()

    def set_active(self, mask_id: str | None) -> None:
        """Highlight one mask region.

        Args:
            mask_id: Active mask identifier, or None.
        """
        self._active_id = mask_id
        self._update_styles()
        self.canvas.draw_idle()

    def _draw_region(self, mask: MaskDefinition) -> None:
        """Draw one enabled mask region.

        Args:
            mask: Enabled mask definition.
        """
        style = PlotStyle(
            color=self.color, alpha=1.0, fill_alpha=0.25, line_style="-", line_width=0.0, zorder=-5
        )
        region_name = f"{self.prefix}{mask.identifier}"
        patch = self.renderer.add_region(
            region_name, mask.wavelength_min, mask.wavelength_max, style=style, label=None
        )
        patch.set_edgecolor(self.color)
        patch.set_linewidth(0.0)

    def _update_styles(self) -> None:
        """Apply active and inactive mask region styles."""
        for identifier in self._definitions:
            region_name = f"{self.prefix}{identifier}"
            patch = self.renderer.get_region(region_name)
            if patch is None:
                continue

            if identifier == self._active_id:
                patch.set_facecolor(mcolors.to_rgba(self.color, alpha=0.40))
                patch.set_edgecolor("none")
                patch.set_linewidth(0.0)
                patch.set_zorder(4)
            else:
                patch.set_facecolor(mcolors.to_rgba(self.color, alpha=0.25))
                patch.set_edgecolor("none")
                patch.set_linewidth(0.0)
                patch.set_zorder(-5)
