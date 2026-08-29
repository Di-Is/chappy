"""Tests for Qt-managed Matplotlib spectrum plot translations."""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

import pytest
import numpy as np
from pytestqt.qtbot import QtBot
from PySide6.QtGui import QMouseEvent

from chappy.gui.adapters.plotting import (
    MatplotlibSpectrumPlot,
    create_matplotlib_mouse_event_bridge_adapter,
)
from scripts.i18n_lupdate import run_lupdate

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from PySide6.QtCore import QEvent


MATPLOTLIB_SPECTRUM_PLOT_QT_SOURCES = {
    "Wavelength [Å]",
    "Flux",
    "Drag to select a masked range",
    "Continuum Reference",
}


@pytest.fixture(name="plot_widget")
def fixture_plot_widget(qtbot: QtBot) -> Iterator[MatplotlibSpectrumPlot]:
    """Create a Matplotlib spectrum plot widget for i18n tests."""

    widget = MatplotlibSpectrumPlot(
        mouse_event_bridge_factory=create_matplotlib_mouse_event_bridge_adapter
    )
    qtbot.addWidget(widget)
    yield widget
    widget.deleteLater()


def _ts_sources(ts_path: Path) -> set[str]:
    """Return source texts extracted into a Qt TS file."""

    tree = ET.parse(ts_path)
    return {source.text for source in tree.findall(".//source") if source.text is not None}


def _axes(widget: MatplotlibSpectrumPlot) -> Axes:
    """Return the Matplotlib axes owned by the plot widget."""

    axes = widget.renderer.axes
    assert axes is not None
    return axes


def test_matplotlib_spectrum_plot_uses_qt_source_text(plot_widget: MatplotlibSpectrumPlot) -> None:
    """Verify migrated plot labels and hints use Qt source text."""

    axes = _axes(plot_widget)
    assert axes.get_xlabel() == "Wavelength [Å]"
    assert axes.get_ylabel() == "Flux"

    plot_widget.begin_mask_selection(100.0)
    assert plot_widget.canvas.toolTip() == "Drag to select a masked range"

    plot_widget.ensure_continuum_reference_line()
    reference_lines = [line for line in axes.lines if line.get_label() == "Continuum Reference"]
    assert len(reference_lines) == 1


class _MouseEvent:
    """Small Matplotlib mouse-event test double."""

    def __init__(self, *, x: float = 10.0, y: float = 20.0, button: int = 1) -> None:
        """Initialize event coordinates."""
        self.x = x
        self.y = y
        self.button = button
        self.xdata = 5000.0
        self.inaxes = None
        self.guiEvent = None


class _Interactor:
    """Collects plot event sink calls."""

    def __init__(self) -> None:
        """Initialize collected calls."""
        self.centered: list[float] = []
        self.left_count = 0
        self.pressed: list[QMouseEvent] = []

    def process_mouse_event(self, event: QEvent) -> None:
        """Accept wheel events."""
        del event

    def handle_mouse_leave(self) -> None:
        """Record mouse leave."""
        self.left_count += 1

    def handle_double_click_center(self, wavelength: float) -> None:
        """Record double-click center requests."""
        self.centered.append(wavelength)

    def handle_mouse_press_event(self, event: object) -> bool:
        """Record mouse press events."""
        assert isinstance(event, QMouseEvent)
        self.pressed.append(event)
        return True

    def handle_mouse_release_event(self, event: object) -> bool:
        """Accept mouse release events."""
        del event
        return True

    def handle_mouse_move_event(self, event: object) -> bool:
        """Accept mouse move events."""
        del event
        return True

    def process_continuum_interaction_event(self, event) -> bool:
        """Accept continuum events."""
        del event
        return True

    def can_process_continuum_event(self) -> bool:
        """Allow continuum events."""
        return True

    def handle_continuum_context_menu(self, position: tuple[float, float]) -> bool:
        """Accept continuum context menu requests."""
        del position
        return True


def test_matplotlib_spectrum_plot_routes_events_to_configured_interactor(
    plot_widget: MatplotlibSpectrumPlot,
) -> None:
    """Plot events should use the configured event sink, not parent traversal."""
    interactor = _Interactor()
    plot_widget.set_input_ports(mouse=interactor, continuum=interactor)

    plot_widget.handle_double_click_centering(_MouseEvent())
    plot_widget.handle_axes_leave(_MouseEvent())
    plot_widget.forward_mouse_event(_MouseEvent(), "press")

    assert interactor.centered == [5000.0]
    assert interactor.left_count == 1
    assert len(interactor.pressed) == 1


def test_matplotlib_spectrum_plot_requires_configured_interactor_for_events(
    plot_widget: MatplotlibSpectrumPlot,
) -> None:
    """Missing event sink is a composition error for bridged plot events."""
    with pytest.raises(RuntimeError, match="requires a mouse input port"):
        plot_widget.handle_double_click_centering(_MouseEvent())


def test_lupdate_extracts_matplotlib_spectrum_plot_sources(tmp_path: Path) -> None:
    """Verify lupdate extracts migrated MatplotlibSpectrumPlot GUI sources."""

    if shutil.which("pyside6-lupdate") is None:
        pytest.skip("pyside6-lupdate is not available")

    ts_path = tmp_path / "matplotlib_spectrum_plot.ts"
    run_lupdate(
        source_dirs=[Path("src/chappy/gui/adapters/plotting/matplotlib_spectrum_plot.py")],
        ts_output=ts_path,
    )

    sources = _ts_sources(ts_path)
    assert MATPLOTLIB_SPECTRUM_PLOT_QT_SOURCES <= sources
    assert not any("GUI__" in source for source in sources)


def test_continuum_reference_line_is_singleton_and_tracks_xlim(
    plot_widget: MatplotlibSpectrumPlot,
) -> None:
    """Avoid recreating the continuum reference line when already present."""
    axes = _axes(plot_widget)

    plot_widget.ensure_continuum_reference_line()
    initial_ref_lines = [line for line in axes.lines if line.get_label() == "Continuum Reference"]
    assert len(initial_ref_lines) == 1
    ref_line = initial_ref_lines[0]

    plot_widget.renderer.axes.set_xlim(2000.0, 3000.0)
    plot_widget.ensure_continuum_reference_line()

    current_ref_lines = [line for line in axes.lines if line.get_label() == "Continuum Reference"]
    assert len(current_ref_lines) == 1
    assert current_ref_lines[0] is ref_line
    np.testing.assert_allclose(current_ref_lines[0].get_xdata(), [2000.0, 3000.0])


def test_clear_continuum_reference_line_removes_only_internal_reference(
    plot_widget: MatplotlibSpectrumPlot,
) -> None:
    """Clear only clears the tracked continuum reference line."""
    axes = _axes(plot_widget)

    (unrelated_line,) = axes.plot([1000.0, 2000.0], [2.0, 2.0], label="Unrelated")
    plot_widget.clear_continuum_reference_line()
    assert unrelated_line in axes.lines

    plot_widget.ensure_continuum_reference_line()
    assert any(line.get_label() == "Continuum Reference" for line in axes.lines)

    plot_widget.clear_continuum_reference_line()
    assert unrelated_line in axes.lines
    assert all(line.get_label() != "Continuum Reference" for line in axes.lines)
