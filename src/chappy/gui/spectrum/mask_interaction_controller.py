"""Mask interaction controller for the shared spectrum surface."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable

    from chappy.gui.protocols.optimize_spectrum import SpectrumModeIntegrationPort
    from chappy.presentation.interaction.interaction_contracts import (
        InteractionStateSnapshot,
        MaskSelectionContext,
        MaskSelectionRequest,
    )

logger = logging.getLogger(__name__)


class MaskSelectionInteractorPort(Protocol):
    """Interactor operations required for mask selection."""

    def begin_mask_selection_interaction(self, request: MaskSelectionRequest) -> bool:
        """Prime mask selection using a typed request."""
        ...

    def cancel_mask_selection_interaction(self, *, reason: str | None = None) -> bool:
        """Cancel an active mask selection interaction."""
        ...


class MaskOverlayPlotPort(Protocol):
    """Plot operations required for mask overlay coordination."""

    def highlight_mask(self, mask_id: str | None) -> None:
        """Highlight or clear the active mask overlay."""
        ...

    def set_active_mask_group(self, group_id: str | None) -> None:
        """Set the active mask group shown on the plot."""
        ...


class SpectrumMaskInteractionController:
    """Coordinate mask interaction requests between optimize mode and spectrum."""

    def __init__(
        self,
        *,
        interactor_provider: Callable[[], MaskSelectionInteractorPort | None],
        plot_host_provider: Callable[[], MaskOverlayPlotPort | None],
        integration_provider: Callable[[], SpectrumModeIntegrationPort | None],
        snapshot_callback: Callable[[InteractionStateSnapshot[MaskSelectionContext]], None],
    ) -> None:
        """Initialize the mask interaction controller.

        Args:
            interactor_provider: Provider for the active spectrum interactor.
            plot_host_provider: Provider for the active plot host.
            integration_provider: Provider for optimize integration.
            snapshot_callback: Callback for observer notification.
        """
        self._interactor_provider = interactor_provider
        self._plot_host_provider = plot_host_provider
        self._integration_provider = integration_provider
        self._snapshot_callback = snapshot_callback

    def request_mask_selection_interaction(self, request: MaskSelectionRequest) -> bool:
        """Route a mask selection request to the spectrum interactor."""
        interactor = self._interactor_provider()
        if interactor is None:
            msg = "Mask selection interactor is required."
            raise RuntimeError(msg)

        return bool(interactor.begin_mask_selection_interaction(request))

    def highlight_mask(self, mask_id: str | None) -> None:
        """Highlight a mask overlay on the spectrum plot."""
        plot_host = self._plot_host_provider()
        if plot_host is None:
            msg = "Mask overlay plot host is required."
            raise RuntimeError(msg)

        plot_host.highlight_mask(mask_id)

    def cancel_mask_selection(self) -> None:
        """Cancel any active mask selection on the spectrum interactor."""
        interactor = self._interactor_provider()
        if interactor is None:
            msg = "Mask selection interactor is required."
            raise RuntimeError(msg)

        interactor.cancel_mask_selection_interaction(reason=None)

    def set_active_mask_group(self, group_id: str | None) -> None:
        """Update the mask group emphasized in the plot."""
        plot_host = self._plot_host_provider()
        if plot_host is None:
            msg = "Mask overlay plot host is required."
            raise RuntimeError(msg)

        plot_host.set_active_mask_group(group_id)

    def apply_snapshot(self, snapshot: InteractionStateSnapshot[MaskSelectionContext]) -> None:
        """Forward a mask selection snapshot to observers and optimize integration."""
        self._log_snapshot(snapshot)
        self._snapshot_callback(snapshot)

        integration = self._integration_provider()
        if integration is not None:
            integration.handle_mask_selection_snapshot(snapshot)

    def _log_snapshot(self, snapshot: InteractionStateSnapshot[MaskSelectionContext]) -> None:
        """Emit structured debug logs for mask selection snapshots."""
        context = snapshot.context
        payload: dict[
            str,
            str | float | tuple[float, float] | dict[str, str | tuple[float, float] | None] | None,
        ] = {"phase": snapshot.phase.value, "interaction_id": snapshot.interaction_id}

        if context is not None:
            payload["mode"] = context.selection_mode
            payload["mask_id"] = context.mask_id
            payload["group_id"] = context.group_id
            payload["start"] = context.start_pos
            payload["current"] = context.current_pos
            payload["end"] = context.end_pos
            payload["cancel_reason"] = context.cancel_reason

            result_mask = context.result_mask
            if result_mask is not None:
                payload["result_mask"] = {
                    "identifier": result_mask.identifier,
                    "range": (result_mask.wavelength_min, result_mask.wavelength_max),
                    "group_id": result_mask.group_id,
                }

        logger.debug("Mask selection snapshot", extra=payload)
