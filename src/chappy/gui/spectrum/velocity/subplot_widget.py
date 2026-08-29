"""Qt widget for a single velocity subplot."""

from __future__ import annotations

import logging
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from matplotlib.backend_bases import Event, MouseEvent
from PySide6.QtCore import QCoreApplication, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStackedLayout,
    QWidget,
)

from chappy.gui.adapters.plotting import (
    MatplotlibSpectrumPlot,
    create_matplotlib_mouse_event_bridge_adapter,
)
from chappy.gui.theme import Colors, Fonts
from chappy.i18n import LanguageSwitcher, get_language_switcher
from chappy.plotting.component_labels import ComponentLabelEntry
from chappy.plotting.utils.validators import validate_generic_spectrum_data
from chappy.plotting.velocity import VelocitySubplotRenderer
from chappy.presentation.spectrum import (
    SpectrumComponentCurve,
    format_abbreviated_component_marker_label,
    format_component_marker_label,
)

if TYPE_CHECKING:
    from matplotlib.lines import Line2D
    from numpy.typing import NDArray
    from PySide6.QtGui import QCloseEvent

    from chappy.presentation.velocity import (
        VelocityComponentInfo,
        VelocitySliceRenderFailureReason,
        VelocitySliceRenderInput,
    )

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VelocityPointerEvent:
    """Pointer event in velocity-space coordinates."""

    velocity: float
    flux: float
    component: VelocityComponentInfo | None


@dataclass(frozen=True, slots=True)
class VelocitySubplotRenderState:
    """Read-only snapshot of subplot display state."""

    title: str
    placeholder_visible: bool
    placeholder_text: str
    selection_checked: bool
    selection_enabled: bool
    selection_visible: bool
    flux_range: tuple[float, float]
    residual_visible: bool
    center_line_count: int
    component_marker_count: int
    component_ids: tuple[str, ...]
    analysis_boundary_count: int
    analysis_out_of_view_text: str | None
    display_velocity_range: tuple[float, float]


def resolve_velocity_component_hit(
    components: tuple[VelocityComponentInfo, ...], *, velocity: float, tolerance: float = 50.0
) -> VelocityComponentInfo | None:
    """Return the closest component within tolerance for a velocity coordinate."""
    closest: VelocityComponentInfo | None = None
    min_distance = float("inf")

    for component in components:
        distance = abs(velocity - component.velocity)
        if distance <= tolerance and distance < min_distance:
            closest = component
            min_distance = distance
    return closest


