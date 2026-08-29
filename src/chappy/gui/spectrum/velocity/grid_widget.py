"""Grid widget for displaying spectra in velocity space."""

from __future__ import annotations

import logging
from contextlib import suppress
from functools import partial
from typing import TYPE_CHECKING, Literal

from PySide6.QtCore import QCoreApplication, QRect, QSize, Qt, Signal
from PySide6.QtGui import QCursor, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from chappy.core.constants import LIGHT_SPEED_KMS
from chappy.gui.spectrum.velocity.subplot_widget import VelocityPointerEvent, VelocitySubplotWidget
from chappy.gui.theme import Fonts, apply_button_variant
from chappy.i18n import LanguageSwitcher, get_language_switcher
from chappy.presentation.velocity import (
    VelocityComponentCreateRequest,
    VelocityContextMenuRequest,
    VelocityCurveSources,
    VelocityDisplayHalfWidth,
    VelocityDragComplete,
    VelocityDragRequest,
    VelocityDragUpdate,
    VelocityGridPage,
    VelocityGridPresenter,
    VelocityPaginationState,
    VelocitySliceInfo,
    VelocitySliceRenderFailureReason,
    VelocityUnit,
    VelocityViewData,
    VelocityVisibleSliceState,
    build_velocity_pagination_state,
    build_velocity_slot_render_input,
    build_visible_slice_states,
    compute_auto_flux_range,
    compute_velocity_grid_capacity,
    compute_velocity_grid_shape,
    normalize_velocity_slices,
    preserve_velocity_slice_selection,
    selected_velocity_slices,
    toggle_velocity_slice_selection,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from PySide6.QtGui import QCloseEvent, QPaintEvent, QResizeEvent

type VelocityGridMode = Literal["identify", "optimize"]

logger = logging.getLogger(__name__)


class RotatedAxisLabel(QWidget):
    """Axis caption drawn bottom-to-top along the left edge of the grid."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create an empty vertical caption widget."""
        super().__init__(parent)
        self._text = ""
        font = self.font()
        font.setPointSize(Fonts.POINT_SIZE_TINY)
        self.setFont(font)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

    def set_text(self, text: str) -> None:
        """Set the caption text and refresh geometry."""
        self._text = text
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt virtual API
        """Return the rotated text extent."""
        metrics = QFontMetrics(self.font())
        return QSize(metrics.height() + 4, metrics.horizontalAdvance(self._text) + 4)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt virtual API
        """Return the rotated text extent."""
        return self.sizeHint()

    def paintEvent(self, _event: QPaintEvent) -> None:  # noqa: N802 - Qt virtual API
        """Draw the caption rotated 90 degrees counter-clockwise."""
        painter = QPainter(self)
        painter.rotate(-90)
        painter.drawText(
            QRect(-self.height(), 0, self.height(), self.width()),
            Qt.AlignmentFlag.AlignCenter,
            self._text,
        )


class VelocityGridWidget(QWidget):
    """Velocity plot grid rendered as a paginated set of subplots."""

    DEFAULT_CAPACITY: tuple[int, int] = (2, 3)

    # D&D signals: component_id, velocity, rest_wavelength, flux, center_z
    sig_velocity_drag_requested = Signal(object)
    sig_velocity_drag_update = Signal(object)
    sig_velocity_drag_complete = Signal(object)

    # Context menu payload request
    sig_context_menu_requested = Signal(object)

    # Shift+click payload request
    sig_shift_click_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create an empty velocity view grid."""
        super().__init__(parent)

        self._language_switcher: LanguageSwitcher = get_language_switcher(self)
        self._placeholder_no_lines = "No lines in view"
        self._placeholder_no_spectrum = "No spectrum loaded"
        self._placeholder_no_presets = "No preset lines selected"
        self._placeholder_no_samples = "No samples in current window"
        self._conversion_failed = "Velocity conversion failed"
        self._slot_label_template = "Slot {index}"
        self._page_status_template = "{current} / {total}"
        self._page_empty_text = "0 / 0"

        self.rest_wavelength: float = 5000.0
        self.center_redshift: float = 0.0
        self._display_half_width = VelocityDisplayHalfWidth(500.0)
        self.velocity_unit: VelocityUnit = "km/s"
        self._mode: VelocityGridMode = "identify"
        self._selection_controls_visible = True

        self._info_label: QLabel | None = None
        self._external_context_label: QLabel | None = None
        self._grid_layout: QGridLayout | None = None
        self._x_axis_label: QLabel | None = None
        self._y_axis_label: RotatedAxisLabel | None = None
        self._subplot_widgets: list[VelocitySubplotWidget] = []
        self._capacity: tuple[int, int] = self.DEFAULT_CAPACITY
        self._slice_meta: tuple[VelocitySliceInfo, ...] = ()
        self._view_data = VelocityViewData(observed=None, model=None, slices=())
        self._selection_scope_key: str | None = None
        self._context_text: str = ""
        self._current_page: int = 0
        self._grid_presenter = VelocityGridPresenter()
        self._page_label: QLabel | None = None
        self._prev_button: QPushButton | None = None
        self._next_button: QPushButton | None = None
        self._page_controls: QWidget | None = None
        self._manual_y_range_set: bool = False
        self._tie_member_resolver: Callable[[str], frozenset[str]] | None = None
        self._linked_drag_subplots: list[VelocitySubplotWidget] = []

        self._build_ui()

        self._language_switcher.language_changed.connect(self._on_language_changed)
        self._apply_translations()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Release subplot widgets and language callbacks when closing."""
        for subplot in self._subplot_widgets:
            subplot.close()
        with suppress(RuntimeError, TypeError):
            self._language_switcher.language_changed.disconnect(self._on_language_changed)
        QWidget.closeEvent(self, event)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._info_label = QLabel(self)
        self._info_label.setObjectName("velocityViewContext")
        self._info_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._info_label.setStyleSheet(f"font-size: {Fonts.SIZE_NORMAL}; font-weight: 500;")
        self._info_label.setWordWrap(True)
        layout.addWidget(self._info_label)

        plot_area = QWidget(self)
        plot_area_layout = QGridLayout(plot_area)
        plot_area_layout.setContentsMargins(0, 0, 0, 0)
        plot_area_layout.setSpacing(0)

        self._y_axis_label = RotatedAxisLabel(plot_area)
        self._y_axis_label.setObjectName("velocityGridYAxisLabel")
        plot_area_layout.addWidget(self._y_axis_label, 0, 0)

        grid_host = QWidget(plot_area)
        self._grid_layout = QGridLayout(grid_host)
        self._grid_layout.setContentsMargins(2, 2, 2, 2)
        self._grid_layout.setSpacing(2)
        plot_area_layout.addWidget(grid_host, 0, 1)

        self._x_axis_label = QLabel(plot_area)
        self._x_axis_label.setObjectName("velocityGridXAxisLabel")
        self._x_axis_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._x_axis_label.setStyleSheet(f"font-size: {Fonts.SIZE_TINY};")
        plot_area_layout.addWidget(self._x_axis_label, 1, 1)

        plot_area_layout.setRowStretch(0, 1)
        plot_area_layout.setColumnStretch(1, 1)
        layout.addWidget(plot_area, 1)

        self._initialise_subplots()

        controls_container = QWidget(self)
        controls_layout = QHBoxLayout(controls_container)
        controls_layout.setContentsMargins(12, 0, 12, 0)
        controls_layout.setSpacing(8)

        prev_button = QPushButton("◀", controls_container)
        prev_button.setObjectName("velocityPlotPrevPage")
        prev_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        prev_button.setEnabled(False)
        prev_button.clicked.connect(lambda: self._set_page(self._current_page - 1))
        apply_button_variant(prev_button, "secondary")
        controls_layout.addWidget(prev_button, 0, Qt.AlignmentFlag.AlignLeft)

        page_label = QLabel("0 / 0", controls_container)
        page_label.setObjectName("velocityPlotPageLabel")
        page_label.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        page_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        controls_layout.addWidget(page_label, 1, Qt.AlignmentFlag.AlignCenter)

        next_button = QPushButton("▶", controls_container)
        next_button.setObjectName("velocityPlotNextPage")
        next_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        next_button.setEnabled(False)
        next_button.clicked.connect(lambda: self._set_page(self._current_page + 1))
        apply_button_variant(next_button, "secondary")
        controls_layout.addWidget(next_button, 0, Qt.AlignmentFlag.AlignRight)

        layout.addWidget(controls_container)

        self._page_controls = controls_container
        self._prev_button = prev_button
        self._next_button = next_button
        self._page_label = page_label

    def _initialise_subplots(self) -> None:
        """Populate the grid layout with placeholder subplot widgets."""
        if self._grid_layout is None:
            return
        for widget in self._subplot_widgets:
            widget.setParent(None)
        self._subplot_widgets.clear()

        self._ensure_subplot_count(self._page_size())
        self._relayout_grid(0)

    def _page_size(self) -> int:
        """Return the number of subplot slots on one page for the current capacity."""
        rows, columns = self._capacity
        return rows * columns

    def _ensure_subplot_count(self, count: int) -> None:
        """Lazily create subplot widgets until at least ``count`` exist."""
        while len(self._subplot_widgets) < count:
            self._subplot_widgets.append(self._create_subplot(len(self._subplot_widgets)))

    def _create_subplot(self, index: int) -> VelocitySubplotWidget:
        """Create one subplot widget wired to the grid's index-based handlers."""
        subplot = VelocitySubplotWidget(self._language_switcher, self)
        subplot.set_heading(self._format_slot_label(index + 1))
        subplot.set_selection_visible(self._selection_controls_visible)
        subplot.selection_toggled.connect(partial(self._handle_slice_toggled, index))
        subplot.mouse_pressed.connect(partial(self._on_subplot_mouse_pressed, subplot))
        subplot.mouse_moved.connect(partial(self._on_subplot_mouse_moved, subplot))
        subplot.mouse_released.connect(partial(self._on_subplot_mouse_released, subplot))
        subplot.context_menu_requested.connect(
            partial(self._on_subplot_context_menu_requested, index)
        )
        subplot.shift_click_requested.connect(
            partial(self._on_subplot_shift_click_requested, index)
        )
        return subplot

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt virtual API
        """Adapt the subplot capacity to the available widget area."""
        super().resizeEvent(event)
        capacity = compute_velocity_grid_capacity(width_px=self.width(), height_px=self.height())
        if capacity == self._capacity:
            return
        self._capacity = capacity
        self._ensure_subplot_count(self._page_size())
        self._update_velocity_display()

    def _relayout_grid(self, visible_count: int) -> None:
        """Arrange subplot cells to fit the visible slice count without empty slots."""
        if self._grid_layout is None:
            return
        max_rows, max_columns = self._capacity
        cell_count = max(1, min(visible_count, self._page_size()))
        rows, columns = compute_velocity_grid_shape(
            cell_count, max_rows=max_rows, max_columns=max_columns
        )
        for subplot in self._subplot_widgets:
            self._grid_layout.removeWidget(subplot)
        for index, subplot in enumerate(self._subplot_widgets):
            if index < cell_count:
                self._grid_layout.addWidget(subplot, index // columns, index % columns)
            subplot.setVisible(index < cell_count)
            subplot.set_tick_labels_visible(
                x=index + columns >= cell_count, y=index % columns == 0
            )
        for row in range(self._grid_layout.rowCount()):
            self._grid_layout.setRowStretch(row, 1 if row < rows else 0)
        for column in range(self._grid_layout.columnCount()):
            self._grid_layout.setColumnStretch(column, 1 if column < columns else 0)

    def apply_view_data(self, data: VelocityViewData) -> None:
        """Apply the non-Qt data package rendered by this widget."""
        self._view_data = data
        preserve_selection = (
            data.selection_scope_key is not None
            and data.selection_scope_key == self._selection_scope_key
        )
        if not preserve_selection:
            self._current_page = 0
        self._slice_meta = (
            preserve_velocity_slice_selection(self._slice_meta, tuple(data.slices))
            if preserve_selection
            else normalize_velocity_slices(tuple(data.slices))
        )
        self._selection_scope_key = data.selection_scope_key
        self._update_velocity_display()

    def set_mode(self, mode: VelocityGridMode) -> None:
        """Set the display mode (identify or optimize).

        Args:
            mode: The active mode using this widget.
        """
        self._mode = mode

    def set_tie_member_resolver(self, resolver: Callable[[str], frozenset[str]] | None) -> None:
        """Set the resolver mapping a component id to its redshift-tied member ids."""
        self._tie_member_resolver = resolver

    def set_selection_controls_visible(self, visible: bool) -> None:
        """Control visibility of selection controls (checkboxes) in all subplots.

        Args:
            visible: True to show checkboxes (identify mode), False to hide (optimize mode).
        """
        self._selection_controls_visible = visible
        for subplot in self._subplot_widgets:
            subplot.set_selection_visible(visible)

    def set_rest_wavelength(self, wavelength: float) -> None:
        """Set the rest wavelength used for velocity conversion."""
        self.rest_wavelength = wavelength
        self._update_velocity_display()

    def set_center_redshift(self, center_z: float) -> None:
        """Set the redshift that defines the zero-velocity pivot."""
        self.center_redshift = center_z
        self._update_velocity_display()

    @property
    def display_half_width(self) -> VelocityDisplayHalfWidth:
        """Return the typed plot-local display half-width."""
        return self._display_half_width

    def set_display_half_width(self, value: VelocityDisplayHalfWidth) -> None:
        """Apply one validated display half-width to every subplot and page."""
        if value == self._display_half_width:
            return
        self._display_half_width = value
        self._update_velocity_display()

    def refresh_plot(self) -> None:
        """Re-render the grid with the latest project data."""
        self._update_velocity_display()

    def set_flux_range(self, min_flux: float, max_flux: float) -> None:
        """Set the Y-axis (flux) range for all subplots.

        Args:
            min_flux: Minimum flux value.
            max_flux: Maximum flux value.
        """
        self._manual_y_range_set = True
        for subplot in self._subplot_widgets:
            subplot.set_flux_range(min_flux, max_flux)

    def is_manual_y_range_active(self) -> bool:
        """Return whether a manual Y range is active."""
        return self._manual_y_range_set

    def reset_manual_y_range(self) -> None:
        """Reset manual Y range state so the next render may auto-range."""
        self._manual_y_range_set = False

    def auto_range_y_all(self) -> None:
        """Auto-range Y-axis for all subplots using unified range.

        Collects min/max from all subplots' observed data and applies
        a unified range to ensure consistent comparison across subplots.
        """
        auto_range = compute_auto_flux_range(self._page_observed_y_ranges())
        if auto_range is None:
            return  # No valid data found

        # Apply unified range to all subplots (bypass flag by calling subplot directly)
        for subplot in self._subplot_widgets:
            subplot.set_flux_range(*auto_range)

        # Reset manual flag after auto-range
        self._manual_y_range_set = False

    def get_global_observed_y_range(self) -> tuple[float, float] | None:
        """Get unified Y range from all subplots' observed data.

        Returns:
            Tuple of (y_min, y_max) with margins applied, or None if no valid data.
        """
        return compute_auto_flux_range(self._page_observed_y_ranges())

    def _page_observed_y_ranges(self) -> tuple[tuple[float, float] | None, ...]:
        """Collect observed Y ranges from subplots within the current page capacity."""
        return tuple(
            subplot.get_observed_y_range()
            for subplot in self._subplot_widgets[: self._page_size()]
        )

    def get_selected_slices(self) -> list[VelocitySliceInfo]:
        """Return the currently selected slice descriptors."""
        return list(selected_velocity_slices(self._slice_meta))

    def pagination_state(self) -> VelocityPaginationState:
        """Return read-only pagination state for the grid."""
        return build_velocity_pagination_state(self._build_grid_page())

    def visible_slice_states(self) -> tuple[VelocityVisibleSliceState, ...]:
        """Return read-only slot states for the current visible page."""
        return build_visible_slice_states(
            slices=self._slice_meta,
            page=self._build_grid_page(),
            slot_label_builder=self._format_slot_label,
        )

    def update_context_label(self, parts: Iterable[str]) -> None:
        """Update the descriptive summary shown above the subplot grid."""
        text = " | ".join(filter(None, parts))
        self._context_text = text
        if self._external_context_label is not None:
            self._external_context_label.setText(text)
        if self._info_label is not None and (self._external_context_label is None):
            self._info_label.setText(text)

    def attach_context_label(self, label: QLabel | None) -> None:
        """Redirect context text to an external label within a parent header."""
        self._external_context_label = label
        if self._info_label is not None:
            use_internal = label is None
            self._info_label.setVisible(use_internal)
            if use_internal:
                self._info_label.setText(self._context_text)
        if label is not None:
            label.setText(self._context_text)

    def reset_selection_state(self) -> None:
        """Forget overlay-local selection state so the next activation starts fresh."""
        self._selection_scope_key = None

    def _update_velocity_display(self) -> None:
        if not self._subplot_widgets:
            return

        page = self._build_grid_page()
        self._current_page = page.current_page
        self._relayout_grid(page.visible_count)
        visible_states = self.visible_slice_states()

        placeholder_messages: dict[VelocitySliceRenderFailureReason, str] = {
            "no_spectrum": self._placeholder_no_spectrum,
            "no_slices": self._placeholder_no_presets,
            "no_lines": self._placeholder_no_lines,
            "no_samples": self._placeholder_no_samples,
            "conversion_failed": self._conversion_failed,
        }
        empty_reason: Literal["no_lines", "no_slices"] = (
            "no_slices" if not self._slice_meta else "no_lines"
        )
        for subplot, visible_state in zip(self._subplot_widgets, visible_states, strict=False):
            slice_info = (
                self._slice_meta[visible_state.absolute_index]
                if visible_state.absolute_index is not None
                else None
            )
            render_input = build_velocity_slot_render_input(
                slice_info,
                default_title=visible_state.title,
                sources=VelocityCurveSources(
                    observed=self._view_data.observed,
                    model=self._view_data.model,
                    component_profiles=self._view_data.component_profiles,
                    show_error_spectrum=self._view_data.show_error_spectrum,
                ),
                display_half_width=self._display_half_width,
                unit=self.velocity_unit,
                optimize_mode=self._mode == "optimize",
                empty_reason=empty_reason,
            )
            subplot.apply_render_input(render_input, placeholder_messages)

        for subplot in self._subplot_widgets[len(visible_states) :]:
            subplot.set_checked(False)
            subplot.set_components([])
            subplot.show_placeholder()

        self._update_pagination_controls()

        # Apply unified Y-axis range only if not manually set
        if not self._manual_y_range_set:
            self.auto_range_y_all()

    def _handle_slice_toggled(self, index: int, checked: bool) -> None:
        """Persist checkbox changes into the slice metadata."""
        page = self._build_grid_page()
        absolute_index = page.absolute_index(index)
        self._slice_meta = toggle_velocity_slice_selection(
            self._slice_meta, absolute_index=absolute_index, checked=checked
        )
        self._view_data = VelocityViewData(
            observed=self._view_data.observed,
            model=self._view_data.model,
            slices=self._slice_meta,
            selection_scope_key=self._selection_scope_key,
            component_profiles=self._view_data.component_profiles,
            show_error_spectrum=self._view_data.show_error_spectrum,
        )
        self._update_velocity_display()

    def _set_page(self, page_index: int) -> None:
        page = self._build_grid_page(requested_page=page_index)
        if page.current_page == self._current_page:
            return
        self._current_page = page.current_page
        self._update_velocity_display()

    def _build_grid_page(self, requested_page: int | None = None) -> VelocityGridPage:
        """Return presenter-computed pagination state for the current view."""
        return self._grid_presenter.build_page(
            slice_count=len(self._slice_meta),
            subplot_count=self._page_size(),
            requested_page=self._current_page if requested_page is None else requested_page,
        )

    def _update_pagination_controls(self) -> None:
        if self._page_label is None or self._prev_button is None or self._next_button is None:
            return

        total_slices = len(self._slice_meta)
        page = self._build_grid_page()
        self._current_page = page.current_page

        if page.total_pages == 0:
            display_text = self._page_empty_text
        else:
            try:
                display_text = self._page_status_template.format(
                    current=page.one_based_page, total=page.total_pages
                )
            except (KeyError, ValueError):
                display_text = f"{page.one_based_page} / {page.total_pages}"

        self._page_label.setText(display_text)

        self._prev_button.setEnabled(page.current_page > 0)
        self._next_button.setEnabled(
            page.total_pages > 0 and page.current_page < (page.total_pages - 1)
        )

        if self._page_controls is not None:
            self._page_controls.setVisible(total_slices > page.page_size)

    def _format_slot_label(self, slot_number: int) -> str:
        try:
            return self._slot_label_template.format(index=slot_number)
        except (KeyError, ValueError):
            return self._slot_label_template

    def _apply_translations(self) -> None:
        self._placeholder_no_lines = self.tr("No lines in view")
        self._placeholder_no_spectrum = self.tr("No spectrum loaded")
        self._placeholder_no_presets = self.tr("No preset lines selected")
        self._placeholder_no_samples = self.tr("No samples in current window")
        self._conversion_failed = self.tr("Velocity conversion failed")
        self._slot_label_template = self.tr("Slot {index}")
        self._page_status_template = self.tr("{current} / {total}")
        self._page_empty_text = self.tr("0 / 0")

        if self._x_axis_label is not None:
            self._x_axis_label.setText(
                QCoreApplication.translate("VelocitySubplot", "Velocity (km/s)")
            )
        if self._y_axis_label is not None:
            self._y_axis_label.set_text(QCoreApplication.translate("VelocitySubplot", "Flux"))

        self._update_velocity_display()

    def cancel_active_drag(self) -> bool:
        """Cancel active drag state across all visible velocity subplots."""
        cancelled = False
        for subplot in self._subplot_widgets:
            cancelled = subplot.cancel_active_drag() or cancelled
        self._linked_drag_subplots.clear()
        return cancelled

    def _on_language_changed(self, _code: str) -> None:
        self._apply_translations()

    def _get_center_z_for_subplot(self, subplot: VelocitySubplotWidget) -> float:
        """Get the center_z for a specific subplot.

        Args:
            subplot: The VelocitySubplotWidget.

        Returns:
            The center_z for the subplot's slice.

        Raises:
            ValueError: If subplot is not found or center_z is not set.
        """
        # Find subplot index in widget list
        try:
            subplot_index = self._subplot_widgets.index(subplot)
        except ValueError as err:
            msg = "_get_center_z_for_subplot: subplot not found in widget list"
            raise ValueError(msg) from err

        # Calculate absolute slice index (accounting for pagination)
        absolute_index = self._build_grid_page().absolute_index(subplot_index)

        if absolute_index >= len(self._slice_meta):
            msg = (
                f"_get_center_z_for_subplot: absolute_index={absolute_index} "
                f">= len(slice_meta)={len(self._slice_meta)}"
            )
            raise ValueError(msg)

        slice_info = self._slice_meta[absolute_index]
        if slice_info.center_z is None:
            msg = (
                f"_get_center_z_for_subplot: center_z is None for slice at index {absolute_index}"
            )
            raise ValueError(msg)

        return slice_info.center_z

    def _on_subplot_mouse_pressed(
        self, subplot: VelocitySubplotWidget, event: VelocityPointerEvent
    ) -> None:
        """Handle mouse press from a subplot.

        Args:
            subplot: The subplot that received the mouse event.
            event: Pointer event in velocity-space coordinates.
        """
        if event.component is not None:
            # Get center_z from slice info for this subplot
            center_z = self._get_center_z_for_subplot(subplot)
            self.sig_velocity_drag_requested.emit(
                VelocityDragRequest(
                    component_id=event.component.component_id,
                    velocity=event.velocity,
                    rest_wavelength=event.component.rest_wavelength,
                    flux=event.flux,
                    center_z=center_z,
                )
            )

    def _on_subplot_mouse_moved(
        self, subplot: VelocitySubplotWidget, event: VelocityPointerEvent
    ) -> None:
        """Handle mouse move from a subplot during drag.

        Args:
            subplot: The subplot that received the mouse event.
            event: Pointer event in velocity-space coordinates.
        """
        if event.component is not None:
            center_z = self._get_center_z_for_subplot(subplot)
            self.sig_velocity_drag_update.emit(
                VelocityDragUpdate(
                    component_id=event.component.component_id,
                    velocity=event.velocity,
                    rest_wavelength=event.component.rest_wavelength,
                    flux=event.flux,
                    center_z=center_z,
                )
            )
            self._update_linked_drag_overlays(
                subplot, event.component.component_id, event.velocity, center_z
            )

    def _update_linked_drag_overlays(
        self,
        source_subplot: VelocitySubplotWidget,
        component_id: str,
        source_velocity: float,
        source_center_z: float,
    ) -> None:
        """Mirror the in-progress drag onto other subplots showing tied components."""
        self._clear_linked_drag_overlays()
        if self._tie_member_resolver is None:
            return

        member_ids = self._tie_member_resolver(component_id)
        if len(member_ids) < 2:
            return

        redshift = source_center_z + source_velocity * (1.0 + source_center_z) / LIGHT_SPEED_KMS
        page = self._build_grid_page()
        for index, subplot in enumerate(self._subplot_widgets):
            if subplot is source_subplot:
                continue
            absolute_index = page.absolute_index(index)
            if absolute_index >= len(self._slice_meta):
                continue
            slice_info = self._slice_meta[absolute_index]
            if slice_info.center_z is None:
                continue
            if not any(
                component.component_id in member_ids for component in slice_info.components
            ):
                continue
            velocity = (
                LIGHT_SPEED_KMS * (redshift - slice_info.center_z) / (1.0 + slice_info.center_z)
            )
            subplot.set_linked_drag_overlay(velocity)
            self._linked_drag_subplots.append(subplot)

    def _clear_linked_drag_overlays(self) -> None:
        """Clear any drag overlays previously mirrored onto other subplots."""
        for subplot in self._linked_drag_subplots:
            subplot.set_linked_drag_overlay(None)
        self._linked_drag_subplots.clear()

    def _on_subplot_mouse_released(
        self, subplot: VelocitySubplotWidget, event: VelocityPointerEvent
    ) -> None:
        """Handle mouse release from a subplot to complete drag.

        Args:
            subplot: The subplot that received the mouse event.
            event: Pointer event in velocity-space coordinates.
        """
        if event.component is not None:
            center_z = self._get_center_z_for_subplot(subplot)
            self.sig_velocity_drag_complete.emit(
                VelocityDragComplete(
                    component_id=event.component.component_id,
                    velocity=event.velocity,
                    rest_wavelength=event.component.rest_wavelength,
                    flux=event.flux,
                    center_z=center_z,
                )
            )
            self._clear_linked_drag_overlays()

    def _on_subplot_context_menu_requested(self, subplot_index: int, velocity: float) -> None:
        """Handle context menu request from a subplot.

        Args:
            subplot_index: Index of the subplot within the current page.
            velocity: Velocity coordinate in km/s where the menu was requested.
        """
        absolute_index = self._build_grid_page().absolute_index(subplot_index)
        if absolute_index >= len(self._slice_meta):
            return

        slice_info = self._slice_meta[absolute_index]
        if slice_info.line_id is None:
            return

        if slice_info.center_z is None:
            return

        global_pos = QCursor.pos()
        self.sig_context_menu_requested.emit(
            VelocityContextMenuRequest(
                velocity=velocity,
                line_id=slice_info.line_id,
                rest_wavelength=slice_info.rest_wavelength,
                center_z=slice_info.center_z,
                global_position=(global_pos.x(), global_pos.y()),
            )
        )

    def _on_subplot_shift_click_requested(self, subplot_index: int, velocity: float) -> None:
        """Handle Shift+click request from a subplot.

        Args:
            subplot_index: Index of the subplot within the current page.
            velocity: Velocity coordinate in km/s where the click occurred.
        """
        # Determine absolute slice index from page and subplot position
        absolute_index = self._build_grid_page().absolute_index(subplot_index)
        if absolute_index >= len(self._slice_meta):
            return

        slice_info = self._slice_meta[absolute_index]
        if slice_info.line_id is None:
            return

        if slice_info.center_z is None:
            return

        self.sig_shift_click_requested.emit(
            VelocityComponentCreateRequest(
                velocity=velocity,
                line_id=slice_info.line_id,
                rest_wavelength=slice_info.rest_wavelength,
                center_z=slice_info.center_z,
            )
        )


__all__ = ["VelocityGridWidget", "VelocityPointerEvent", "VelocitySubplotWidget"]
