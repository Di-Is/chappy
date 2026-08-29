"""Tests for plot coordinate transformation utilities."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from chappy.gui.utils.plot_coordinate_transform import PlotCoordinateTransform


@dataclass(slots=True)
class _Canvas:
    """Minimal canvas surface used by PlotCoordinateTransform."""

    width_value: int = 800
    height_value: int = 600
    dpi_ratio: float = 1.5

    def width(self) -> int:
        """Return canvas width in Qt logical pixels."""
        return self.width_value

    def height(self) -> int:
        """Return canvas height in Qt logical pixels."""
        return self.height_value

    def devicePixelRatio(self) -> float:  # noqa: N802
        """Return the configured device pixel ratio."""
        return self.dpi_ratio


@dataclass(slots=True)
class _DataTransform:
    """Data transform fake that can either return a point or fail."""

    result: tuple[float, float] = (5000.0, 1.0)
    error: Exception | None = None

    def transform(self, _position: tuple[float, float]) -> tuple[float, float]:
        """Return configured data coordinates."""
        if self.error is not None:
            raise self.error
        return self.result


@dataclass(slots=True)
class _TransData:
    """Matplotlib transData fake recording inversion use."""

    inverse: _DataTransform
    inverted_count: int = 0

    def inverted(self) -> _DataTransform:
        """Return the inverse transform and record the request."""
        self.inverted_count += 1
        return self.inverse


@dataclass(slots=True)
class _Axes:
    """Axes fake exposing transData."""

    transData: _TransData


@dataclass(slots=True)
class _Renderer:
    """Renderer fake exposing axes."""

    axes: _Axes | None


@dataclass(slots=True)
class _PlotWidget:
    """Plot widget fake exposing canvas and renderer."""

    canvas: _Canvas
    renderer: _Renderer


@pytest.fixture
def plot_widget() -> _PlotWidget:
    """Create plot widget fake with canvas and renderer."""
    return _PlotWidget(
        canvas=_Canvas(),
        renderer=_Renderer(axes=_Axes(transData=_TransData(inverse=_DataTransform()))),
    )


@pytest.fixture
def transform(plot_widget: _PlotWidget) -> PlotCoordinateTransform:
    """Create transform instance with a stateful plot widget fake."""
    return PlotCoordinateTransform(plot_widget)


class TestPlotCoordinateTransform:
    """Test suite for plot coordinate transformation."""

    def test_qt_to_data_coordinates(
        self, transform: PlotCoordinateTransform, plot_widget: _PlotWidget
    ) -> None:
        """Test Qt to data coordinate conversion."""
        result = transform.qt_to_data_coordinates(400, 300)

        assert result == (5000.0, 1.0)
        assert plot_widget.renderer.axes is not None
        assert plot_widget.renderer.axes.transData.inverted_count == 1

    def test_is_valid_position(self, transform: PlotCoordinateTransform) -> None:
        """Test position validation logic."""
        assert transform.is_valid_position(400.0, 300.0) is True
        assert transform.is_valid_position(-5.0, 100.0) is False
        assert transform.is_valid_position(900.0, 100.0) is False
        assert transform.is_valid_position(100.0, 700.0) is False

    def test_invalid_transform_marks_position_invalid(
        self, transform: PlotCoordinateTransform, plot_widget: _PlotWidget
    ) -> None:
        """Coordinate transform failures should make a position invalid."""
        assert plot_widget.renderer.axes is not None
        plot_widget.renderer.axes.transData.inverse.error = ValueError("conversion failed")

        assert transform.is_valid_position(400.0, 300.0) is False

    def test_handle_missing_axes(self, plot_widget: _PlotWidget) -> None:
        """Test handling when axes are not available."""
        plot_widget.renderer.axes = None
        transform = PlotCoordinateTransform(plot_widget)

        with pytest.raises(ValueError):
            transform.qt_to_data_coordinates(400.0, 300.0)
