"""Tests for mask selection overlay integration on the plot layer."""

from __future__ import annotations

from typing import Iterator

import pytest
from PySide6.QtWidgets import QApplication, QWidget
from pytestqt.qtbot import QtBot

from chappy.core.masking import MaskDefinition
from chappy.plotting.components.selection_handler import MatplotlibSelectionHandler
from chappy.gui.adapters.plotting import MatplotlibSpectrumPlot
from chappy.plotting.overlays.identify_preview import IdentifyPreviewOverlay
from chappy.plotting.overlays.line_regions import LineRegionArtist, LineRegionOverlay
from chappy.plotting.overlays.mask_regions import MaskRegionOverlay, RegionArtist
from chappy.plotting.overlays.mask_selection import MaskSelectionOverlay
from chappy.plotting.renderers import PlotStyle


class _FailingRemovable:
    """Fake removable artist that raises the configured cleanup error."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def remove(self) -> None:
        """Raise the configured cleanup error."""
        raise self.error


class _FakeSelector:
    """Selection widget fake exposing the private artist slots cleaned by the handler."""

    def __init__(
        self, selection_artist: _FailingRemovable, handles: list[_FailingRemovable]
    ) -> None:
        self._selection_artist = selection_artist
        self._handles = handles
        self.active = True

    def set_active(self, active: bool) -> None:
        """Record selector activation state."""
        self.active = active


class _FakeLineRegionArtist:
    """Line region artist fake for renderer protocol conformance."""

    def set_edgecolor(self, color: str) -> None:
        """Accept edge color updates."""

    def set_alpha(self, _alpha: float) -> None:
        """Accept alpha updates."""


class _FakeLineRegionRenderer:
    """Renderer fake used by line region overlay cleanup tests."""

    def add_region(
        self,
        name: str,
        x_min: float,
        x_max: float,
        style: PlotStyle | None = None,
        label: str | None = None,
    ) -> LineRegionArtist:
        """Return a fake region artist."""
        return _FakeLineRegionArtist()

    def remove_regions_with_prefix(self, prefix: str) -> None:
        """Accept region cleanup requests."""


class _FakeMaskRegionArtist:
    """Mask region artist fake for overlay tests."""

    def set_facecolor(self, color: tuple[float, float, float, float]) -> None:
        """Accept face color updates."""

    def set_edgecolor(self, color: str) -> None:
        """Accept edge color updates."""

    def set_linewidth(self, width: float) -> None:
        """Accept line width updates."""

    def set_zorder(self, level: float) -> None:
        """Accept z-order updates."""


class _FailingMaskRegionRenderer:
    """Renderer fake that fails while drawing mask regions."""

    def __init__(self) -> None:
        self.removed_prefixes: list[str] = []

    def add_region(
        self,
        name: str,
        x_min: float,
        x_max: float,
        style: PlotStyle | None = None,
        label: str | None = None,
    ) -> RegionArtist:
        """Raise a backend drawing failure."""
        raise RuntimeError("mask draw failed")

    def remove_regions_with_prefix(self, prefix: str) -> None:
        """Record region cleanup requests."""
        self.removed_prefixes.append(prefix)

    def get_region(self, name: str) -> RegionArtist | None:
        """Return no existing region."""
        return None


@pytest.fixture(name="qapp")
def fixture_qapp() -> QApplication:
    """Provide a QApplication instance for Qt-based widgets."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(name="plot_widget")
def fixture_plot_widget(qapp: QApplication, qtbot: QtBot) -> Iterator[MatplotlibSpectrumPlot]:
    """Create a MatplotlibSpectrumPlot for overlay tests."""
    assert qapp is not None
    widget = MatplotlibSpectrumPlot()
    qtbot.addWidget(widget)
    widget.renderer.axes.set_ylim(0.0, 1.0)
    yield widget


def test_mask_overlay_methods_manage_patch(plot_widget: MatplotlibSpectrumPlot) -> None:
    """Interaction overlay APIs should create, update, and clear shaded patches."""
    plot_widget.begin_mask_selection(110.0)
    plot_widget.update_mask_selection(110.0, 125.0)

    patch = plot_widget._mask_selection_overlay.patch  # noqa: SLF001 - intentional test inspection
    assert patch is not None
    assert patch.get_x() == pytest.approx(110.0)
    assert patch.get_width() == pytest.approx(15.0)

    plot_widget.clear_mask_selection()
    assert plot_widget._mask_selection_overlay.patch is None  # noqa: SLF001


def test_selection_handler_updates_mask_preview_callback(qapp: QApplication) -> None:
    """MatplotlibSelectionHandler should emit mask preview updates for drag events."""
    from matplotlib.figure import Figure

    assert qapp is not None
    figure = Figure()
    axes = figure.add_subplot(111)
    handler = MatplotlibSelectionHandler(axes, figure)

    captured: list[tuple[float, float]] = []
    handler._on_update_callback = (  # noqa: SLF001 - test instrumentation
        lambda start, end: captured.append((start, end))
    )

    handler._on_span_move(130.0, 110.0)  # noqa: SLF001 - exercising internal hook

    assert captured == [(110.0, 130.0)]


def test_selection_handler_cleanup_suppresses_removed_artist_value_error(
    qapp: QApplication,
) -> None:
    """Selection cleanup should ignore Matplotlib already-removed artist errors."""
    from matplotlib.figure import Figure

    assert qapp is not None
    figure = Figure()
    axes = figure.add_subplot(111)
    handler = MatplotlibSelectionHandler(axes, figure)
    handler.selector = _FakeSelector(  # type: ignore[assignment]
        _FailingRemovable(ValueError("already removed")),
        [_FailingRemovable(ValueError("already removed"))],
    )

    handler._remove_selector()  # noqa: SLF001 - exercising cleanup boundary

    assert handler.selector is None


