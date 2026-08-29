"""Tests for the composed velocity overlay widget."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from chappy.gui.spectrum.velocity import (
    SpectrumVelocityOverlayWidget,
    VelocityDisplayHalfWidthSpinBox,
    VelocityDisplayInputRejection,
)
from chappy.presentation.velocity import (
    VelocityDisplayHalfWidth,
    VelocityDisplayScopeKey,
    VelocitySelectionCreateRequest,
    VelocitySliceInfo,
    build_velocity_view_data,
)
from tests.gui.support.faithful_env import faithful_application_environment

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def _scope(value: str) -> VelocityDisplayScopeKey:
    """Build a nominal plot-local display scope for test sessions."""
    return VelocityDisplayScopeKey(value)


@pytest.fixture
def overlay_widget(qtbot: QtBot) -> SpectrumVelocityOverlayWidget:
    """Create a SpectrumVelocityOverlayWidget instance for testing."""
    widget = SpectrumVelocityOverlayWidget()
    qtbot.addWidget(widget)
    return widget


def test_overlay_widget_uses_translated_labels(
    overlay_widget: SpectrumVelocityOverlayWidget,
) -> None:
    """Title and button labels should expose the expected source text."""
    title = overlay_widget.findChild(QLabel, "velocityPlotTitle")
    create_button = overlay_widget.findChild(QPushButton, "velocityPlotCreateButton")
    exit_button = overlay_widget.findChild(QPushButton, "velocityPlotExitButton")

    assert (title.text() if title is not None else "") == "Velocity Plot"
    assert (
        create_button.text() if create_button is not None else ""
    ) == "Add selected lines to temporary list"
    exit_text = exit_button.text() if exit_button is not None else ""
    assert exit_text.startswith("←")
    assert exit_text.endswith("Back to Spectrum")


def test_overlay_widget_add_requested_emits_selected_slices(
    overlay_widget: SpectrumVelocityOverlayWidget,
) -> None:
    """Create button should emit a typed selection payload from the embedded grid."""
    requests: list[VelocitySelectionCreateRequest] = []
    overlay_widget.add_requested.connect(requests.append)
    overlay_widget.grid_widget.apply_view_data(
        build_velocity_view_data(
            None,
            [
                VelocitySliceInfo(
                    rest_wavelength=1215.67, label="Lyα", tie_group_key="", selected=True
                )
            ],
            display_half_width_kms=overlay_widget.grid_widget.display_half_width.value,
            include_optimize_overlays=False,
        )
    )
    overlay_widget.set_create_enabled(True)

    button = overlay_widget.findChild(QPushButton, "velocityPlotCreateButton")
    assert button is not None
    button.click()

    assert len(requests) == 1
    assert len(requests[0].selections) == 1
    assert requests[0].selections[0].label == "Lyα"


def test_optimize_header_uses_plot_local_display_controls(
    overlay_widget: SpectrumVelocityOverlayWidget, qtbot: QtBot
) -> None:
    """Both scientific modes should expose independent display controls."""
    spinbox = overlay_widget.findChild(
        VelocityDisplayHalfWidthSpinBox, "velocityDisplayHalfWidthSpinBox"
    )
    fit_button = overlay_widget.findChild(QPushButton, "velocityFitViewToAnalysisRangesButton")
    create_button = overlay_widget.findChild(QPushButton, "velocityPlotCreateButton")
    assert spinbox is not None
    assert fit_button is not None
    assert create_button is not None

    overlay_widget.show()
    overlay_widget.set_mode("identify")
    overlay_widget.activate_display_range(
        scope_key=_scope("identify:hypothesis-a"), analysis_half_widths_kms=(200.0,)
    )
    qtbot.wait(0)
    assert spinbox.isVisible() is True
    assert fit_button.isVisible() is True
    assert create_button.isVisible() is True
    assert spinbox.accepted_value.value == 225.0

    overlay_widget.set_mode("optimize")
    overlay_widget.activate_display_range(
        scope_key=_scope("optimize:region-a"), analysis_half_widths_kms=(230.0, 180.0)
    )
    qtbot.wait(0)
    assert spinbox.isVisible() is True
    assert fit_button.isVisible() is True
    assert create_button.isVisible() is False
    assert spinbox.accepted_value.value == 250.0


def test_fit_view_action_is_the_only_refresh_that_rederives_manual_state(
    overlay_widget: SpectrumVelocityOverlayWidget,
) -> None:
    """Normal refresh should preserve manual state; the explicit action should rederive it."""
    overlay_widget.set_mode("optimize")
    overlay_widget.activate_display_range(
        scope_key=_scope("optimize:region-a"), analysis_half_widths_kms=(230.0,)
    )
    spinbox = overlay_widget.findChild(
        VelocityDisplayHalfWidthSpinBox, "velocityDisplayHalfWidthSpinBox"
    )
    fit_button = overlay_widget.findChild(QPushButton, "velocityFitViewToAnalysisRangesButton")
    assert spinbox is not None
    assert fit_button is not None

    spinbox.value_accepted.emit(VelocityDisplayHalfWidth(600.0))
    overlay_widget.activate_display_range(
        scope_key=_scope("optimize:region-a"), analysis_half_widths_kms=(1000.0,)
    )
    assert spinbox.accepted_value.value == 600.0

    fit_button.click()
    assert spinbox.accepted_value.value == 1250.0
    assert overlay_widget.display_range_state is not None
    assert overlay_widget.display_range_state.source == "auto"


def test_identify_refresh_updates_boundaries_without_overwriting_manual_display(
    overlay_widget: SpectrumVelocityOverlayWidget,
) -> None:
    """Identify draft updates should not synchronize into a manually chosen view."""
    overlay_widget.set_mode("identify")
    overlay_widget.activate_display_range(
        scope_key=_scope("identify:hypothesis-a"), analysis_half_widths_kms=(200.0,)
    )
    spinbox = overlay_widget.findChild(
        VelocityDisplayHalfWidthSpinBox, "velocityDisplayHalfWidthSpinBox"
    )
    fit_button = overlay_widget.findChild(QPushButton, "velocityFitViewToAnalysisRangesButton")
    summary = overlay_widget.findChild(QLabel, "velocityAnalysisRangeSummary")
    assert spinbox is not None
    assert fit_button is not None
    assert summary is not None
    assert spinbox.accepted_value == VelocityDisplayHalfWidth(225.0)

    spinbox.value_accepted.emit(VelocityDisplayHalfWidth(600.0))
    overlay_widget.activate_display_range(
        scope_key=_scope("identify:hypothesis-a"), analysis_half_widths_kms=(1000.0,)
    )

    assert spinbox.accepted_value == VelocityDisplayHalfWidth(600.0)
    assert "±1000 km/s" in summary.text()
    assert "analysis range" in summary.accessibleName()

    fit_button.click()
    assert spinbox.accepted_value == VelocityDisplayHalfWidth(1250.0)


def test_identify_header_preserves_full_action_labels_at_representative_width(
    overlay_widget: SpectrumVelocityOverlayWidget, qtbot: QtBot
) -> None:
    """The two-row grid should give Identify actions enough width for their full labels."""
    overlay_widget.set_mode("identify")
    overlay_widget.resize(740, 560)
    overlay_widget.show()
    qtbot.wait(0)
    create_button = overlay_widget.findChild(QPushButton, "velocityPlotCreateButton")
    exit_button = overlay_widget.findChild(QPushButton, "velocityPlotExitButton")
    fit_button = overlay_widget.findChild(QPushButton, "velocityFitViewToAnalysisRangesButton")
    assert create_button is not None
    assert exit_button is not None
    assert fit_button is not None

    for button in (create_button, exit_button, fit_button):
        # The layout must grant each button its natural size (full label plus
        # the style's own padding); absolute padding pixels are style-dependent.
        text_width = button.fontMetrics().horizontalAdvance(button.text())
        assert button.width() >= button.sizeHint().width()
        assert button.width() > text_width


@pytest.mark.parametrize("mode", ["identify", "optimize"])
def test_velocity_header_keeps_navigation_aligned_and_range_controls_compact(
    overlay_widget: SpectrumVelocityOverlayWidget,
    qtbot: QtBot,
    mode: Literal["identify", "optimize"],
) -> None:
    """Wide layouts should not separate related range controls or move Back between modes."""
    overlay_widget.set_mode(mode)
    overlay_widget.activate_display_range(
        scope_key=_scope(f"{mode}:wide"), analysis_half_widths_kms=(200.0,)
    )
    overlay_widget.resize(1800, 850)
    overlay_widget.show()
    qtbot.wait(0)

    title = overlay_widget.findChild(QLabel, "velocityPlotTitle")
    summary = overlay_widget.findChild(QLabel, "velocityAnalysisRangeSummary")
    display_label = overlay_widget.findChild(QLabel, "velocityDisplayHalfWidthLabel")
    fit_button = overlay_widget.findChild(QPushButton, "velocityFitViewToAnalysisRangesButton")
    exit_button = overlay_widget.findChild(QPushButton, "velocityPlotExitButton")
    assert title is not None
    assert summary is not None
    assert display_label is not None
    assert fit_button is not None
    assert exit_button is not None

    assert abs(exit_button.geometry().center().y() - title.geometry().center().y()) <= 1
    assert abs(summary.geometry().center().y() - display_label.geometry().center().y()) <= 1
    assert display_label.geometry().left() - summary.geometry().right() <= 9
    assert summary.geometry().left() > 100
    assert overlay_widget.width() - fit_button.geometry().right() <= 17


@pytest.mark.parametrize("language", ["en", "ja"])
def test_identify_header_remains_usable_in_faithful_environment(
    qtbot: QtBot, qapp: QApplication, language: str
) -> None:
    """Both locales should keep the value and full actions at a typical central width."""
    with faithful_application_environment(qapp, language):
        widget = SpectrumVelocityOverlayWidget()
        qtbot.addWidget(widget)
        widget.set_mode("identify")
        widget.activate_display_range(
            scope_key=_scope(f"identify:{language}"), analysis_half_widths_kms=(200.0,)
        )
        widget.show()
        QApplication.processEvents()
        minimum_width = widget.minimumSizeHint().width()
        widget.resize(minimum_width, 560)
        QApplication.processEvents()

        summary = widget.findChild(QLabel, "velocityAnalysisRangeSummary")
        create_button = widget.findChild(QPushButton, "velocityPlotCreateButton")
        exit_button = widget.findChild(QPushButton, "velocityPlotExitButton")
        fit_button = widget.findChild(QPushButton, "velocityFitViewToAnalysisRangesButton")
        assert summary is not None
        assert create_button is not None
        assert exit_button is not None
        assert fit_button is not None
        assert "±200 km/s" in summary.text()
        assert "range" in summary.text() or "範囲" in summary.text()
        assert "dashed" in summary.text() or "破線" in summary.text()
        assert widget.width() <= 950
        for button in (create_button, exit_button, fit_button):
            text_width = button.fontMetrics().horizontalAdvance(button.text())
            assert button.width() >= text_width + 16


def test_leaving_optimize_clears_the_overlay_display_session(
    overlay_widget: SpectrumVelocityOverlayWidget,
) -> None:
    """Mode exit should not leak a manual display value into the next Optimize session."""
    overlay_widget.set_mode("optimize")
    overlay_widget.activate_display_range(
        scope_key=_scope("optimize:region-a"), analysis_half_widths_kms=(230.0,)
    )
    spinbox = overlay_widget.findChild(
        VelocityDisplayHalfWidthSpinBox, "velocityDisplayHalfWidthSpinBox"
    )
    assert spinbox is not None
    spinbox.value_accepted.emit(VelocityDisplayHalfWidth(600.0))

    overlay_widget.set_mode("identify")
    assert overlay_widget.display_range_state is None

    overlay_widget.set_mode("optimize")
    overlay_widget.activate_display_range(
        scope_key=_scope("optimize:region-a"), analysis_half_widths_kms=(230.0,)
    )
    assert spinbox.accepted_value.value == 250.0


def test_rejected_display_input_exposes_reason_without_changing_value(
    overlay_widget: SpectrumVelocityOverlayWidget, qtbot: QtBot
) -> None:
    """Invalid display input should retain the value and make the valid range visible."""
    overlay_widget.set_mode("optimize")
    overlay_widget.activate_display_range(
        scope_key=_scope("optimize:region-a"), analysis_half_widths_kms=(230.0,)
    )
    overlay_widget.show()
    spinbox = overlay_widget.findChild(
        VelocityDisplayHalfWidthSpinBox, "velocityDisplayHalfWidthSpinBox"
    )
    status = overlay_widget.findChild(QLabel, "velocityDisplayRangeStatus")
    assert spinbox is not None
    assert status is not None

    spinbox.set_accepted_value(VelocityDisplayHalfWidth(10.0))
    spinbox.setFocus()
    qtbot.keyClick(spinbox, Qt.Key.Key_Down)

    assert spinbox.accepted_value.value == 10.0
    assert "10" in status.text()
    assert "5000" in status.text()
    assert status.isVisible() is True


def test_accepted_display_input_restores_baseline_accessibility_after_rejection(
    overlay_widget: SpectrumVelocityOverlayWidget,
) -> None:
    """A corrected input should not leave the previous error on the spinbox."""
    overlay_widget.set_mode("optimize")
    overlay_widget.activate_display_range(
        scope_key=_scope("optimize:region-a"), analysis_half_widths_kms=(230.0,)
    )
    spinbox = overlay_widget.findChild(
        VelocityDisplayHalfWidthSpinBox, "velocityDisplayHalfWidthSpinBox"
    )
    assert spinbox is not None

    spinbox.input_rejected.emit(
        VelocityDisplayInputRejection(reason="invalid_number", entered_text="invalid")
    )
    assert "valid numeric" in spinbox.accessibleDescription()

    spinbox.value_accepted.emit(VelocityDisplayHalfWidth(300.0))

    assert spinbox.accessibleName() == "Display range"
    assert (
        spinbox.accessibleDescription() == "Symmetric plot-local velocity display range in ±km/s."
    )
