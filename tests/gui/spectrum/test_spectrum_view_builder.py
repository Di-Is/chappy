"""Tests for spectrum view composition fail-fast behavior."""

from __future__ import annotations

import pytest

from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from chappy.gui.spectrum.spectrum_view_builder import SpectrumViewBuilder


class _BuilderView(QWidget):
    """Minimal view double for SpectrumViewBuilder tests."""

    def __init__(self, *, plot_host: object | None = None) -> None:
        """Initialize with typed components."""
        super().__init__()
        self.plot_host = plot_host
        self.registered_plot: QWidget | None = None

    def register_plot_container(
        self, container: QWidget, _stack: object, _plot_widget: QWidget
    ) -> None:
        """Record the plot container registration."""
        self.registered_plot = container


class _PlotComponent:
    """Plot component double."""

    def create_widget(self) -> QWidget:
        """Create a plot widget."""
        return QWidget()


class _InvalidPlotComponent:
    """Invalid plot component double."""

    def create_widget(self) -> object:
        """Return an invalid plot widget."""
        return object()


def test_builder_requires_plot(qtbot: QtBot) -> None:
    """Missing plot is a composition error."""
    view = _BuilderView()
    qtbot.addWidget(view)

    with pytest.raises(TypeError):
        SpectrumViewBuilder(view).build()  # type: ignore[arg-type]


def test_builder_rejects_invalid_plot_widget(qtbot: QtBot) -> None:
    """Invalid plot widget type is a composition error."""
    view = _BuilderView(plot_host=_InvalidPlotComponent())
    qtbot.addWidget(view)

    with pytest.raises(TypeError):
        SpectrumViewBuilder(view).build()  # type: ignore[arg-type]


def test_builder_registers_valid_plot(qtbot: QtBot) -> None:
    """Valid required components build the view."""
    view = _BuilderView(plot_host=_PlotComponent())
    qtbot.addWidget(view)

    SpectrumViewBuilder(view).build()  # type: ignore[arg-type]

    assert view.registered_plot is not None


def test_builder_rejects_rebuild(qtbot: QtBot) -> None:
    """Rebuilding an already-built view is a lifecycle invariant error."""
    view = _BuilderView(plot_host=_PlotComponent())
    qtbot.addWidget(view)
    builder = SpectrumViewBuilder(view)  # type: ignore[arg-type]
    builder.build()

    with pytest.raises(RuntimeError, match="already been built"):
        builder.build()
