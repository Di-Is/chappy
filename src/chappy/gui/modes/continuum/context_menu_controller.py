"""Continuum-mode context menu action provider."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject

from chappy.gui.protocols.context_menu import ContextMenuActionDescriptor, ContextMenuTriggerAction
from chappy.gui.protocols.intent_types import AddContinuumPointIntent, DeleteContinuumPointIntent


@dataclass(frozen=True, slots=True)
class ContinuumContextMenuRequest:
    """State required to build continuum context menu actions."""

    wavelength: float
    flux: float | None
    can_add: bool
    can_delete: bool
    nearest_index: int | None


class ContinuumContextMenuController(QObject):
    """Build continuum-mode context menu action descriptors."""

    def actions_for_request(
        self, request: ContinuumContextMenuRequest
    ) -> tuple[ContextMenuActionDescriptor, ...]:
        """Build typed context menu action descriptors.

        Args:
            request: Continuum context menu request state.

        Returns:
            Context menu descriptors consumed by the spectrum surface.
        """
        add_enabled = request.can_add and request.flux is not None
        delete_enabled = request.can_delete and request.nearest_index is not None
        return (
            ContextMenuTriggerAction(
                label=self.tr("Add Control Point"),
                enabled=add_enabled,
                intent=(
                    AddContinuumPointIntent(wavelength=request.wavelength, flux=request.flux)
                    if add_enabled and request.flux is not None
                    else None
                ),
            ),
            ContextMenuTriggerAction(
                label=self.tr("Delete Control Point"),
                enabled=delete_enabled,
                intent=(
                    DeleteContinuumPointIntent(index=request.nearest_index)
                    if delete_enabled and request.nearest_index is not None
                    else None
                ),
            ),
        )
