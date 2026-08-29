"""Base renderer interface for plotting backends.

This module defines the abstract base class that all renderer implementations
must follow to ensure consistent API across different plotting libraries.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray


class PlotType(Enum):
    """Types of plots supported by renderers."""

    SPECTRUM = auto()  # Main spectrum curve
    MODEL = auto()  # Model fit curve
    RESIDUAL = auto()  # Residual curve
    CONTINUUM = auto()  # Continuum curve
    MARKER = auto()  # Vertical line markers


MatplotlibDrawStyle = Literal["default", "steps", "steps-pre", "steps-mid", "steps-post"]


@dataclass
class PlotStyle:
    """Style configuration for plot elements."""

    color: str | tuple[int, int, int] = "white"
    line_width: float = 1.0
    line_style: str = "-"  # solid, dashed, dotted
    alpha: float = 1.0
    drawstyle: MatplotlibDrawStyle | None = None
    marker_style: str | None = None
    marker_size: float = 8.0
    fill_alpha: float = 0.3
    zorder: int = 0  # Drawing order (higher values drawn on top)


@dataclass
class AxisConfig:
    """Configuration for plot axes."""

    label: str = ""
    units: str = ""
    scale: str = "linear"  # linear, log
    min_value: float | None = None
    max_value: float | None = None
    grid: bool = True
    grid_alpha: float = 0.3


@runtime_checkable
class CurveArtist(Protocol):
    """Line artist operations required by curve rendering and management."""

    def set_color(self, color: str | tuple[int, int, int]) -> None:
        """Set line color."""
        ...

    def set_linewidth(self, width: float) -> None:
        """Set line width."""
        ...

    def set_alpha(self, alpha: float) -> None:
        """Set line alpha."""
        ...

    def set_zorder(self, zorder: float) -> None:
        """Set line draw order."""
        ...

    def set_drawstyle(self, drawstyle: str) -> None:
        """Set line draw style."""
        ...

    def set_data(self, x: NDArray[np.float64], y: NDArray[np.float64]) -> None:
        """Replace both x and y data."""
        ...

    def set_xdata(self, x: NDArray[np.float64]) -> None:
        """Replace x data."""
        ...

    def set_ydata(self, y: NDArray[np.float64]) -> None:
        """Replace y data."""
        ...

    def remove(self) -> None:
        """Remove the line from the axes."""
        ...