class VelocitySubplotWidget(QFrame):
    """Single subplot cell within the velocity plot grid."""

    selection_toggled = Signal(bool)
    mouse_pressed = Signal(VelocityPointerEvent)
    mouse_moved = Signal(VelocityPointerEvent)
    mouse_released = Signal(VelocityPointerEvent)
    context_menu_requested = Signal(float)
    shift_click_requested = Signal(float)

    def __init__(
        self, language_switcher: LanguageSwitcher | None = None, parent: QWidget | None = None
    ) -> None:
        """Initialise the subplot frame and its nested plot widget."""
        super().__init__(parent)

        self._language_switcher: LanguageSwitcher = language_switcher or get_language_switcher(
            self
        )
        self._default_placeholder = "No velocity data"
        self._auto_label_default = "Group (auto)"
        self._baseline_template = "{label} (baseline)"
        self._analysis_out_of_view_template = (
            "Analysis range extends beyond view (±{value:g} km/s)"
        )
        self._analysis_bounds_template = (
            "Dashed lines mark analysis boundaries at ±{value:g} km/s."
        )
        self._components: list[VelocityComponentInfo] = []
        self._dragging_component: VelocityComponentInfo | None = None

        self.setObjectName("velocitySubplot")
        self.setStyleSheet(
            f"QFrame#velocitySubplot {{ border: 1px solid {Colors.BORDER_DEFAULT};"
            f" border-radius: 3px; }}"
        )
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedLayout()
        layout.addLayout(self._stack, 0, 0)

        self._header = QWidget(self)
        self._header.setObjectName("velocitySubplotHeader")
        self._header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(4, 2, 4, 2)
        header_layout.setSpacing(6)

        self._selection_visible = True
        self._checkbox = QCheckBox(self._header)
        self._checkbox.setObjectName("velocitySubplotSelection")
        self._checkbox.setTristate(False)
        self._checkbox.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._apply_selection_style()
        header_layout.addWidget(self._checkbox, 0, Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(
            self._header, 0, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )

        self._plot_widget = MatplotlibSpectrumPlot(
            self,
            mouse_event_bridge_factory=create_matplotlib_mouse_event_bridge_adapter,
            observed_data_validator=validate_generic_spectrum_data,
            constrained_layout=True,
            tick_labelsize=float(Fonts.POINT_SIZE_TINY),
            show_axis_labels=False,
        )
        self._plot_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._plot_renderer = VelocitySubplotRenderer(self._plot_widget)
        self._stack.addWidget(self._plot_widget)

        if self._plot_renderer.connect_mouse_events(
            self._on_mouse_press, self._on_mouse_move, self._on_mouse_release
        ):
            logger.debug("VelocitySubplotWidget: mouse events connected to canvas")
        else:
            logger.warning("VelocitySubplotWidget: mouse events NOT connected")

        self._placeholder = QLabel("", self)
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet(f"color: #707070; font-size: {Fonts.SIZE_TINY};")
        self._stack.addWidget(self._placeholder)
        # QStackedLayout raises the current widget on every switch, so re-raise the header.
        self._stack.currentChanged.connect(lambda _index: self._header.raise_())
        self._header.raise_()

        self._language_switcher.language_changed.connect(self._on_language_changed)
        self._apply_translations()

        self.show_placeholder()
        self._checkbox.toggled.connect(self.selection_toggled.emit)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Release subplot callbacks when the Qt widget closes."""
        self._plot_renderer.disconnect_mouse_events()
        with suppress(RuntimeError, TypeError):
            self._language_switcher.language_changed.disconnect(self._on_language_changed)
        self._plot_widget.close()
        QFrame.closeEvent(self, event)

    @property
    def _center_lines(self) -> tuple[Line2D, ...]:
        """Return center-line artists owned by the plotting renderer."""
        return self._plot_renderer.center_lines()

    def set_heading(self, text: str | None, *, primary: bool = False) -> None:
        """Set the human-readable title for this subplot."""
        label = text or self._auto_label_default
        if primary:
            label = self._baseline_template.format(label=label)
        self._checkbox.setText(label)

    def set_checked(self, value: bool) -> None:
        """Update checkbox state without emitting signals."""
        previous = self._checkbox.blockSignals(True)
        self._checkbox.setChecked(value)
        self._checkbox.blockSignals(previous)

    def is_checked(self) -> bool:
        """Return current checkbox state."""
        return self._checkbox.isChecked()

    def set_selection_enabled(self, enabled: bool) -> None:
        """Enable or disable the selection checkbox."""
        self._checkbox.setEnabled(enabled)

    def set_selection_visible(self, visible: bool) -> None:
        """Show or hide the selection indicator while keeping the title text visible."""
        self._selection_visible = visible
        self._apply_selection_style()
        self._checkbox.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, not visible)
        self._header.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, not visible)

    def _apply_selection_style(self) -> None:
        self._header.setStyleSheet(
            "QWidget#velocitySubplotHeader"
            " { background-color: rgba(0, 0, 0, 150); border-radius: 3px; }"
        )
        style = (
            f"QCheckBox {{ font-size: {Fonts.SIZE_SMALL}; font-weight: 600;"
            f" color: {Colors.TEXT_PRIMARY}; }}"
            f" QCheckBox:disabled {{ color: {Colors.TEXT_PRIMARY}; }}"
        )
        if not self._selection_visible:
            style += (
                " QCheckBox { spacing: 0px; } QCheckBox::indicator"
                " { width: 0px; height: 0px; border: none; margin: 0px; }"
            )
        self._checkbox.setStyleSheet(style)

    def clear_mask_patches(self) -> None:
        """Clear previously rendered mask patches."""
        self._plot_renderer.clear_mask_patches()

    def blocks_plot_mouse_forwarding(self) -> bool:
        """Return whether the nested plot should suppress shared mouse forwarding."""
        return True

    def add_mask_region(self, velocity_min: float, velocity_max: float, color: str) -> None:
        """Add a masked velocity region."""
        self._plot_renderer.add_mask_region(velocity_min, velocity_max, color)

    def add_center_line(
        self,
        velocity: float,
        *,
        color: str = "yellow",
        linestyle: str = "--",
        alpha: float = 0.7,
        linewidth: float = 1.0,
        zorder: int = 10,
        label: str | None = None,
    ) -> None:
        """Add a vertical center line at the specified velocity."""
        self._plot_renderer.add_center_line(
            velocity,
            color=color,
            linestyle=linestyle,
            alpha=alpha,
            linewidth=linewidth,
            zorder=zorder,
            label=label,
        )

    def clear_center_lines(self) -> None:
        """Remove all center lines from the subplot."""
        self._plot_renderer.clear_center_lines()

    def set_data(
        self,
        velocity: NDArray[np.float64],
        flux: NDArray[np.float64],
        error: NDArray[np.float64] | None,
        display_half_width_kms: float,
    ) -> None:
        """Render the supplied velocity-space spectrum."""
        rendered = self._plot_renderer.set_data(velocity, flux, error, display_half_width_kms)

        if not rendered:
            self.show_placeholder()
            return

        self._stack.setCurrentWidget(self._plot_widget)

    def set_model_spectrum(self, velocity: NDArray[np.float64], flux: NDArray[np.float64]) -> None:
        """Set model data for display."""
        self._plot_renderer.set_model_spectrum(velocity, flux)

    def set_residual(self, velocity: NDArray[np.float64], residual: NDArray[np.float64]) -> None:
        """Set residual data for display."""
        self._plot_renderer.set_residual(velocity, residual)

    def get_observed_y_range(self) -> tuple[float, float] | None:
        """Get Y range from observed data only."""
        return self._plot_renderer.get_observed_y_range()

    def set_flux_range(self, min_flux: float, max_flux: float) -> None:
        """Set the Y-axis (flux) range manually."""
        self._plot_renderer.set_flux_range(min_flux, max_flux)

    def get_flux_range(self) -> tuple[float, float]:
        """Return the current Y-axis flux range."""
        return self._plot_renderer.get_flux_range()

    def set_tick_labels_visible(self, *, x: bool, y: bool) -> None:
        """Show or hide the axis tick labels for this subplot."""
        self._plot_renderer.set_tick_labels_visible(x=x, y=y)

    def show_placeholder(self, message: str | None = None) -> None:
        """Display placeholder text when no data is available."""
        self._plot_renderer.clear_center_lines()
        self._plot_renderer.clear_component_markers()
        self._plot_renderer.clear_component_profile_curves()
        self._plot_renderer.clear_analysis_bounds()
        self._plot_renderer.clear_drag_overlay()
        self._dragging_component = None
        text = message or self._default_placeholder
        self._placeholder.setText(text)
        self._stack.setCurrentWidget(self._placeholder)

    def render_state(self) -> VelocitySubplotRenderState:
        """Return a read-only snapshot of the current display state."""
        residual_data = self._plot_widget.data_store.get_residual_data()
        return VelocitySubplotRenderState(
            title=self._checkbox.text(),
            placeholder_visible=self._stack.currentWidget() is self._placeholder,
            placeholder_text=self._placeholder.text(),
            selection_checked=self._checkbox.isChecked(),
            selection_enabled=self._checkbox.isEnabled(),
            selection_visible=self._selection_visible,
            flux_range=self.get_flux_range(),
            residual_visible=residual_data is not None,
            center_line_count=len(self._plot_renderer.center_lines()),
            component_marker_count=self._plot_renderer.component_marker_count(),
            component_ids=tuple(component.component_id for component in self._components),
            analysis_boundary_count=self._plot_renderer.analysis_boundary_count(),
            analysis_out_of_view_text=self._plot_renderer.analysis_out_of_view_text(),
            display_velocity_range=self._plot_renderer.get_display_velocity_range(),
        )

    def _apply_translations(self) -> None:
        self._default_placeholder = QCoreApplication.translate(
            "VelocitySubplot", "No velocity data"
        )
        self._auto_label_default = QCoreApplication.translate("VelocitySubplot", "Region (auto)")
        self._baseline_template = QCoreApplication.translate(
            "VelocitySubplot", "{label} (baseline)"
        )
        #: {value} is the analysis half-width that extends beyond the current view.
        self._analysis_out_of_view_template = QCoreApplication.translate(
            "VelocitySubplot", "Analysis range extends beyond view (±{value:g} km/s)"
        )
        #: {value} is the symmetric analysis-boundary half-width in km/s.
        self._analysis_bounds_template = QCoreApplication.translate(
            "VelocitySubplot", "Dashed lines mark analysis boundaries at ±{value:g} km/s."
        )
        if self._stack.currentWidget() is self._placeholder:
            self._placeholder.setText(self._default_placeholder)

    def _on_language_changed(self, _code: str) -> None:
        self._apply_translations()

    def set_components(self, components: list[VelocityComponentInfo]) -> None:
        """Register components for D&D detection."""
        self._components = list(components)
        logger.debug(
            "VelocitySubplotWidget.set_components: received %d components", len(components)
        )

    def apply_render_input(
        self,
        render_input: VelocitySliceRenderInput,
        placeholder_messages: dict[VelocitySliceRenderFailureReason, str],
    ) -> None:
        """Apply a typed render input to the subplot."""
        self.clear_center_lines()
        self.clear_mask_patches()
        self._plot_renderer.clear_component_markers()
        self._plot_renderer.clear_component_profile_curves()
        self._plot_renderer.clear_analysis_bounds()
        self.setToolTip("")
        self.setAccessibleDescription("")

        self.set_heading(render_input.title, primary=render_input.primary)
        self.set_selection_enabled(render_input.selection_enabled)
        self.set_checked(render_input.selected)
        self.set_components(list(render_input.components))

        if render_input.kind == "failure":
            self.show_placeholder(placeholder_messages[render_input.reason])
            return

        observed_velocity = np.asarray(render_input.observed_velocity, dtype=np.float64)
        observed_flux = np.asarray(render_input.observed_flux, dtype=np.float64)
        observed_error = (
            np.asarray(render_input.observed_error, dtype=np.float64)
            if render_input.observed_error is not None
            else None
        )
        self.set_data(
            observed_velocity, observed_flux, observed_error, render_input.display_half_width_kms
        )

        out_of_view_message = None
        if render_input.analysis_bounds is not None:
            analysis_description = self._analysis_bounds_template.format(
                value=render_input.analysis_bounds.half_width_kms
            )
            if render_input.analysis_out_of_view:
                out_of_view_message = self._analysis_out_of_view_template.format(
                    value=render_input.analysis_bounds.half_width_kms
                )
                analysis_description = (
                    f"{analysis_description} {out_of_view_message}. "
                    f"{self.tr('Fit view to analysis ranges')}."
                )
            self.setToolTip(analysis_description)
            self.setAccessibleDescription(analysis_description)
        self._plot_renderer.set_analysis_bounds(
            render_input.analysis_bounds, out_of_view_message=out_of_view_message
        )

        if render_input.model_velocity is not None and render_input.model_flux is not None:
            self.set_model_spectrum(
                np.asarray(render_input.model_velocity, dtype=np.float64),
                np.asarray(render_input.model_flux, dtype=np.float64),
            )

        if render_input.residual is not None:
            self.set_residual(
                observed_velocity, np.asarray(render_input.residual, dtype=np.float64)
            )

        for mask_region in render_input.mask_regions:
            self.add_mask_region(
                mask_region.velocity_min, mask_region.velocity_max, mask_region.color
            )

        for center_line in render_input.center_lines:
            self.add_center_line(
                center_line.velocity,
                color=center_line.color,
                linestyle="--",
                alpha=0.7,
                label=center_line.label,
            )

        self._plot_renderer.set_component_markers(
            [
                ComponentLabelEntry(
                    x=component.velocity,
                    text=format_component_marker_label(component.label, component.tie_label),
                    short_text=format_abbreviated_component_marker_label(
                        component.label, component.tie_label
                    ),
                )
                for component in render_input.component_markers
            ]
        )
        self._plot_renderer.set_component_profile_curves(
            [
                SpectrumComponentCurve(
                    component_id=curve.component_id,
                    color=curve.color,
                    wavelength=np.asarray(curve.velocity, dtype=np.float64),
                    flux=np.asarray(curve.flux, dtype=np.float64),
                    emphasized=curve.emphasized,
                )
                for curve in render_input.component_profile_curves
            ]
        )

    def get_component_at_velocity(
        self, velocity: float, tolerance: float = 50.0
    ) -> VelocityComponentInfo | None:
        """Find component near the given velocity."""
        return resolve_velocity_component_hit(
            tuple(self._components), velocity=velocity, tolerance=tolerance
        )

    def _on_mouse_press(self, event: Event) -> None:
        """Handle matplotlib mouse press event for drag detection and context menu."""
        if not isinstance(event, MouseEvent):
            return
        if event.inaxes is None:
            return

        velocity = event.xdata
        if velocity is None:
            return

        if event.button == 3:
            self.context_menu_requested.emit(velocity)
            return

        if event.button != 1:
            return

        if event.guiEvent and (event.guiEvent.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.shift_click_requested.emit(velocity)
            return

        flux = event.ydata
        if flux is None:
            return

        component = self.get_component_at_velocity(velocity)
        if component is not None:
            self._dragging_component = component

        self.mouse_pressed.emit(
            VelocityPointerEvent(velocity=velocity, flux=flux, component=component)
        )

    def _on_mouse_move(self, event: Event) -> None:
        """Handle matplotlib mouse move event for drag tracking."""
        if not isinstance(event, MouseEvent):
            return
        if self._dragging_component is None or event.inaxes is None:
            return

        velocity = event.xdata
        flux = event.ydata
        if velocity is None or flux is None:
            return

        self._update_drag_overlay(velocity)
        self.mouse_moved.emit(
            VelocityPointerEvent(velocity=velocity, flux=flux, component=self._dragging_component)
        )

    def _update_drag_overlay(self, velocity: float) -> None:
        """Update the drag overlay line position."""
        try:
            self._plot_renderer.update_drag_overlay(velocity)
        except (AttributeError, RuntimeError, ValueError):
            logger.debug("Failed to update drag overlay", exc_info=True)

    def _clear_drag_overlay(self) -> None:
        """Remove the drag overlay line."""
        self._plot_renderer.clear_drag_overlay()

    def set_linked_drag_overlay(self, velocity: float | None) -> None:
        """Show or clear a drag overlay driven by a tied component in another subplot."""
        if velocity is None:
            self._clear_drag_overlay()
            return
        self._update_drag_overlay(velocity)

    def has_drag_overlay(self) -> bool:
        """Return whether a drag overlay is currently visible on this subplot."""
        return self._plot_renderer.has_drag_overlay()

    def cancel_active_drag(self) -> bool:
        """Cancel any in-progress drag interaction on this subplot."""
        had_drag = self._dragging_component is not None or self._plot_renderer.has_drag_overlay()
        self._dragging_component = None
        self._clear_drag_overlay()
        return had_drag

    def _on_mouse_release(self, event: Event) -> None:
        """Handle matplotlib mouse release event for drag completion."""
        if not isinstance(event, MouseEvent):
            return
        if event.button != 1 or self._dragging_component is None:
            return

        velocity = event.xdata
        flux = event.ydata
        self._clear_drag_overlay()

        if velocity is None or flux is None:
            self._dragging_component = None
            return

        component = self._dragging_component
        self._dragging_component = None
        self.mouse_released.emit(
            VelocityPointerEvent(velocity=velocity, flux=flux, component=component)
        )
