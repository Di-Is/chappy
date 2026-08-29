"""Optimize-mode context menu action provider."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject

from chappy.gui.protocols.context_menu import (
    ContextMenuActionDescriptor,
    ContextMenuToggleAction,
    ContextMenuTriggerAction,
)
from chappy.gui.protocols.intent_types import (
    AddOptimizeComponentIntent,
    ToggleOptimizeVelocityPlotIntent,
)


@dataclass(frozen=True, slots=True)
class OptimizeContextMenuRequest:
    """State required to build optimize context menu actions."""

    wavelength: float
    can_add_component: bool
    has_selected_line: bool
    has_selected_region: bool
    velocity_plot_visible: bool


class OptimizeContextMenuController(QObject):
    """Build optimize-mode context menu action descriptors."""

    def actions_for_request(
        self, request: OptimizeContextMenuRequest
    ) -> tuple[ContextMenuActionDescriptor, ...]:
        """Build typed context menu action descriptors.

        Args:
            request: Optimize context menu request state.

        Returns:
            Context menu descriptors consumed by the spectrum integration.
        """
        return (
            ContextMenuTriggerAction(
                label=self.tr("Add Component Here"),
                enabled=request.can_add_component,
                tooltip=(
                    self.tr("Out of selected line range")
                    if not request.can_add_component and request.has_selected_line
                    else None
                ),
                intent=(
                    AddOptimizeComponentIntent(wavelength=request.wavelength)
                    if request.can_add_component
                    else None
                ),
            ),
            ContextMenuToggleAction(
                label=self.tr("Show Velocity Plot (V)"),
                enabled=request.has_selected_region,
                checked=request.velocity_plot_visible,
                tooltip=(
                    self.tr("Please select a region") if not request.has_selected_region else None
                ),
                intent_when_checked=ToggleOptimizeVelocityPlotIntent(),
                intent_when_unchecked=ToggleOptimizeVelocityPlotIntent(),
            ),
        )
