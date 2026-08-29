"""Integration tests for spectrum plot facade data flow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from matplotlib.backend_bases import LocationEvent, MouseEvent
from matplotlib.lines import Line2D
import numpy as np
from numpy.typing import NDArray
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

pytest.importorskip("PySide6")

from pytestqt.qtbot import QtBot

from chappy.gui.adapters.plotting import (
    MatplotlibSpectrumPlot,
    create_matplotlib_mouse_event_bridge_adapter,
)
from chappy.gui.spectrum.interaction.input.binding.spectrum_plot_input_binding import (
    SpectrumPlotInputBinding,
)
from chappy.presentation.interaction.interaction_contracts import (
    InteractionChannel,
    InteractionEvent,
    InteractionEventKind,
)
from chappy.presentation.spectrum import AbsorptionMarkerInput, SpectrumPlotDisplayCommand
from chappy.presentation.spectrum.visual_tokens import SpectrumVisuals


@dataclass(frozen=True)
class PlotProjectFixture:
    """Small project-like data container for plotting tests."""

    wavelength: NDArray[np.float64]
    flux: NDArray[np.float64]
    error: NDArray[np.float64]
    model_flux: NDArray[np.float64]
    continuum: NDArray[np.float64]
    groups: list[object]


def _line_from_plot(widget: MatplotlibSpectrumPlot, name: str) -> Line2D:
    """Return a rendered line from the Matplotlib renderer."""
    item = widget.renderer.plot_items[name]
    assert isinstance(item, Line2D)
    return item


def _vertical_line_from_plot(widget: MatplotlibSpectrumPlot, name: str) -> Line2D:
    """Return a rendered vertical marker from the Matplotlib renderer."""
    item = widget.renderer.axvline_items[name]
    assert isinstance(item, Line2D)
    return item


def _callback_count(widget: MatplotlibSpectrumPlot, event_name: str) -> int:
    """Return the number of callbacks registered for one Matplotlib event."""
    return len(widget.canvas.callbacks.callbacks.get(event_name, {}))


def _lya_marker() -> AbsorptionMarkerInput:
    """Return a Lyman-alpha marker payload for component label tests."""
    return AbsorptionMarkerInput(
        name="Lya",
        rest_wavelength=1215.67,
        redshift=2.0,
        column_density=14.0,
        b_parameter=20.0,
        oscillator_strength=0.4164,
        gamma=6.265e8,
    )


def _component_label_anchors(widget: MatplotlibSpectrumPlot) -> list[float]:
    """Return the axes-fraction band top each component label hangs from."""
    return [float(label.xy[1]) for label in widget._absorber_marker_overlay._labels.values()]


class _BackendGuiEvent:
    """Backend guiEvent replacement exposing modifiers."""

    def __init__(self, modifiers: Qt.KeyboardModifier) -> None:
        """Initialize with a modifier mask."""
        self._modifiers = modifiers

    def modifiers(self) -> Qt.KeyboardModifier:
        """Return keyboard modifiers."""
        return self._modifiers


class _BrokenBackendGuiEvent:
    """Backend guiEvent that cannot provide modifiers."""

    def modifiers(self) -> Qt.KeyboardModifier:
        """Always fail when reading modifiers."""
        msg = "backend guiEvent does not support modifiers"
        raise RuntimeError(msg)


class _BridgeMouseEvent:
    """Matplotlib-like mouse event for local forwarding path tests."""

    def __init__(
        self,
        *,
        x: float = 10.0,
        y: float = 20.0,
        button: int = 1,
        guiEvent: object | None = None,
        xdata: float = 5000.0,
        inaxes: object | None = None,
        dblclick: bool = False,
    ) -> None:
        """Initialize a lightweight mouse event payload."""
        self.x = x
        self.y = y
        self.button = button
        self.guiEvent = guiEvent
        self.xdata = xdata
        self.inaxes = inaxes
        self.dblclick = dblclick


class _BridgeInteractor:
    """Capture mouse events and their modifiers for assertions."""

    def __init__(self) -> None:
        """Initialize capture buffers."""
        self.pressed: list[QMouseEvent] = []
        self.centered: list[float] = []
        self.left_count = 0
        self.continuum_events: list[InteractionEvent] = []

    def process_mouse_event(self, event) -> None:
        """Accept wheel events."""
        del event

    def handle_mouse_leave(self) -> None:
        """Capture cursor-leave events."""
        self.left_count += 1

    def handle_double_click_center(self, wavelength: float) -> None:
        """Capture double-click center requests."""
        self.centered.append(wavelength)

    def handle_mouse_press_event(self, event: object) -> bool:
        """Capture mouse press events."""
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

    def can_process_continuum_event(self) -> bool:
        """Allow continuum events."""
        return True

    def process_continuum_interaction_event(self, event: InteractionEvent) -> bool:
        """Capture continuum events."""
        self.continuum_events.append(event)
        return True


class TestMatplotlibSpectrumPlotDataFlow:
    """Test plotting data flow through real Matplotlib renderer state."""

    @pytest.fixture
    def project_fixture(self) -> PlotProjectFixture:
        """Create project-like spectral data."""
        wavelength = np.linspace(1200.0, 1300.0, 100)
        return PlotProjectFixture(
            wavelength=wavelength,
            flux=np.ones(100),
            error=np.ones(100) * 0.1,
            model_flux=np.ones(100) * 0.95,
            continuum=np.ones(100),
            groups=[],
        )

    @pytest.fixture
    def plot_widget(self, qtbot: QtBot) -> Iterator[MatplotlibSpectrumPlot]:
        """Create a MatplotlibSpectrumPlot with the real renderer."""
        widget = MatplotlibSpectrumPlot(
            mouse_event_bridge_factory=create_matplotlib_mouse_event_bridge_adapter
        )
        qtbot.addWidget(widget)

        yield widget

        widget.deleteLater()

    def test_curve_owner_integration(self, plot_widget: MatplotlibSpectrumPlot) -> None:
        """Facade should compose a dedicated curve owner."""
        assert plot_widget._curve_owner is not None

    def test_forwarded_mouse_event_prefers_gui_event_modifiers(
        self, plot_widget: MatplotlibSpectrumPlot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Forwarded mouse press events should prefer modifiers from backend guiEvent."""
        interactor = _BridgeInteractor()
        plot_widget.set_input_ports(mouse=interactor, continuum=interactor)
        monkeypatch.setattr(
            QApplication, "keyboardModifiers", lambda: Qt.KeyboardModifier.ControlModifier
        )

        plot_widget.forward_mouse_event(
            _BridgeMouseEvent(guiEvent=_BackendGuiEvent(Qt.KeyboardModifier.ShiftModifier)),
            "press",
        )

        assert interactor.pressed[-1].modifiers() == Qt.KeyboardModifier.ShiftModifier

    def test_forwarded_mouse_event_falls_back_when_backend_modifiers_fail(
        self, plot_widget: MatplotlibSpectrumPlot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Broken backend guiEvent.modifiers should fall back to QApplication.keyboardModifiers."""
        interactor = _BridgeInteractor()
        plot_widget.set_input_ports(mouse=interactor, continuum=interactor)
        monkeypatch.setattr(
            QApplication, "keyboardModifiers", lambda: Qt.KeyboardModifier.ControlModifier
        )

        plot_widget.forward_mouse_event(
            _BridgeMouseEvent(guiEvent=_BrokenBackendGuiEvent()), "press"
        )

        assert interactor.pressed[-1].modifiers() == Qt.KeyboardModifier.ControlModifier

    def test_axes_leave_callback_follows_interactor_lifecycle(
        self, plot_widget: MatplotlibSpectrumPlot
    ) -> None:
        """Axes-leave routing should connect once and disconnect with its event sink."""
        first_interactor = _BridgeInteractor()
        second_interactor = _BridgeInteractor()

        assert _callback_count(plot_widget, "axes_leave_event") == 0

        plot_widget.set_input_ports(mouse=first_interactor, continuum=first_interactor)
        assert _callback_count(plot_widget, "axes_leave_event") == 1

        plot_widget.set_input_ports(mouse=second_interactor, continuum=second_interactor)
        assert _callback_count(plot_widget, "axes_leave_event") == 1

        LocationEvent("axes_leave_event", plot_widget.canvas, x=0, y=0)._process()
        assert first_interactor.left_count == 0
        assert second_interactor.left_count == 1

        plot_widget.set_input_ports(mouse=None, continuum=None)
        assert _callback_count(plot_widget, "axes_leave_event") == 0

        LocationEvent("axes_leave_event", plot_widget.canvas, x=0, y=0)._process()
        assert second_interactor.left_count == 1

    def test_input_ports_reject_partial_attachment(
        self, plot_widget: MatplotlibSpectrumPlot
    ) -> None:
        """Mouse and continuum ports must never enter a partially attached state."""
        interactor = _BridgeInteractor()

        with pytest.raises(ValueError, match="must be attached or detached together"):
            plot_widget.set_input_ports(mouse=interactor, continuum=None)

        assert _callback_count(plot_widget, "axes_leave_event") == 0
        assert plot_widget.continuum_editor._interactor is None

    def test_motion_from_axes_to_outside_emits_one_leave_event(
        self, plot_widget: MatplotlibSpectrumPlot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One inside-to-outside transition should emit one cursor-leave notification."""
        interactor = _BridgeInteractor()
        plot_widget.set_input_ports(mouse=interactor, continuum=interactor)
        plot_widget.canvas.draw()
        monkeypatch.setattr(LocationEvent, "_last_axes_ref", None)

        axes = plot_widget.renderer.axes
        assert axes is not None
        inside_x = (axes.bbox.x0 + axes.bbox.x1) / 2
        inside_y = (axes.bbox.y0 + axes.bbox.y1) / 2

        MouseEvent("motion_notify_event", plot_widget.canvas, x=inside_x, y=inside_y)._process()
        MouseEvent("motion_notify_event", plot_widget.canvas, x=0, y=0)._process()

        assert interactor.left_count == 1

    def test_dispose_disconnects_axes_leave_callback(
        self, plot_widget: MatplotlibSpectrumPlot
    ) -> None:
        """Disposed plots should not retain event-sink callbacks."""
        interactor = _BridgeInteractor()
        plot_widget.set_input_ports(mouse=interactor, continuum=interactor)
        canvas = plot_widget.canvas

        plot_widget.dispose()

        assert len(canvas.callbacks.callbacks.get("axes_leave_event", {})) == 0
        LocationEvent("axes_leave_event", canvas, x=0, y=0)._process()
        assert interactor.left_count == 0

    def test_binding_routes_continuum_events_to_the_dedicated_port(
        self, plot_widget: MatplotlibSpectrumPlot
    ) -> None:
        """The real plot must not send continuum events to the mouse-only binding."""
        binding = SpectrumPlotInputBinding()
        event_sink = _BridgeInteractor()
        binding.attach_plot_widget(plot_widget, event_sink=event_sink)
        event = InteractionEvent(
            channel=InteractionChannel.CONTINUUM,
            kind=InteractionEventKind.CONTINUUM_SELECT,
            position=(1250.0, 1.0),
        )

        assert plot_widget.continuum_editor._send_interaction_event(event) is True
        assert event_sink.continuum_events == [event]

    def test_observed_data_flow(self, plot_widget: MatplotlibSpectrumPlot) -> None:
        """Observed data should flow into the store and rendered curves."""
        wavelength = np.linspace(1200, 1300, 100)
        flux = np.random.random(100)
        error = np.ones(100) * 0.1

        plot_widget.set_observed_spectrum(wavelength, flux, error)

        observed_data = plot_widget.data_store.get_observed_data()
        assert observed_data is not None
        assert np.array_equal(observed_data["wavelength"], wavelength)
        assert np.array_equal(observed_data["flux"], flux)
        assert np.array_equal(observed_data["error"], error)

        observed_line = _line_from_plot(plot_widget, "observed")
        error_line = _line_from_plot(plot_widget, "error")
        np.testing.assert_array_equal(observed_line.get_xdata(), wavelength)
        np.testing.assert_array_equal(observed_line.get_ydata(), flux)
        np.testing.assert_array_equal(error_line.get_xdata(), wavelength)
        np.testing.assert_array_equal(error_line.get_ydata(), error)

    def test_model_data_flow_with_project(
        self, plot_widget: MatplotlibSpectrumPlot, project_fixture: PlotProjectFixture
    ) -> None:
        """Model data should flow into the store and rendered model curve."""
        plot_widget.set_project(project_fixture)

        wavelength = project_fixture.wavelength
        flux = project_fixture.model_flux
        plot_widget.set_model_spectrum(wavelength, flux)

        model_data = plot_widget.data_store.get_model_data()
        assert model_data is not None
        assert np.array_equal(model_data["wavelength"], wavelength)
        assert np.array_equal(model_data["flux"], flux)

        model_line = _line_from_plot(plot_widget, "model")
        np.testing.assert_array_equal(model_line.get_xdata(), wavelength)
        np.testing.assert_array_equal(model_line.get_ydata(), flux)

    def test_absorption_marker_flow(self, plot_widget: MatplotlibSpectrumPlot) -> None:
        """Absorption marker data should remain stored and rendered."""
        component_id = plot_widget.add_absorption_marker(
            AbsorptionMarkerInput(
                name="Lya",
                rest_wavelength=1215.67,
                redshift=2.0,
                column_density=14.0,
                b_parameter=20.0,
                oscillator_strength=0.4164,
                gamma=6.265e8,
            )
        )

        assert component_id in plot_widget.absorption_markers
        marker_data = plot_widget.absorption_markers[component_id]
        assert marker_data["name"] == "Lya"
        assert marker_data["rest_wavelength"] == 1215.67
        assert marker_data["redshift"] == 2.0

        marker_line = _vertical_line_from_plot(plot_widget, f"marker_{component_id}")
        assert marker_line.get_xdata()[0] == pytest.approx(1215.67 * 3.0)

        plot_widget.update_absorption_marker_redshift(component_id, 2.25)

        assert marker_data["redshift"] == pytest.approx(2.25)
        assert marker_line.get_xdata()[0] == pytest.approx(1215.67 * 3.25)

    def test_overlay_renderer_integration(self, plot_widget: MatplotlibSpectrumPlot) -> None:
        """Overlay rendering should keep marker curves independent."""
        lya_id = plot_widget.add_absorption_marker(
            AbsorptionMarkerInput(
                name="Lya",
                rest_wavelength=1215.67,
                redshift=2.0,
                column_density=14.0,
                b_parameter=20.0,
                oscillator_strength=0.4164,
                gamma=6.265e8,
            )
        )
        civ_id = plot_widget.add_absorption_marker(
            AbsorptionMarkerInput(
                name="CIV",
                rest_wavelength=1548.20,
                redshift=2.0,
                column_density=14.0,
                b_parameter=20.0,
                oscillator_strength=0.19,
                gamma=2.65e8,
            )
        )

        lya_line = _vertical_line_from_plot(plot_widget, f"marker_{lya_id}")
        civ_line = _vertical_line_from_plot(plot_widget, f"marker_{civ_id}")
        assert lya_line.get_xdata()[0] == pytest.approx(1215.67 * 3.0)
        assert civ_line.get_xdata()[0] == pytest.approx(1548.20 * 3.0)

    def test_component_labels_hang_under_the_absorption_line_labels(
        self, plot_widget: MatplotlibSpectrumPlot
    ) -> None:
        """Drawn line labels push the component label band down below themselves."""
        plot_widget.apply_display_command(
            SpectrumPlotDisplayCommand(
                use_normalized_observed=False, render_absorption_line_labels=True
            )
        )
        plot_widget.add_absorption_marker(_lya_marker())

        plot_widget.set_absorption_line_regions(
            [{"lambda_start": 3600.0, "lambda_end": 3700.0, "label": "LyA", "label_y": 0.92}]
        )

        assert _component_label_anchors(plot_widget) == [pytest.approx(0.91)]

    def test_component_labels_reach_the_top_without_line_labels(
        self, plot_widget: MatplotlibSpectrumPlot
    ) -> None:
        """Without line labels the component labels use the full band."""
        plot_widget.add_absorption_marker(_lya_marker())

        plot_widget.set_absorption_line_regions([])

        assert _component_label_anchors(plot_widget) == [pytest.approx(0.985)]

    def test_zooming_replaces_the_component_labels(
        self, plot_widget: MatplotlibSpectrumPlot
    ) -> None:
        """Changing the X limits re-places labels against the new pixel spacing."""
        plot_widget.add_absorption_marker(_lya_marker())
        plot_widget.set_absorption_line_regions([])
        before = list(plot_widget._absorber_marker_overlay._labels.values())

        plot_widget._axes.set_xlim(3600.0, 3700.0)

        after = list(plot_widget._absorber_marker_overlay._labels.values())
        assert [id(label) for label in after] != [id(label) for label in before]

    def test_selected_component_label_reaches_the_overlay(
        self, plot_widget: MatplotlibSpectrumPlot
    ) -> None:
        """The facade forwards the selected component down to its marker label."""
        component_id = plot_widget.add_absorption_marker(_lya_marker())
        plot_widget.set_absorption_line_regions([])

        plot_widget.set_selected_component_id(component_id)

        labels = plot_widget._absorber_marker_overlay._labels
        assert labels[component_id].get_fontweight() == "bold"

    def test_absorption_marker_requires_physical_payload(
        self, plot_widget: MatplotlibSpectrumPlot
    ) -> None:
        """Typed marker payload requires all physical inputs."""
        with pytest.raises(TypeError):
            AbsorptionMarkerInput(  # type: ignore[call-arg]
                name="Lya",
                rest_wavelength=1215.67,
                redshift=2.0,
                b_parameter=20.0,
                oscillator_strength=0.4164,
                gamma=6.265e8,
            )

    def test_absorption_marker_rejects_malformed_physical_values(
        self, plot_widget: MatplotlibSpectrumPlot
    ) -> None:
        """Direct marker API validates physical values instead of defaulting."""
        with pytest.raises(ValueError, match="oscillator_strength"):
            plot_widget.add_absorption_marker(
                AbsorptionMarkerInput(
                    name="Lya",
                    rest_wavelength=1215.67,
                    redshift=2.0,
                    column_density=14.0,
                    b_parameter=20.0,
                    oscillator_strength=float("nan"),
                    gamma=6.265e8,
                )
            )

    def test_set_absorption_line_regions_accepts_empty_payload(
        self, plot_widget: MatplotlibSpectrumPlot
    ) -> None:
        """Empty regions should clear overlays without raising."""
        plot_widget.set_absorption_line_regions([{"lambda_start": 1000.0, "lambda_end": 1010.0}])
        assert plot_widget.renderer.get_region("line_region_1") is not None

        plot_widget.set_absorption_line_regions([])
        assert plot_widget.renderer.get_region("line_region_1") is None

    def test_set_absorption_line_regions_accepts_valid_payload(
        self, plot_widget: MatplotlibSpectrumPlot
    ) -> None:
        """Validated payload should remain drawable without mutation."""
        plot_widget.set_absorption_line_regions(
            [{"lambda_start": "1000.0", "lambda_end": 1020, "label": "LyA"}]
        )

        assert plot_widget.renderer.get_region("line_region_1") is not None

    def test_absorption_line_region_labels_follow_display_command(
        self, plot_widget: MatplotlibSpectrumPlot
    ) -> None:
        """Absorption-line label rendering should follow caller-owned display policy."""
        region = [{"lambda_start": 1000.0, "lambda_end": 1020.0, "label": "LyA"}]

        plot_widget.apply_display_command(
            SpectrumPlotDisplayCommand(
                use_normalized_observed=False, render_absorption_line_labels=False
            )
        )
        plot_widget.set_absorption_line_regions(region)
        assert plot_widget._line_region_overlay.labels == []

        plot_widget.apply_display_command(
            SpectrumPlotDisplayCommand(
                use_normalized_observed=False, render_absorption_line_labels=True
            )
        )
        plot_widget.set_absorption_line_regions(region)
        assert len(plot_widget._line_region_overlay.labels) == 1

    def test_set_absorption_line_regions_rejects_missing_bounds(
        self, plot_widget: MatplotlibSpectrumPlot
    ) -> None:
        """Missing lambda bounds must raise immediately."""
        with pytest.raises(ValueError, match="requires both"):
            plot_widget.set_absorption_line_regions([{"label": "LyA"}])

    def test_set_absorption_line_regions_rejects_non_finite_bounds(
        self, plot_widget: MatplotlibSpectrumPlot
    ) -> None:
        """Non-finite payload values should fail rather than coerce defaults."""
        with pytest.raises(ValueError, match="must be finite"):
            plot_widget.set_absorption_line_regions(
                [{"lambda_start": float("nan"), "lambda_end": 1020.0}]
            )

        with pytest.raises(ValueError, match="must be finite"):
            plot_widget.set_absorption_line_regions(
                [{"lambda_start": 1000.0, "lambda_end": float("inf")}]
            )

    def test_set_absorption_line_regions_rejects_invalid_order(
        self, plot_widget: MatplotlibSpectrumPlot
    ) -> None:
        """Invalid region boundaries should fail-fast."""
        with pytest.raises(ValueError, match="lambda_start < lambda_end"):
            plot_widget.set_absorption_line_regions(
                [{"lambda_start": 1100.0, "lambda_end": 1000.0}]
            )

    def test_error_spectrum_always_displayed(self, plot_widget: MatplotlibSpectrumPlot) -> None:
        """Error spectrum is always displayed when available."""
        wavelength = np.linspace(1200, 1300, 100)
        flux = np.random.random(100)
        error = np.ones(100) * 0.1

        plot_widget.set_observed_spectrum(wavelength, flux, error)

        assert "error" in plot_widget.renderer.plot_items
        error_line = _line_from_plot(plot_widget, "error")
        np.testing.assert_array_equal(error_line.get_ydata(), error)

    def test_zoom_after_clear_redecimates_observed_curve(
        self, plot_widget: MatplotlibSpectrumPlot
    ) -> None:
        """Axis-limit callbacks must survive clear_plot so zooming re-decimates."""
        n = 100_000
        wavelength = np.linspace(3000.0, 10000.0, n)
        flux = np.random.random(n)

        plot_widget.set_observed_spectrum(wavelength, flux, None)
        plot_widget.clear_plot()
        plot_widget.set_observed_spectrum(wavelength, flux, None)
        plot_widget.set_wavelength_range(3000.0, 10000.0)
        plot_widget.set_wavelength_range(8000.0, 8400.0)

        observed = _line_from_plot(plot_widget, "observed")
        x_data = np.asarray(observed.get_xdata())
        assert len(x_data) < n
        assert x_data.min() >= 8000.0 - 2 * 400.0
        assert x_data.max() <= 8400.0 + 2 * 400.0

    def test_render_while_zoomed_keeps_viewport_resolution(
        self, plot_widget: MatplotlibSpectrumPlot
    ) -> None:
        """Re-renders while zoomed must re-decimate for the current viewport."""
        n = 100_000
        wavelength = np.linspace(3000.0, 10000.0, n)
        flux = np.random.random(n)

        plot_widget.set_observed_spectrum(wavelength, flux, None)
        plot_widget.set_wavelength_range(3000.0, 10000.0)
        plot_widget.set_wavelength_range(8000.0, 8400.0)

        plot_widget.apply_display_command(
            SpectrumPlotDisplayCommand(
                use_normalized_observed=False, render_absorption_line_labels=False
            )
        )
        plot_widget.set_model_spectrum(wavelength, flux * 0.9)

        for name in ("observed", "model"):
            x_data = np.asarray(_line_from_plot(plot_widget, name).get_xdata())
            assert x_data.min() >= 8000.0 - 2 * 400.0
            assert x_data.max() <= 8400.0 + 2 * 400.0

    def test_apply_display_command_skips_rerender_for_same_command(
        self, plot_widget: MatplotlibSpectrumPlot
    ) -> None:
        """Re-applying the current display command must not re-render observed."""
        wavelength = np.linspace(1200.0, 1300.0, 100)
        plot_widget.set_observed_spectrum(wavelength, np.random.random(100), None)
        command = SpectrumPlotDisplayCommand(
            use_normalized_observed=False, render_absorption_line_labels=False
        )
        plot_widget.apply_display_command(command)
        render_calls: list[int] = []
        original_render = plot_widget._curve_owner.render_observed
        plot_widget._curve_owner.render_observed = (  # type: ignore[method-assign]
            lambda **kwargs: (render_calls.append(1), original_render(**kwargs))[1]
        )

        plot_widget.apply_display_command(command)

        assert render_calls == []

    def test_residual_data_flow(self, plot_widget: MatplotlibSpectrumPlot) -> None:
        """Residual data should flow into the store and rendered residual curve."""
        wavelength = np.linspace(1200, 1300, 100)
        residual = np.random.random(100) * 0.1

        plot_widget.set_residual_data(wavelength, residual)

        residual_data = plot_widget.data_store.get_residual_data()
        assert residual_data is not None
        assert np.array_equal(residual_data["wavelength"], wavelength)
        assert np.array_equal(residual_data["residuals"], residual)

        residual_line = _line_from_plot(plot_widget, "residual")
        np.testing.assert_array_equal(residual_line.get_xdata(), wavelength)
        np.testing.assert_array_equal(residual_line.get_ydata(), -residual)
        assert residual_line.get_drawstyle() == SpectrumVisuals.RESIDUAL_DRAWSTYLE

    def test_rendered_curves_keep_separate_plot_items(
        self, plot_widget: MatplotlibSpectrumPlot
    ) -> None:
        """Observed, model, and residual curves should not overwrite one another."""
        wavelength = np.linspace(1200, 1300, 100)
        flux = np.random.random(100)
        model_flux = np.random.random(100)
        residual = np.random.random(100) * 0.1

        plot_widget.set_observed_spectrum(wavelength, flux, np.ones(100) * 0.1)
        plot_widget.set_model_spectrum(wavelength, model_flux)
        plot_widget.set_residual_data(wavelength, residual)

        assert {"observed", "model", "residual"}.issubset(plot_widget.renderer.plot_items)

    def test_clear_residual_removes_curve(self, plot_widget: MatplotlibSpectrumPlot) -> None:
        """clear_residual should remove residual curve from renderer."""
        wavelength = np.linspace(1200, 1300, 100)
        residual = np.random.random(100) * 0.1

        plot_widget.set_residual_data(wavelength, residual)
        plot_widget.clear_residual()

        assert "residual" not in plot_widget.renderer.plot_items

    def test_clear_residual_clears_data_store(self, plot_widget: MatplotlibSpectrumPlot) -> None:
        """clear_residual should clear residual in the data store."""
        wavelength = np.linspace(1200, 1300, 100)
        residual = np.random.random(100) * 0.1

        plot_widget.set_residual_data(wavelength, residual)
        assert plot_widget.data_store.get_residual_data() is not None

        plot_widget.clear_residual()

        assert plot_widget.data_store.get_residual_data() is None

    def test_clear_residual_noop_when_no_residual(
        self, plot_widget: MatplotlibSpectrumPlot
    ) -> None:
        """clear_residual should not raise when no residual exists."""
        plot_widget.renderer.plot_items = {}
        plot_widget.clear_residual()
        assert plot_widget.data_store.get_residual_data() is None

    def test_set_mode_propagates_observed_plot_refresh_failure(
        self, plot_widget: MatplotlibSpectrumPlot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Display-command changes should not hide observed plot refresh failures."""
        wavelength = np.linspace(1200, 1300, 100)
        flux = np.random.random(100)
        error = np.ones(100) * 0.1
        plot_widget.set_observed_spectrum(wavelength, flux, error)
        plot_widget.apply_display_command(
            SpectrumPlotDisplayCommand(
                use_normalized_observed=True, render_absorption_line_labels=True
            )
        )

        monkeypatch.setattr(
            plot_widget,
            "_update_observed_plot",
            lambda: (_ for _ in ()).throw(RuntimeError("forced observed plot failure")),
        )

        with pytest.raises(RuntimeError, match="forced observed plot failure"):
            plot_widget.apply_display_command(
                SpectrumPlotDisplayCommand(
                    use_normalized_observed=True, render_absorption_line_labels=False
                )
            )

    def test_hide_continuum_display_propagates_observed_plot_refresh_failure(
        self, plot_widget: MatplotlibSpectrumPlot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Continuum-visibility changes should not hide observed plot refresh failures."""
        wavelength = np.linspace(1200, 1300, 100)
        flux = np.random.random(100)
        error = np.ones(100) * 0.1
        plot_widget.set_observed_spectrum(wavelength, flux, error)
        plot_widget.apply_display_command(
            SpectrumPlotDisplayCommand(
                use_normalized_observed=True, render_absorption_line_labels=True
            )
        )

        monkeypatch.setattr(
            plot_widget,
            "_update_observed_plot",
            lambda: (_ for _ in ()).throw(RuntimeError("forced observed plot failure")),
        )

        with pytest.raises(RuntimeError, match="forced observed plot failure"):
            plot_widget.hide_continuum_display()
