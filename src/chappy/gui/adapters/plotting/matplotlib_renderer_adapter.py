"""Qt-owned adapter for Matplotlib renderer dependencies."""
# mypy: disable-error-code="attr-defined,no-untyped-call"

from __future__ import annotations

import logging
import platform
from typing import TYPE_CHECKING

from matplotlib import font_manager, rcParams
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from PySide6.QtGui import QGuiApplication

from chappy.gui.application_font import (
    common_font_candidates,
    font_supports_japanese,
    platform_font_candidates,
)
from chappy.plotting.renderers.matplotlib_renderer import MatplotlibRenderer

if TYPE_CHECKING:
    from matplotlib.figure import Figure

logger = logging.getLogger(__name__)


def create_qt_matplotlib_renderer(
    *, constrained_layout: bool = False, tick_labelsize: float | None = None
) -> MatplotlibRenderer:
    """Create a Matplotlib renderer configured with Qt-owned dependencies."""
    return MatplotlibRenderer(
        canvas_factory=create_qt_matplotlib_canvas,
        axis_label_font=determine_qt_axis_label_font(),
        constrained_layout=constrained_layout,
        tick_labelsize=tick_labelsize,
    )


def create_qt_matplotlib_canvas(figure: Figure) -> FigureCanvasQTAgg:
    """Create a Qt Matplotlib canvas for the given figure."""
    return FigureCanvasQTAgg(figure)


def determine_qt_axis_label_font() -> str | None:
    """Return a Qt-validated font family that can render Japanese glyphs."""
    for family in ordered_qt_font_candidates():
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


def ordered_qt_font_candidates() -> list[str]:
    """Return Qt-visible font families ordered for axis labels."""
    app = QGuiApplication.instance()
    app_font = app.font().family() if isinstance(app, QGuiApplication) else ""

    system_name = platform.system().lower()
    os_candidates = platform_font_candidates(system_name)
    common_candidates = common_font_candidates()

    candidates: list[str] = []
    if system_name == "windows":
        candidates.extend(os_candidates)
        if app_font:
            candidates.append(app_font)
    else:
        if app_font:
            candidates.append(app_font)
        candidates.extend(os_candidates)
    candidates.extend(common_candidates)

    unique_candidates: list[str] = []
    for family in candidates:
        if family and family not in unique_candidates and font_supports_japanese(family):
            unique_candidates.append(family)
    return unique_candidates
