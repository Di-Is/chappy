"""Plot primitive visual tokens shared by GUI and plotting adapters."""

from __future__ import annotations

from typing import Final


class SpectrumVisuals:
    """Visual tokens for spectrum plot primitives."""

    OBSERVED_COLOR = "#000000"
    OBSERVED_LINE_WIDTH = 1.0
    OBSERVED_DRAWSTYLE: Final = "steps-mid"
    OBSERVED_Z_ORDER = 0

    # Residuals mirror the optimized data windows for easier inspection.
    RESIDUAL_DRAWSTYLE: Final = "steps-mid"

    ERROR_COLOR = "#808080"
    ERROR_LINE_WIDTH = 1.0
    ERROR_Z_ORDER = 1

    CONTINUUM_COLOR = "#0066CC"
    CONTINUUM_LINE_WIDTH = 2.0
    CONTINUUM_Z_ORDER = 2


class ContinuumControlPointVisuals:
    """Visual tokens for continuum control point markers."""

    MARKER_COLOR = "#4CD964"
    MARKER_COLOR_SELECTED = "#34C759"
    MARKER_OUTLINE_DRAGGING = "#2FAA4B"
    MARKER_RADIUS_PX = 8
    MARKER_DRAG_SCALE = 1.5
    HIT_RADIUS_PX = 10
    Z_ORDER = 3

    LIMIT = 1000
    MIN_SEPARATION_ANGSTROM = 0.1
    MIN_POINTS_REQUIRED = 3


COMPONENT_CURVE_COLORS: Final[tuple[str, ...]] = (
    "#1B9E77",
    "#D95F02",
    "#7570B3",
    "#E7298A",
    "#66A61E",
    "#E6AB02",
    "#A6761D",
    "#666666",
)


class ComponentCurveVisuals:
    """Visual tokens for per-component profile curves."""

    LINE_STYLE: Final = "--"
    LINE_WIDTH = 0.8
    ALPHA = 0.5
    EMPHASIZED_LINE_WIDTH = 1.6
    EMPHASIZED_ALPHA = 1.0
    # Stays under the composite model curve (PlotType.MODEL uses zorder 4).
    Z_ORDER = 2
    EMPHASIZED_Z_ORDER = 3


def component_curve_color(index: int) -> str:
    """Return the identity colour assigned to the component at the given position."""
    return COMPONENT_CURVE_COLORS[index % len(COMPONENT_CURVE_COLORS)]
