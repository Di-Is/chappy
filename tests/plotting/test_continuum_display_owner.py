"""Unit tests for continuum display ownership."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from chappy.plotting.components.continuum_display import ContinuumDisplayOwner
from chappy.plotting.renderers.base_renderer import PlotStyle, PlotType


@dataclass
class _ReferenceLine:
    xdata: tuple[float, float] | None = None
    label: str | None = None
    removed: bool = False

    def remove(self) -> None:
        self.removed = True

    def set_xdata(self, x: tuple[float, float]) -> None:
        self.xdata = x

    def set_label(self, label: str) -> None:
        self.label = label


@dataclass
class _Axes:
    xlim: tuple[float, float] = (1000.0, 1100.0)
    lines: list[_ReferenceLine] = field(default_factory=list)

    def get_xlim(self) -> tuple[float, float]:
        return self.xlim

    def axhline(self, **kwargs) -> _ReferenceLine:
        line = _ReferenceLine(label=str(kwargs["label"]))
        self.lines.append(line)
        return line


@dataclass
class _Renderer:
    plot_items: dict[str, object] = field(default_factory=dict)
    axes: _Axes = field(default_factory=_Axes)

    def add_curve(
        self, name: str, x, y, plot_type=PlotType.SPECTRUM, style: PlotStyle | None = None
    ) -> object:
        del x, y, plot_type, style
        self.plot_items[name] = object()
        return self.plot_items[name]

    def update_curve(self, name: str, x=None, y=None) -> None:
        del name, x, y

    def remove_curve(self, name: str) -> None:
        self.plot_items.pop(name, None)


@dataclass
class _Canvas:
    draw_idle_calls: int = 0

    def draw_idle(self) -> None:
        self.draw_idle_calls += 1


@dataclass
class _Editor:
    active: bool = False
    points: list[tuple[float, float]] = field(default_factory=list)

    def set_display_active(self, active: bool) -> None:
        self.active = active

    def set_points(self, points: list[tuple[float, float]]) -> None:
        self.points = list(points)


class _StyleRegistry:
    def get_plot_style(self, plot_type: PlotType) -> PlotStyle:
        del plot_type
        return PlotStyle(color="cyan")


def test_continuum_display_owner_tracks_curve_and_reference_line() -> None:
    """Continuum owner should draw the curve, anchors, and reference line."""
    renderer = _Renderer()
    canvas = _Canvas()
    editor = _Editor()
    owner = ContinuumDisplayOwner(
        renderer=renderer, canvas=canvas, continuum_editor=editor, style_registry=_StyleRegistry()
    )

    owner.set_data(
        wavelength=np.array([1000.0, 1010.0]),
        continuum_flux=np.array([1.0, 1.1]),
        anchor_points=[(1000.0, 1.0)],
    )
    owner.ensure_reference_line("Continuum Reference")
    owner.refresh_reference_label("Updated")
    owner.hide_display()

    assert "continuum" not in renderer.plot_items
    assert editor.active is False
    assert editor.points == [(1000.0, 1.0)]
    assert renderer.axes.lines[0].xdata == (1000.0, 1100.0)
    assert renderer.axes.lines[0].label == "Updated"
    assert renderer.axes.lines[0].removed is True
    assert canvas.draw_idle_calls >= 4
