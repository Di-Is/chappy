"""Unit tests for absorber marker overlay ownership."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from matplotlib.figure import Figure

from chappy.plotting.overlays.absorber_markers import AbsorberMarkerOverlay
from chappy.presentation.spectrum import AbsorptionMarkerInput

if TYPE_CHECKING:
    from matplotlib.axes import Axes


def _axes() -> Axes:
    axes = Figure().subplots()
    axes.set_xlim(3000.0, 5000.0)
    return axes


@dataclass
class _Line:
    xdata: list[float]
    visible: bool = True
    removed: bool = False

    def get_visible(self) -> bool:
        return self.visible

    def set_visible(self, visible: bool) -> None:
        self.visible = visible

    def set_xdata(self, xdata: list[float]) -> None:
        self.xdata = xdata

    def remove(self) -> None:
        self.removed = True


@dataclass
class _Renderer:
    lines: dict[str, _Line] = field(default_factory=dict)

    def add_vertical_line(self, name: str, x: float, style=None, label=None) -> _Line:
        del style, label
        line = _Line([x])
        self.lines[name] = line
        return line

    def update_vertical_line_position(self, name: str, x: float) -> bool:
        line = self.lines.get(name)
        if line is None:
            return False
        line.set_xdata([x])
        return True

    def remove_vertical_line(self, name: str) -> bool:
        line = self.lines.pop(name, None)
        if line is None:
            return False
        line.remove()
        return True

    def get_vertical_line(self, name: str) -> _Line | None:
        return self.lines.get(name)


@dataclass
class _Canvas:
    draw_idle_calls: int = 0

    def draw_idle(self) -> None:
        self.draw_idle_calls += 1


def _overlay(
    *, renderer: _Renderer, canvas: _Canvas, axes: Axes, band_top: float = 0.985
) -> AbsorberMarkerOverlay:
    return AbsorberMarkerOverlay(
        renderer=renderer, canvas=canvas, axes=axes, band_top_provider=lambda: band_top
    )


def test_absorber_marker_overlay_drag_lifecycle() -> None:
    """Overlay should hide original marker, move temp line, and restore on finish."""
    renderer = _Renderer()
    canvas = _Canvas()
    overlay = _overlay(renderer=renderer, canvas=canvas, axes=_axes())
    marker = AbsorptionMarkerInput(
        name="Lya",
        rest_wavelength=1215.67,
        redshift=2.0,
        column_density=14.0,
        b_parameter=20.0,
        oscillator_strength=0.4164,
        gamma=6.265e8,
    )

    overlay.add_marker(marker, component_id="c1")
    overlay.begin_drag("c1", 3600.0)
    overlay.update_drag("c1", 3610.0)
    overlay.finish_drag("c1")

    assert renderer.get_vertical_line("marker_c1") is not None
    assert renderer.get_vertical_line("marker_c1").visible is True
    assert renderer.get_vertical_line("_temp_drag_c1") is None
    assert canvas.draw_idle_calls >= 2


def _marker(name: str, redshift: float, tie_label: str | None = None) -> AbsorptionMarkerInput:
    return AbsorptionMarkerInput(
        name=name,
        rest_wavelength=1215.67,
        redshift=redshift,
        column_density=14.0,
        b_parameter=20.0,
        oscillator_strength=0.4164,
        gamma=6.265e8,
        tie_label=tie_label,
    )


def test_refresh_component_labels_places_tie_annotated_text() -> None:
    """Refreshing labels annotates each marker with its bracketed tie label."""
    axes = _axes()
    overlay = _overlay(renderer=_Renderer(), canvas=_Canvas(), axes=axes)

    overlay.add_marker(_marker("c1", 2.0, tie_label="A"), component_id="c1")
    overlay.add_marker(_marker("c2", 2.001), component_id="c2")
    overlay.refresh_component_labels()

    assert {text.get_text() for text in axes.texts} == {"c1 [A]", "c2"}


def test_clear_removes_component_labels() -> None:
    """Clearing the overlay removes annotations as well as vertical lines."""
    axes = _axes()
    overlay = _overlay(renderer=_Renderer(), canvas=_Canvas(), axes=axes)

    overlay.add_marker(_marker("c1", 2.0), component_id="c1")
    overlay.refresh_component_labels()
    overlay.clear()

    assert len(axes.texts) == 0


def test_toggle_hides_component_labels() -> None:
    """Toggling markers off hides their labels."""
    axes = _axes()
    overlay = _overlay(renderer=_Renderer(), canvas=_Canvas(), axes=axes)

    overlay.add_marker(_marker("c1", 2.0), component_id="c1")
    overlay.refresh_component_labels()
    overlay.toggle(show=False)

    assert all(not text.get_visible() for text in axes.texts)


def test_band_top_provider_places_labels_below_the_line_labels() -> None:
    """The overlay hangs its labels from whatever band top the provider reports."""
    axes = _axes()
    overlay = _overlay(renderer=_Renderer(), canvas=_Canvas(), axes=axes, band_top=0.91)

    overlay.add_marker(_marker("c1", 2.0), component_id="c1")
    overlay.refresh_component_labels()

    assert float(axes.texts[0].xy[1]) == 0.91


def test_selected_component_label_is_emphasised() -> None:
    """Selecting a component re-places labels with that one bold."""
    axes = _axes()
    overlay = _overlay(renderer=_Renderer(), canvas=_Canvas(), axes=axes)

    overlay.add_marker(_marker("c1", 2.0), component_id="c1")
    overlay.add_marker(_marker("c2", 2.5), component_id="c2")
    overlay.refresh_component_labels()
    overlay.set_selected_component_id("c2")

    weights = {text.get_text(): text.get_fontweight() for text in axes.texts}
    assert weights == {"c1": "normal", "c2": "bold"}


def test_clear_keeps_the_selected_component() -> None:
    """Clearing markers does not forget which component is selected."""
    axes = _axes()
    overlay = _overlay(renderer=_Renderer(), canvas=_Canvas(), axes=axes)

    overlay.add_marker(_marker("c1", 2.0), component_id="c1")
    overlay.set_selected_component_id("c1")
    overlay.clear()
    overlay.add_marker(_marker("c1", 2.0), component_id="c1")
    overlay.refresh_component_labels()

    assert axes.texts[0].get_fontweight() == "bold"


def test_hidden_labels_stay_hidden_after_a_refresh() -> None:
    """A refresh triggered by zooming must not resurrect hidden labels."""
    axes = _axes()
    overlay = _overlay(renderer=_Renderer(), canvas=_Canvas(), axes=axes)

    overlay.add_marker(_marker("c1", 2.0), component_id="c1")
    overlay.refresh_component_labels()
    overlay.toggle(show=False)
    overlay.refresh_component_labels()

    assert all(not text.get_visible() for text in axes.texts)
