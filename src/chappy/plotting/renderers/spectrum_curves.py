"""Owner for observed, model, and residual curve rendering."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

import numpy as np

from chappy.plotting.renderers.base_renderer import CurveArtist, PlotStyle, PlotType
from chappy.presentation.spectrum.visual_tokens import ComponentCurveVisuals, SpectrumVisuals

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from chappy.plotting.core.plot_config import PlotConfig
    from chappy.plotting.core.spectrum_data_store import SpectrumPlotDataStore
    from chappy.plotting.renderers.curve_display_resolution import CurveDisplayResolutionOwner
    from chappy.plotting.renderers.style_registry import StyleRegistry
    from chappy.presentation.spectrum import SpectrumComponentCurve, SpectrumPlotDisplayCommand

logger = logging.getLogger(__name__)

COMPONENT_CURVE_PREFIX = "component_profile:"


class CurveRenderer(Protocol):
    """Renderer API required by spectrum curve owners."""

    plot_items: dict[str, object]

    def add_curve(
        self,
        name: str,
        x: NDArray[np.float64],
        y: NDArray[np.float64],
        plot_type: PlotType = PlotType.SPECTRUM,
        style: PlotStyle | None = None,
    ) -> object:
        """Add a curve to the plot."""
        ...

    def update_curve(
        self, name: str, x: NDArray[np.float64] | None = None, y: NDArray[np.float64] | None = None
    ) -> None:
        """Update an existing curve."""
        ...

    def remove_curve(self, name: str) -> None:
        """Remove a curve from the plot."""
        ...


@dataclass
class SpectrumCurveOwner:
    """Own observed, model, and residual renderer operations."""

    renderer: CurveRenderer
    data_store: SpectrumPlotDataStore
    style_registry: StyleRegistry
    config: PlotConfig
    display_resolution: CurveDisplayResolutionOwner
    _component_curve_colors: dict[str, str] = field(default_factory=dict)

    def render_observed(
        self, *, display_command: SpectrumPlotDisplayCommand, show_error_bars: bool
    ) -> None:
        """Render the observed spectrum from stored data."""
        data = self.data_store.get_observed_data()
        if data is None:
            logger.warning("No observed data available")
            return

        wavelength = data["wavelength"]
        flux = data["flux"]
        error = data.get("error")

        if wavelength is None or flux is None:
            logger.warning("Observed wavelength or flux is missing")
            return

        use_normalized = False
        if display_command.use_normalized_observed:
            normalized = self.data_store.get_normalized_observed_data()
            norm_flux = normalized.get("flux") if normalized else None
            norm_error = normalized.get("error") if normalized else None

            if isinstance(norm_flux, np.ndarray) and len(norm_flux) == len(flux):
                if np.any(np.isfinite(norm_flux)):
                    flux = norm_flux
                    if isinstance(norm_error, np.ndarray) and len(norm_error) == len(norm_flux):
                        error = norm_error
                    use_normalized = True
                else:
                    logger.debug(
                        "Normalized flux contains no finite samples; falling back to raw observed data"
                    )
            elif norm_flux is not None:
                logger.debug(
                    "Normalized flux length mismatch (raw: %d, normalized: %d); using raw observed data",
                    len(flux),
                    len(norm_flux),
                )

        if use_normalized:
            logger.debug("Rendering continuum-normalized observed spectrum via display command")

        prepared_error = error if show_error_bars else None

        observed_color = self.config.colors.OBSERVED_DATA or SpectrumVisuals.OBSERVED_COLOR
        observed_width = self.config.styles.DATA_LINE_WIDTH
        spectrum_style = PlotStyle(
            color=observed_color,
            line_width=float(observed_width),
            drawstyle=SpectrumVisuals.OBSERVED_DRAWSTYLE,
            zorder=SpectrumVisuals.OBSERVED_Z_ORDER,
        )

        self._render_curve(
            "observed", wavelength, flux, plot_type=PlotType.SPECTRUM, style=spectrum_style
        )

        if prepared_error is not None and show_error_bars:
            error_style = PlotStyle(
                color=SpectrumVisuals.ERROR_COLOR,
                line_width=SpectrumVisuals.ERROR_LINE_WIDTH,
                drawstyle=SpectrumVisuals.OBSERVED_DRAWSTYLE,
                alpha=0.85,
                zorder=SpectrumVisuals.ERROR_Z_ORDER,
            )
            self._render_curve(
                "error", wavelength, prepared_error, plot_type=PlotType.SPECTRUM, style=error_style
            )
        elif "error" in self.renderer.plot_items:
            self.renderer.remove_curve("error")
            self.display_resolution.unregister("error")

    def render_model(self) -> None:
        """Render the model curve from stored data."""
        data = self.data_store.get_model_data()
        if data is None:
            return

        wavelength = data["wavelength"]
        flux = data["flux"]
        if wavelength is None or flux is None:
            return

        self._render_curve(
            "model",
            wavelength,
            flux,
            plot_type=PlotType.MODEL,
            style=self.style_registry.get_plot_style(PlotType.MODEL),
        )

    def set_residual_data(
        self, wavelength: NDArray[np.float64], residual: NDArray[np.float64]
    ) -> None:
        """Store and render the residual curve."""
        self.data_store.set_residual_data(wavelength, residual)
        logger.info("Using all %d residual data points", len(wavelength))

        self._render_curve(
            "residual",
            wavelength,
            -residual,
            plot_type=PlotType.RESIDUAL,
            style=self.style_registry.get_plot_style(PlotType.RESIDUAL),
        )

    def clear_residual(self) -> None:
        """Remove the residual curve and clear stored data."""
        if "residual" in self.renderer.plot_items:
            self.renderer.remove_curve("residual")
        self.display_resolution.unregister("residual")
        self.data_store.clear_residual_data()

    def clear_model(self) -> None:
        """Remove the model curve, its component curves, and clear stored data."""
        if "model" in self.renderer.plot_items:
            self.renderer.remove_curve("model")
        self.display_resolution.unregister("model")
        self.data_store.clear_model_data()
        self.clear_component_profiles()

    def render_component_profiles(self, curves: tuple[SpectrumComponentCurve, ...]) -> None:
        """Render one curve per component, dropping curves no longer present."""
        incoming = {component_curve_name(curve.component_id) for curve in curves}
        for name in set(self._component_curve_colors) - incoming:
            self._remove_component_curve(name)

        for curve in curves:
            name = component_curve_name(curve.component_id)
            self._component_curve_colors[name] = curve.color
            self._render_curve(
                name,
                curve.wavelength,
                curve.flux,
                plot_type=PlotType.MODEL,
                style=_component_curve_style(curve.color, emphasized=curve.emphasized),
            )

    def clear_component_profiles(self) -> None:
        """Remove every rendered component curve."""
        for name in list(self._component_curve_colors):
            self._remove_component_curve(name)

    def set_emphasized_component_id(self, component_id: str | None) -> None:
        """Restyle already-rendered component curves for the emphasised component."""
        emphasized_name = None if component_id is None else component_curve_name(component_id)
        for name, color in self._component_curve_colors.items():
            item = self.renderer.plot_items.get(name)
            if not isinstance(item, CurveArtist):
                continue
            style = _component_curve_style(color, emphasized=name == emphasized_name)
            item.set_linewidth(style.line_width)
            item.set_alpha(style.alpha)
            item.set_zorder(style.zorder)

    def _remove_component_curve(self, name: str) -> None:
        if name in self.renderer.plot_items:
            self.renderer.remove_curve(name)
        self.display_resolution.unregister(name)
        self._component_curve_colors.pop(name, None)

    def _render_curve(
        self,
        name: str,
        wavelength: NDArray[np.float64],
        flux: NDArray[np.float64],
        *,
        plot_type: PlotType,
        style: PlotStyle,
    ) -> None:
        """Create or update one renderer curve and reapply style."""
        display_x, display_y = self.display_resolution.register_source(name, wavelength, flux)
        if name in self.renderer.plot_items:
            self.renderer.update_curve(name, display_x, display_y)
            item = self.renderer.plot_items.get(name)
        else:
            item = self.renderer.add_curve(
                name, display_x, display_y, plot_type=plot_type, style=style
            )

        if not isinstance(item, CurveArtist):
            return

        item.set_color(style.color)
        item.set_linewidth(style.line_width)
        item.set_alpha(style.alpha)
        item.set_zorder(style.zorder)
        if style.drawstyle:
            item.set_drawstyle(style.drawstyle)


def component_curve_name(component_id: str) -> str:
    """Return the renderer curve name used for one component profile."""
    return f"{COMPONENT_CURVE_PREFIX}{component_id}"


def _component_curve_style(color: str, *, emphasized: bool) -> PlotStyle:
    """Return the curve style for a component profile in its current emphasis state."""
    return PlotStyle(
        color=color,
        line_width=(
            ComponentCurveVisuals.EMPHASIZED_LINE_WIDTH
            if emphasized
            else ComponentCurveVisuals.LINE_WIDTH
        ),
        line_style=ComponentCurveVisuals.LINE_STYLE,
        alpha=ComponentCurveVisuals.EMPHASIZED_ALPHA
        if emphasized
        else ComponentCurveVisuals.ALPHA,
        zorder=(
            ComponentCurveVisuals.EMPHASIZED_Z_ORDER
            if emphasized
            else ComponentCurveVisuals.Z_ORDER
        ),
    )
