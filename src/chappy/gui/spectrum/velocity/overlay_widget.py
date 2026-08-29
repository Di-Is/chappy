"""Velocity overlay widget composed above the shared spectrum surface."""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING, Literal

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from chappy.gui.theme import BACK_ARROW_PREFIX, Colors, Fonts, apply_button_variant
from chappy.i18n import LanguageSwitcher, get_language_switcher
from chappy.presentation.velocity import (
    MAX_VELOCITY_DISPLAY_HALF_WIDTH_KMS,
    MIN_VELOCITY_DISPLAY_HALF_WIDTH_KMS,
    VelocityDisplayHalfWidth,
    VelocityDisplayRangeState,
    VelocityDisplayScopeKey,
    VelocitySelectionCreateRequest,
)

from .display_range_controller import VelocityDisplayRangeController
from .display_range_spinbox import VelocityDisplayHalfWidthSpinBox, VelocityDisplayInputRejection
from .grid_widget import VelocityGridWidget

if TYPE_CHECKING:
    from collections.abc import Sequence

    from PySide6.QtGui import QCloseEvent, QResizeEvent


class _ElidedHeaderLabel(QLabel):
    """Single-line header text that elides without increasing the overlay minimum width."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full_text = ""

    def setText(self, text: str) -> None:  # noqa: N802 - Qt virtual API
        """Store the full text and render an elided copy."""
        self._full_text = text
        self.setToolTip(text)
        self._apply_elide()

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt virtual API
        """Allow controls to keep their labels at narrow central widths."""
        return QSize(0, super().minimumSizeHint().height())

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt virtual API
        """Re-elide after header geometry changes."""
        super().resizeEvent(event)
        self._apply_elide()

    def _apply_elide(self) -> None:
        rendered = self.fontMetrics().elidedText(
            self._full_text, Qt.TextElideMode.ElideRight, max(0, self.width())
        )
        QLabel.setText(self, rendered)


class SpectrumVelocityOverlayWidget(QWidget):
    """Composite widget containing velocity header controls and the grid widget."""

    add_requested = Signal(object)
    exit_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the velocity overlay surface."""
        super().__init__(parent)

        self._language_switcher: LanguageSwitcher = get_language_switcher(self)
        self._title_label: QLabel | None = None
        self._info_label: QLabel | None = None
        self._create_button: QPushButton | None = None
        self._exit_button: QPushButton | None = None
        self._header_layout: QVBoxLayout | None = None
        self._primary_header_layout: QHBoxLayout | None = None
        self._range_header_layout: QHBoxLayout | None = None
        self._display_label: QLabel | None = None
        self._display_spinbox: VelocityDisplayHalfWidthSpinBox | None = None
        self._fit_view_button: QPushButton | None = None
        self._display_status_label: QLabel | None = None
        self._analysis_range_label: QLabel | None = None
        self._grid_widget: VelocityGridWidget | None = None
        self._mode: Literal["identify", "optimize"] = "identify"
        self._last_rejection: VelocityDisplayInputRejection | None = None
        self._analysis_half_widths_kms: tuple[float, ...] = ()

        self.setObjectName("velocityPlotContainer")
        self._build_ui()
        self._display_range_controller = VelocityDisplayRangeController(
            apply_display_half_width=self.grid_widget.set_display_half_width,
            state_changed=self._render_display_range_state,
        )

        self._language_switcher.language_changed.connect(self._apply_translations)
        self._apply_translations()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Disconnect language updates when closing."""
        self.clear_display_range_session()
        with suppress(RuntimeError, TypeError):
            self._language_switcher.language_changed.disconnect(self._apply_translations)
        QWidget.closeEvent(self, event)

    @property
    def grid_widget(self) -> VelocityGridWidget:
        """Return the embedded velocity grid widget."""
        if self._grid_widget is None:
            msg = "Velocity grid widget has not been initialised."
            raise RuntimeError(msg)
        return self._grid_widget

    def set_context_parts(self, parts: Sequence[str]) -> None:
        """Update the context summary label and grid mirror text."""
        self.grid_widget.update_context_label(parts)

    def clear_context(self) -> None:
        """Clear the context summary label."""
        self.grid_widget.update_context_label(())

    def set_create_enabled(self, enabled: bool) -> None:
        """Enable or disable the create button."""
        if self._create_button is not None:
            self._create_button.setEnabled(enabled)

    def set_create_visible(self, visible: bool) -> None:
        """Show or hide the create button."""
        if self._create_button is not None:
            self._create_button.setVisible(visible)

    @property
    def display_range_state(self) -> VelocityDisplayRangeState | None:
        """Return the current plot-local display state for tests and composition."""
        return self._display_range_controller.state

    def set_mode(self, mode: Literal["identify", "optimize"]) -> None:
        """Render the shared header with only the active mode's controls."""
        if self._mode != mode:
            self.clear_display_range_session()
        self._mode = mode
        self._layout_header()
        self._apply_translations()

    def activate_display_range(
        self, *, scope_key: VelocityDisplayScopeKey, analysis_half_widths_kms: tuple[float, ...]
    ) -> None:
        """Open or refresh a mode-independent plot-local display-range session."""
        self._analysis_half_widths_kms = tuple(analysis_half_widths_kms)
        self._display_range_controller.activate(scope_key, analysis_half_widths_kms)
        self._render_analysis_range_label()

    def clear_display_range_session(self) -> None:
        """Discard plot-local display state at an overlay or project boundary."""
        if self._display_spinbox is not None:
            self._display_spinbox.clearFocus()
        self._display_range_controller.clear()
        self._analysis_half_widths_kms = ()
        self._render_analysis_range_label()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 16)
        layout.setSpacing(8)

        header_layout = QVBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        self._header_layout = header_layout

        primary_header_layout = QHBoxLayout()
        primary_header_layout.setContentsMargins(0, 0, 0, 0)
        primary_header_layout.setSpacing(8)
        self._primary_header_layout = primary_header_layout

        range_header_layout = QHBoxLayout()
        range_header_layout.setContentsMargins(0, 0, 0, 0)
        range_header_layout.setSpacing(8)
        self._range_header_layout = range_header_layout

        title_label = QLabel("", self)
        title_label.setObjectName("velocityPlotTitle")
        title_label.setStyleSheet(f"font-size: {Fonts.SIZE_LARGE}; font-weight: 600;")
        self._title_label = title_label

        info_label = _ElidedHeaderLabel(self)
        info_label.setObjectName("velocityPlotInfo")
        info_label.setStyleSheet(
            f"font-size: {Fonts.SIZE_NORMAL}; color: {Colors.TEXT_SECONDARY};"
        )
        info_label.setWordWrap(False)
        info_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._info_label = info_label

        analysis_range_label = QLabel("", self)
        analysis_range_label.setObjectName("velocityAnalysisRangeSummary")
        analysis_range_label.setStyleSheet(
            f"font-size: {Fonts.SIZE_SMALL}; color: {Colors.TEXT_SECONDARY};"
        )
        analysis_range_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
        )
        self._analysis_range_label = analysis_range_label

        create_button = QPushButton("", self)
        create_button.setObjectName("velocityPlotCreateButton")
        create_button.setEnabled(False)
        apply_button_variant(create_button, "primary")
        create_button.clicked.connect(self._emit_add_requested)
        self._create_button = create_button

        display_status_label = QLabel("", self)
        display_status_label.setObjectName("velocityDisplayRangeStatus")
        display_status_label.setStyleSheet(
            f"font-size: {Fonts.SIZE_SMALL}; color: {Colors.TEXT_SECONDARY};"
        )
        display_status_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        display_status_label.setVisible(False)
        self._display_status_label = display_status_label

        display_label = QLabel("", self)
        display_label.setObjectName("velocityDisplayHalfWidthLabel")
        self._display_label = display_label

        display_spinbox = VelocityDisplayHalfWidthSpinBox(self)
        display_spinbox.value_accepted.connect(self._on_display_half_width_accepted)
        display_spinbox.input_rejected.connect(self._on_display_half_width_rejected)
        display_label.setBuddy(display_spinbox)
        self._display_spinbox = display_spinbox

        fit_view_button = QPushButton("", self)
        fit_view_button.setObjectName("velocityFitViewToAnalysisRangesButton")
        apply_button_variant(fit_view_button, "text")
        fit_view_button.clicked.connect(self._fit_view_to_analysis_ranges)
        self._fit_view_button = fit_view_button

        exit_button = QPushButton("", self)
        exit_button.setObjectName("velocityPlotExitButton")
        apply_button_variant(exit_button, "text")
        exit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        exit_button.clicked.connect(self.exit_requested.emit)
        self._exit_button = exit_button

        header_layout.addLayout(primary_header_layout)
        header_layout.addLayout(range_header_layout)
        header_layout.addWidget(display_status_label)
        layout.addLayout(header_layout)

        grid_widget = VelocityGridWidget(self)
        grid_widget.attach_context_label(info_label)
        layout.addWidget(grid_widget, stretch=1)
        self._grid_widget = grid_widget
        self._layout_header()

        QWidget.setTabOrder(create_button, display_spinbox)
        QWidget.setTabOrder(display_spinbox, fit_view_button)
        QWidget.setTabOrder(fit_view_button, exit_button)

    def _layout_header(self) -> None:
        """Lead row one with the back link, then context and the add action.

        Row two keeps the compact velocity range cluster.
        """
        title = self._title_label
        info = self._info_label
        create = self._create_button
        status = self._display_status_label
        analysis = self._analysis_range_label
        label = self._display_label
        spinbox = self._display_spinbox
        fit_button = self._fit_view_button
        exit_button = self._exit_button
        if (
            self._primary_header_layout is None
            or self._range_header_layout is None
            or title is None
            or info is None
            or create is None
            or status is None
            or analysis is None
            or label is None
            or spinbox is None
            or fit_button is None
            or exit_button is None
        ):
            return
        self._clear_layout(self._primary_header_layout)
        self._clear_layout(self._range_header_layout)

        self._primary_header_layout.addWidget(exit_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self._primary_header_layout.addWidget(title, 0, Qt.AlignmentFlag.AlignVCenter)
        self._primary_header_layout.addWidget(info, 1)
        if self._mode == "identify":
            self._primary_header_layout.addWidget(create)

        self._range_header_layout.addStretch(1)
        self._range_header_layout.addWidget(analysis)
        self._range_header_layout.addWidget(label, 0, Qt.AlignmentFlag.AlignVCenter)
        self._range_header_layout.addWidget(spinbox)
        self._range_header_layout.addWidget(fit_button)
        create.setVisible(self._mode == "identify")
        analysis.setVisible(True)
        label.setVisible(True)
        spinbox.setVisible(True)
        fit_button.setVisible(True)
        status.setVisible(bool(status.text()))

    @staticmethod
    def _clear_layout(layout: QHBoxLayout) -> None:
        """Remove row items so mode-specific controls can be placed again."""
        while layout.takeAt(0) is not None:
            pass

    def _on_display_half_width_accepted(self, value: object) -> None:
        """Commit typed user input to the overlay-local controller."""
        if not isinstance(value, VelocityDisplayHalfWidth):
            msg = "Display half-width signal must carry VelocityDisplayHalfWidth."
            raise TypeError(msg)
        if self._display_range_controller.state is None:
            return
        self._display_range_controller.commit_manual(value)

    def _on_display_half_width_rejected(self, rejection: object) -> None:
        """Show a user-correctable reason while retaining the prior accepted value."""
        if not isinstance(rejection, VelocityDisplayInputRejection):
            msg = "Display range rejection signal has an invalid payload."
            raise TypeError(msg)
        if self._display_range_controller.state is None:
            return
        self._last_rejection = rejection
        self._render_rejection()

    def _fit_view_to_analysis_ranges(self) -> None:
        """Run the explicit plot-fit action without recording scientific history."""
        self._display_range_controller.fit_view_to_analysis_ranges()

    def _render_display_range_state(self, state: VelocityDisplayRangeState | None) -> None:
        """Reflect accepted session state in the header control."""
        if self._display_spinbox is not None and state is not None:
            self._display_spinbox.set_accepted_value(state.value)
        self._last_rejection = None
        self._apply_display_spinbox_accessibility()
        if self._display_status_label is not None:
            self._display_status_label.clear()
            self._display_status_label.setAccessibleDescription("")
            self._display_status_label.setVisible(False)

    def _render_rejection(self) -> None:
        """Render the current localized input rejection."""
        if self._last_rejection is None or self._display_status_label is None:
            return
        if self._last_rejection.reason == "invalid_number":
            message = self.tr("Enter a valid numeric display range.")
        else:
            template = self.tr("Display range must be between ±{minimum:g} and ±{maximum:g} km/s.")
            message = template.format(
                minimum=MIN_VELOCITY_DISPLAY_HALF_WIDTH_KMS,
                maximum=MAX_VELOCITY_DISPLAY_HALF_WIDTH_KMS,
            )
        self._display_status_label.setText(message)
        self._display_status_label.setAccessibleDescription(message)
        self._display_status_label.setVisible(True)
        if self._display_spinbox is not None:
            self._display_spinbox.setAccessibleDescription(message)

    def _emit_add_requested(self) -> None:
        """Emit the current overlay selection request payload."""
        self.add_requested.emit(
            VelocitySelectionCreateRequest(
                selections=tuple(self.grid_widget.get_selected_slices())
            )
        )

    def _apply_translations(self, _code: str | None = None) -> None:
        """Apply translated button and title text."""
        if self._title_label is not None:
            self._title_label.setText(self.tr("Velocity Plot"))
        if self._create_button is not None:
            self._create_button.setText(self.tr("Add selected lines to temporary list"))
        if self._display_label is not None:
            self._display_label.setText(self.tr("Display range"))
        self._apply_display_spinbox_accessibility()
        if self._fit_view_button is not None:
            self._fit_view_button.setText(self.tr("Fit view to analysis ranges"))
            self._fit_view_button.setAccessibleName(self.tr("Fit view to analysis ranges"))
            description = (
                self.tr("Recalculate the display range from the new-candidate analysis range.")
                if self._mode == "identify"
                else self.tr("Recalculate the display range from current analysis ranges.")
            )
            self._fit_view_button.setAccessibleDescription(description)
        if self._exit_button is not None:
            self._exit_button.setText(BACK_ARROW_PREFIX + self.tr("Back to Spectrum"))
        self._render_rejection()
        self._render_analysis_range_label()

    def _render_analysis_range_label(self) -> None:
        """Describe the scientific boundaries independently of the display control."""
        if self._analysis_range_label is None:
            return
        widths = self._analysis_half_widths_kms
        if not widths:
            self._analysis_range_label.clear()
            self._analysis_range_label.setAccessibleDescription("")
            return
        low = min(widths)
        high = max(widths)
        if self._mode == "identify":
            #: {value} is the future-candidate analysis half-width in km/s.
            visible_template = self.tr("New-candidate range ±{value:g} km/s (dashed)")
            text = visible_template.format(value=high)
            accessible_template = self.tr(
                "New-candidate analysis range ±{value:g} km/s (dashed lines)"
            )
            accessible_name = accessible_template.format(value=high)
            description = self.tr(
                "Dashed lines mark the symmetric analysis range copied to newly created candidates."
            )
        elif low == high:
            #: {value} is one line's analysis half-width in km/s.
            template = self.tr("Analysis range ±{value:g} km/s (dashed)")
            text = template.format(value=high)
            accessible_name = text
            description = self.tr("Dashed lines mark the current line analysis range.")
        else:
            #: {minimum} and {maximum} bound the line analysis half-widths in km/s.
            template = self.tr("Analysis ranges ±{minimum:g}–{maximum:g} km/s (dashed)")
            text = template.format(minimum=low, maximum=high)
            accessible_name = text
            description = self.tr("Dashed lines mark each line's current analysis range.")
        self._analysis_range_label.setText(text)
        self._analysis_range_label.setToolTip(description)
        self._analysis_range_label.setAccessibleName(accessible_name)
        self._analysis_range_label.setAccessibleDescription(description)

    def _apply_display_spinbox_accessibility(self) -> None:
        """Apply localized baseline accessibility text when no error is active."""
        if self._display_spinbox is None:
            return
        self._display_spinbox.setAccessibleName(self.tr("Display range"))
        if self._last_rejection is None:
            self._display_spinbox.setAccessibleDescription(
                self.tr("Symmetric plot-local velocity display range in ±km/s.")
            )


__all__ = ["SpectrumVelocityOverlayWidget"]
