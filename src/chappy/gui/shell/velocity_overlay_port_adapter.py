"""Shell adapter exposing the shared spectrum velocity overlay as a typed port."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chappy.gui.modes.common import VelocityOverlayPort

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Literal

    from chappy.gui.spectrum.spectrum_view import SpectrumView
    from chappy.presentation.velocity import VelocityOverlayInfo


class SpectrumVelocityOverlayPort(VelocityOverlayPort):
    """Adapt the active spectrum view to the shared velocity overlay port."""

    def __init__(self, *, spectrum_view_provider: Callable[[], SpectrumView | None]) -> None:
        """Store the spectrum view provider."""
        self._spectrum_view_provider = spectrum_view_provider

    def show_velocity_overlay(
        self,
        overlay_info: VelocityOverlayInfo,
        *,
        context: Literal["identify", "optimize"] = "identify",
    ) -> None:
        """Show the shared velocity overlay when a spectrum view is available."""
        spectrum_view = self._spectrum_view_provider()
        if spectrum_view is None:
            return
        spectrum_view.set_velocity_plot_active(True, overlay_info, context=context)

    def hide_velocity_overlay(
        self, *, context: Literal["identify", "optimize"] | None = None
    ) -> None:
        """Hide the shared velocity overlay when a spectrum view is available."""
        spectrum_view = self._spectrum_view_provider()
        if spectrum_view is None or not spectrum_view.is_velocity_plot_visible():
            return
        spectrum_view.set_velocity_plot_active(
            False, context=context if context is not None else "identify"
        )

    def is_velocity_overlay_visible(self) -> bool:
        """Return whether the shared velocity overlay is visible."""
        spectrum_view = self._spectrum_view_provider()
        return bool(spectrum_view is not None and spectrum_view.is_velocity_plot_visible())
