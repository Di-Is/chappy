"""Tests for velocity subplot rendering helpers."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from chappy.plotting.component_labels import ComponentLabelEntry
from chappy.plotting.renderers.base_renderer import PlotStyle
from chappy.plotting.velocity import VelocitySubplotRenderer
from chappy.presentation.spectrum import SpectrumComponentCurve
from chappy.presentation.velocity import VelocityAnalysisBounds


class _CanvasSpy(FigureCanvasAgg):
    """Agg canvas recording draw and mpl callback operations."""

    def __init__(self, figure: Figure) -> None:
        super().__init__(figure)
        self.draw_idle_count = 0
        self._next_connection_id = 1
        self.connected_events: list[str] = []
        self.disconnected_ids: list[int] = []

    def draw_idle(self) -> None:
        """Record draw requests."""
        self.draw_idle_count += 1

    def mpl_connect(self, event_name: str, _callback: object) -> int:
        """Record a matplotlib event connection."""
        self.connected_events.append(event_name)
        connection_id = self._next_connection_id
        self._next_connection_id += 1
        return connection_id

    def mpl_disconnect(self, connection_id: int) -> None:
        """Record a matplotlib event disconnection."""
        self.disconnected_ids.append(connection_id)


@dataclass(slots=True)
class _RendererSpy:
    """Renderer spy exposing the minimal interface used by the subplot renderer."""

    figure: Figure
    axes: object
    vertical_lines: list[object] = field(default_factory=list)

    def require_figure(self) -> Figure:
        """Return the configured figure."""
        return self.figure

    def require_axes(self) -> object:
        """Return the configured axes."""
        return self.axes

    def add_vertical_line(
        self, _name: str, position: float, *, style: PlotStyle, label: str | None = None
    ) -> object:
        """Create a simple vertical line on the axes."""
        line = self.axes.axvline(
            position,
            color=style.color,
            linestyle=style.line_style,
            alpha=style.alpha,
            linewidth=style.line_width,
            label=label,
        )
        self.vertical_lines.append(line)
        return line

    def get_range(self) -> tuple[float, float, float, float]:
        """Return axis limits in facade-compatible order."""
        x_min, x_max = self.axes.get_xlim()
        y_min, y_max = self.axes.get_ylim()
        return x_min, x_max, y_min, y_max


@dataclass(slots=True)
class _PlotWidgetSpy:
    """Plot widget spy exposing the minimal facade used by the renderer."""

    renderer: _RendererSpy
    canvas: _CanvasSpy
    observed_calls: list[tuple[np.ndarray, np.ndarray, np.ndarray | None]] = field(
        default_factory=list
    )
    model_calls: list[tuple[np.ndarray, np.ndarray]] = field(default_factory=list)
    residual_calls: list[tuple[np.ndarray, np.ndarray]] = field(default_factory=list)
    clear_residual_count: int = 0
    observed_y_range: tuple[float, float] | None = None
    flux_range: tuple[float, float] | None = None
    component_curve_calls: list[tuple[SpectrumComponentCurve, ...]] = field(default_factory=list)
    clear_component_profiles_count: int = 0

    def clear_residual(self) -> None:
        """Record residual clearing."""
        self.clear_residual_count += 1

    def set_component_profile_spectra(self, curves: tuple[SpectrumComponentCurve, ...]) -> None:
        """Record component transmission curves."""
        self.component_curve_calls.append(curves)

    def clear_component_profiles(self) -> None:
        """Record component curve clearing."""
        self.clear_component_profiles_count += 1

    def set_observed_spectrum(
        self, velocity: np.ndarray, flux: np.ndarray, error: np.ndarray | None
    ) -> None:
        """Record observed spectrum updates."""
        self.observed_calls.append((velocity, flux, error))
        self.observed_y_range = (float(np.min(flux)), float(np.max(flux)))

    def set_model_spectrum(self, velocity: np.ndarray, flux: np.ndarray) -> None:
        """Record model spectrum updates."""
        self.model_calls.append((velocity, flux))

    def set_residual_data(self, velocity: np.ndarray, residual: np.ndarray) -> None:
        """Record residual updates."""
        self.residual_calls.append((velocity, residual))

    def get_observed_y_range(self) -> tuple[float, float] | None:
        """Return recorded observed Y range."""
        return self.observed_y_range

    def set_flux_range(self, min_flux: float, max_flux: float) -> None:
        """Record a flux range update."""
        self.flux_range = (min_flux, max_flux)
        self.renderer.axes.set_ylim(min_flux, max_flux)


def _build_plot_widget() -> _PlotWidgetSpy:
    """Create a fake plot widget backed by a real matplotlib figure."""
    figure = Figure()
    canvas = _CanvasSpy(figure)
    axes = figure.add_subplot(111)
    renderer = _RendererSpy(figure=figure, axes=axes)
    return _PlotWidgetSpy(renderer=renderer, canvas=canvas)


def test_set_data_applies_window_limits() -> None:
    """Observed velocity data should update ranges and draw state."""
    plot_widget = _build_plot_widget()
    renderer = VelocitySubplotRenderer(plot_widget)
    velocity = np.array([-10.0, 0.0, 10.0], dtype=np.float64)
    flux = np.array([0.9, 1.0, 1.1], dtype=np.float64)
    error = np.array([0.1, 0.1, 0.1], dtype=np.float64)

    rendered = renderer.set_data(velocity, flux, error, 250.0)

    assert rendered is True
    assert plot_widget.clear_residual_count == 1
    assert len(plot_widget.observed_calls) == 1
    assert plot_widget.renderer.axes.get_xlim() == (-250.0, 250.0)


def test_analysis_bounds_are_separate_from_display_limits_and_include_text_notice() -> None:
    """Analysis artists should not change the display X limits."""
    plot_widget = _build_plot_widget()
    renderer = VelocitySubplotRenderer(plot_widget)
    velocity = np.array([-100.0, 0.0, 100.0], dtype=np.float64)
    flux = np.array([0.9, 1.0, 1.1], dtype=np.float64)
    renderer.set_data(velocity, flux, None, 200.0)

    renderer.set_analysis_bounds(
        VelocityAnalysisBounds.from_half_width(350.0),
        out_of_view_message="Analysis range extends beyond view (±350 km/s)",
    )

    assert plot_widget.renderer.axes.get_xlim() == (-200.0, 200.0)
    assert renderer.analysis_boundary_count() == 2
    assert renderer.analysis_out_of_view_text() == (
        "↔ Analysis range extends beyond view (±350 km/s)"
    )

    renderer.clear_analysis_bounds()
    assert renderer.analysis_boundary_count() == 0
    assert renderer.analysis_out_of_view_text() is None


def test_drag_overlay_reuses_single_artist_and_can_be_cleared() -> None:
    """Drag overlay should update an existing line instead of allocating a new one."""
    plot_widget = _build_plot_widget()
    renderer = VelocitySubplotRenderer(plot_widget)

    renderer.update_drag_overlay(10.0)
    renderer.update_drag_overlay(20.0)

    assert renderer.has_drag_overlay() is True
    assert len(plot_widget.renderer.axes.lines) == 1
    assert list(plot_widget.renderer.axes.lines[0].get_xdata()) == [20.0, 20.0]

    renderer.clear_drag_overlay()

    assert renderer.has_drag_overlay() is False
    assert len(plot_widget.renderer.axes.lines) == 0


def test_set_component_markers_draws_line_and_annotation_per_marker() -> None:
    """Each supplied entry should draw one line and one annotation."""
    plot_widget = _build_plot_widget()
    renderer = VelocitySubplotRenderer(plot_widget)

    renderer.set_component_markers(
        [ComponentLabelEntry(x=10.0, text="c1 [A]"), ComponentLabelEntry(x=-20.0, text="c2")]
    )

    axes = plot_widget.renderer.axes
    assert len(axes.lines) == 2
    assert {text.get_text() for text in axes.texts} == {"c1 [A]", "c2"}


def test_set_component_markers_clears_previous_markers_on_reapply() -> None:
    """Reapplying markers should not accumulate stale artists."""
    plot_widget = _build_plot_widget()
    renderer = VelocitySubplotRenderer(plot_widget)

    renderer.set_component_markers([ComponentLabelEntry(x=10.0, text="c1")])
    renderer.set_component_markers(
        [ComponentLabelEntry(x=5.0, text="c2"), ComponentLabelEntry(x=15.0, text="c3")]
    )

    axes = plot_widget.renderer.axes
    assert len(axes.lines) == 2
    assert {text.get_text() for text in axes.texts} == {"c2", "c3"}


def test_clear_component_markers_removes_all_artists() -> None:
    """Clearing should remove both the vertical lines and their annotations."""
    plot_widget = _build_plot_widget()
    renderer = VelocitySubplotRenderer(plot_widget)

    renderer.set_component_markers(
        [ComponentLabelEntry(x=10.0, text="c1"), ComponentLabelEntry(x=-5.0, text="c2")]
    )
    renderer.clear_component_markers()

    axes = plot_widget.renderer.axes
    assert len(axes.lines) == 0
    assert len(axes.texts) == 0


def test_connect_and_disconnect_mouse_events_use_canvas_callbacks() -> None:
    """Mouse callback wiring should stay entirely on the matplotlib canvas side."""
    plot_widget = _build_plot_widget()
    renderer = VelocitySubplotRenderer(plot_widget)

    renderer.connect_mouse_events(lambda _event: None, lambda _event: None, lambda _event: None)
    renderer.disconnect_mouse_events()

    assert plot_widget.canvas.connected_events == [
        "button_press_event",
        "motion_notify_event",
        "button_release_event",
    ]
    assert plot_widget.canvas.disconnected_ids == [1, 2, 3]


def test_component_profile_curves_reach_the_shared_spectrum_facade() -> None:
    """Velocity subplots reuse the spectrum facade's component curve rendering."""
    plot_widget = _build_plot_widget()
    renderer = VelocitySubplotRenderer(plot_widget)
    curve = SpectrumComponentCurve(
        component_id="abs-1",
        color="#1B9E77",
        wavelength=np.array([-10.0, 0.0, 10.0], dtype=np.float64),
        flux=np.array([1.0, 0.8, 1.0], dtype=np.float64),
    )

    renderer.set_component_profile_curves([curve])

    assert plot_widget.component_curve_calls == [(curve,)]


def test_clearing_component_profile_curves_reaches_the_shared_spectrum_facade() -> None:
    """Clearing a subplot drops its component curves through the same facade."""
    plot_widget = _build_plot_widget()
    renderer = VelocitySubplotRenderer(plot_widget)

    renderer.clear_component_profile_curves()

    assert plot_widget.clear_component_profiles_count == 1
