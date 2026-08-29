"""Interactive region selection handler for spectrum plots.

This module provides region selection capabilities for spectrum plots,
allowing users to select wavelength ranges for analysis or zooming.
"""

from __future__ import annotations

import contextlib
import logging
from enum import Enum, auto
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from matplotlib.backend_bases import MouseButton
from matplotlib.widgets import RectangleSelector, SpanSelector

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from matplotlib.axes import Axes
    from matplotlib.backend_bases import MouseEvent
    from matplotlib.figure import Figure

logger = logging.getLogger(__name__)


class SelectionMode(Enum):
    """Selection modes for different behaviors."""

    ZOOM = auto()  # Select region to zoom
    RANGE = auto()  # Select wavelength range
    CONTINUUM = auto()  # Select continuum normalization range


class RemovableArtist(Protocol):
    """Matplotlib artist cleanup capability used by selector teardown."""

    def remove(self) -> None:
        """Remove the artist from its axes."""
        ...


@runtime_checkable
class SelectorCleanupArtifacts(Protocol):
    """Selector private cleanup artifacts exposed by Matplotlib widgets."""

    _selection_artist: RemovableArtist | None
    _handles: Iterable[RemovableArtist]


class MatplotlibSelectionHandler:
    """Handles interactive region selection in Matplotlib plots.

    This provides similar functionality to SelectionHandler but for
    Matplotlib-based spectrum plots.
    """

    def __init__(self, axes: Axes, figure: Figure) -> None:
        """Initialize matplotlib selection handler.

        Args:
            axes: Matplotlib axes object
            figure: Matplotlib figure object
        """
        self.axes = axes
        self.figure = figure
        self.canvas = figure.canvas

        # Selection state
        self.enabled = False
        self.mode = SelectionMode.ZOOM
        self.selector: RectangleSelector | SpanSelector | None = None
        self._interactive = False
        self._on_update_callback: Callable[[float, float], None] | None = None
        self._min_span = 5.0

        # Visual style
        self.rect_props = {
            "facecolor": "blue",
            "edgecolor": "blue",
            "alpha": 0.2,
            "fill": True,
            "linestyle": "--",
            "linewidth": 2,
        }

        # Callback storage
        self._on_select_callback: Callable[[float, float, float, float], None] | None = None

        logger.debug("MatplotlibSelectionHandler initialized")

    def set_enabled(
        self,
        enabled: bool,
        mode: SelectionMode = SelectionMode.ZOOM,
        on_select: Callable[[float, float, float, float], None] | None = None,
        *,
        interactive: bool = False,
        on_update: Callable[[float, float], None] | None = None,
    ) -> None:
        """Enable or disable selection mode.

        Args:
            enabled: True to enable selection
            mode: Selection mode to use
            on_select: Callback function for selection completion
            interactive: Whether handles should be interactive (SpanSelector only)
            on_update: Optional callback for live updates during drag (SpanSelector only)
        """
        self.enabled = enabled
        self.mode = mode
        self._on_select_callback = on_select
        self._interactive = interactive
        self._on_update_callback = on_update if enabled else None

        if enabled:
            self._create_selector()
        else:
            self._remove_selector()

    def set_min_span(self, value: float) -> None:
        """Set minimum span for range selections."""
        self._min_span = max(float(value), 0.0)

    def _create_selector(self) -> None:
        """Create appropriate selector based on mode."""
        # Remove existing selector
        self._remove_selector()

        if self.mode in (SelectionMode.ZOOM, SelectionMode.CONTINUUM):
            # Use RectangleSelector for 2D selection
            self.selector = RectangleSelector(
                self.axes,
                self._on_rectangle_select,
                useblit=True,
                button=[MouseButton.LEFT],  # Left mouse button
                minspanx=5,
                minspany=5,
                spancoords="pixels",
                props=self.rect_props,
                interactive=False,
            )

        else:  # RANGE or GROUP mode
            # Use SpanSelector for 1D wavelength selection
            min_span = self._min_span
            self.selector = SpanSelector(
                self.axes,
                self._on_span_select,
                "horizontal",
                useblit=True,
                button=[MouseButton.LEFT],
                minspan=min_span,
                props=self.rect_props,
                interactive=self._interactive,
                onmove_callback=self._on_span_move if self._on_update_callback else None,
            )

        logger.info("Selection enabled in %s mode", self.mode.name)

    def _remove_selector(self) -> None:
        """Remove and cleanup selector."""
        if self.selector:
            selector = self.selector
            if isinstance(selector, SelectorCleanupArtifacts):
                artist = selector._selection_artist
                if artist is not None:
                    with contextlib.suppress(ValueError):
                        artist.remove()
                for handle in selector._handles:
                    with contextlib.suppress(ValueError):
                        handle.remove()
            selector.set_active(False)
            self.selector = None
            self.canvas.draw_idle()

    def _on_rectangle_select(self, eclick: MouseEvent, erelease: MouseEvent) -> None:
        """Handle rectangle selection completion.

        Args:
            eclick: Mouse click event
            erelease: Mouse release event
        """
        if not self._on_select_callback:
            return

        # Extract bounds - handle None values
        if (
            eclick.xdata is None
            or erelease.xdata is None
            or eclick.ydata is None
            or erelease.ydata is None
        ):
            return

        x_min = min(eclick.xdata, erelease.xdata)
        x_max = max(eclick.xdata, erelease.xdata)
        y_min = min(eclick.ydata, erelease.ydata)
        y_max = max(eclick.ydata, erelease.ydata)

        logger.info("Rectangle selected: (%.2f, %.2f) to (%.2f, %.2f)", x_min, x_max, y_min, y_max)

        self._on_select_callback(x_min, x_max, y_min, y_max)

    def _on_span_select(self, x_min: float, x_max: float) -> None:
        """Handle span selection completion.

        Args:
            x_min: Minimum x value
            x_max: Maximum x value
        """
        logger.info("Span selected: %.2f to %.2f", x_min, x_max)

        # For span selection, use full y range
        y_limits = self.axes.get_ylim()

        if self._on_select_callback:
            self._on_select_callback(x_min, x_max, y_limits[0], y_limits[1])

    def _on_span_move(self, x_min: float, x_max: float) -> None:
        """Handle live drag updates emitted by SpanSelector.

        Args:
            x_min: Proposed lower wavelength boundary.
            x_max: Proposed upper wavelength boundary.
        """
        if not self._on_update_callback:
            return
        start = min(x_min, x_max)
        end = max(x_min, x_max)
        self._on_update_callback(start, end)
