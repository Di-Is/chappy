"""Line overlay adapter used by mode lifecycle objects."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from chappy.gui.utils.absorption_overlays import compute_confirmed_line_regions

if TYPE_CHECKING:
    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.utils.absorption_overlays import RegionPayload


@runtime_checkable
class LineOverlaySpectrumView(Protocol):
    """Spectrum view operations required for line overlay updates."""

    def set_absorption_line_regions(self, regions: list[RegionPayload]) -> None:
        """Set the displayed absorption line regions."""
        ...


class LineOverlaySpectrumViewHost(Protocol):
    """View-stack subset that exposes the spectrum view."""

    @property
    def spectrum_view(self) -> LineOverlaySpectrumView | None:
        """Return the spectrum view when available."""
        ...


class IdentifyLineOverlaySource(Protocol):
    """Identify coordinator operations required for line overlay updates."""

    def build_line_overlay_payload(self, *, include_temporary: bool) -> list[RegionPayload]:
        """Build line overlay payloads for the current identify state."""
        ...


class LineOverlayWindow(Protocol):
    """Main-window subset required by the line overlay adapter."""

    @property
    def current_project(self) -> SpectroscopyProject | None:
        """Return the active project."""
        ...

    @property
    def identify_coordinator(self) -> IdentifyLineOverlaySource | None:
        """Return the identify coordinator when available."""
        ...

    @property
    def view_stack(self) -> LineOverlaySpectrumViewHost | None:
        """Return the view stack when available."""
        ...


class ModeLineOverlayAdapter:
    """Apply mode-specific absorption line overlays to the spectrum view."""

    def __init__(self, window: LineOverlayWindow) -> None:
        """Initialize the adapter.

        Args:
            window: Main-window-like object exposing project, identify, and view state.
        """
        self._window = window

    def show_confirmed_line_overlays(self) -> None:
        """Display confirmed line overlays."""
        self._set_regions(self._confirmed_regions())

    def show_identify_line_overlays(self) -> None:
        """Display line overlays including identify-mode temporary candidates."""
        identify_coordinator = self._window.identify_coordinator
        if identify_coordinator is None:
            msg = "Identify line overlays require an identify coordinator."
            raise RuntimeError(msg)
        regions = identify_coordinator.build_line_overlay_payload(include_temporary=True)
        self._set_regions(regions)

    def clear_line_overlays(self) -> None:
        """Clear displayed line overlays."""
        self._set_regions([])

    def _confirmed_regions(self) -> list[RegionPayload]:
        """Return confirmed line regions for the active project."""
        return compute_confirmed_line_regions(self._window.current_project)

    def _set_regions(self, regions: list[RegionPayload]) -> None:
        """Apply regions to the spectrum view when available."""
        view_stack = self._window.view_stack
        if view_stack is None:
            msg = "Line overlays require a view stack."
            raise RuntimeError(msg)

        spectrum_view = view_stack.spectrum_view
        if not isinstance(spectrum_view, LineOverlaySpectrumView):
            msg = "Line overlays require a spectrum view."
            raise TypeError(msg)
        spectrum_view.set_absorption_line_regions(regions)