def test_selection_handler_cleanup_propagates_unexpected_artist_error(qapp: QApplication) -> None:
    """Selection cleanup should not hide unexpected artist removal failures."""
    from matplotlib.figure import Figure

    assert qapp is not None
    figure = Figure()
    axes = figure.add_subplot(111)
    handler = MatplotlibSelectionHandler(axes, figure)
    handler.selector = _FakeSelector(  # type: ignore[assignment]
        _FailingRemovable(RuntimeError("backend failed")), []
    )

    with pytest.raises(RuntimeError, match="backend failed"):
        handler._remove_selector()  # noqa: SLF001 - exercising cleanup boundary


def test_mask_overlay_cleanup_suppresses_removed_artist_value_error(
    plot_widget: MatplotlibSpectrumPlot,
) -> None:
    """Mask overlay cleanup should ignore Matplotlib already-removed artist errors."""
    overlay = MaskSelectionOverlay(plot_widget.renderer.axes, plot_widget.canvas, "#123456")
    overlay.patch = _FailingRemovable(ValueError("already removed"))  # type: ignore[assignment]
    overlay.preview = _FailingRemovable(ValueError("already removed"))  # type: ignore[assignment]

    overlay.clear()

    assert overlay.patch is None
    assert overlay.preview is None


def test_mask_overlay_cleanup_propagates_unexpected_artist_error(
    plot_widget: MatplotlibSpectrumPlot,
) -> None:
    """Mask overlay cleanup should not hide unexpected artist removal failures."""
    overlay = MaskSelectionOverlay(plot_widget.renderer.axes, plot_widget.canvas, "#123456")
    overlay.patch = _FailingRemovable(RuntimeError("backend failed"))  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match="backend failed"):
        overlay.clear()


def test_identify_preview_cleanup_suppresses_removed_artist_value_error(
    plot_widget: MatplotlibSpectrumPlot,
) -> None:
    """Identify preview cleanup should ignore Matplotlib already-removed artist errors."""
    overlay = IdentifyPreviewOverlay(plot_widget.renderer.axes, plot_widget.canvas)
    overlay.spans.append(_FailingRemovable(ValueError("already removed")))

    overlay.clear()

    assert overlay.spans == []


def test_identify_preview_cleanup_propagates_unexpected_artist_error(
    plot_widget: MatplotlibSpectrumPlot,
) -> None:
    """Identify preview cleanup should not hide unexpected artist removal failures."""
    overlay = IdentifyPreviewOverlay(plot_widget.renderer.axes, plot_widget.canvas)
    overlay.spans.append(_FailingRemovable(RuntimeError("backend failed")))

    with pytest.raises(RuntimeError, match="backend failed"):
        overlay.clear()


def test_identify_preview_hint_is_rendered_and_cleared(
    plot_widget: MatplotlibSpectrumPlot,
) -> None:
    """Transient Shift guidance shares the preview overlay lifecycle."""
    overlay = IdentifyPreviewOverlay(plot_widget.renderer.axes, plot_widget.canvas)

    overlay.set_preview(
        {"entries": ({"lambda_min": 1200.0, "lambda_max": 1210.0},), "hint_text": "Shift hint"}
    )

    assert overlay.hint is not None
    assert overlay.hint.get_text() == "Shift hint"

    overlay.clear()

    assert overlay.hint is None


def test_line_region_label_cleanup_suppresses_removed_artist_value_error(
    plot_widget: MatplotlibSpectrumPlot,
) -> None:
    """Line region label cleanup should ignore Matplotlib already-removed artist errors."""
    overlay = LineRegionOverlay(
        _FakeLineRegionRenderer(), plot_widget.renderer.axes, plot_widget.canvas, "absorption"
    )
    overlay.labels.append(_FailingRemovable(ValueError("already removed")))  # type: ignore[arg-type]

    overlay.clear_labels()

    assert overlay.labels == []


def test_line_region_label_cleanup_suppresses_not_implemented_error(
    plot_widget: MatplotlibSpectrumPlot,
) -> None:
    """Line region label cleanup should ignore backends without artist removal support."""
    overlay = LineRegionOverlay(
        _FakeLineRegionRenderer(), plot_widget.renderer.axes, plot_widget.canvas, "absorption"
    )
    overlay.labels.append(_FailingRemovable(NotImplementedError("cannot remove artist")))  # type: ignore[arg-type]

    overlay.clear_labels()

    assert overlay.labels == []


def test_line_region_label_cleanup_propagates_unexpected_artist_error(
    plot_widget: MatplotlibSpectrumPlot,
) -> None:
    """Line region label cleanup should not hide unexpected artist removal failures."""
    overlay = LineRegionOverlay(
        _FakeLineRegionRenderer(), plot_widget.renderer.axes, plot_widget.canvas, "absorption"
    )
    overlay.labels.append(_FailingRemovable(RuntimeError("backend failed")))  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="backend failed"):
        overlay.clear_labels()


def test_mask_region_overlay_propagates_draw_failures(plot_widget: MatplotlibSpectrumPlot) -> None:
    """Persistent mask drawing should fail fast on renderer failures."""
    renderer = _FailingMaskRegionRenderer()
    overlay = MaskRegionOverlay(renderer, plot_widget.canvas, "mask:", "#123456")
    mask = MaskDefinition.from_range(110.0, 120.0, identifier="mask-1")

    with pytest.raises(RuntimeError, match="mask draw failed"):
        overlay.set_regions([mask])

    assert renderer.removed_prefixes == ["mask:"]
