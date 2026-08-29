"""GUI adapter for optimize mask panel rendering."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chappy.core.masking import MaskDefinition
    from chappy.gui.modes.analysis.region_detail.mask.mask_panel import OptimizeMaskPanel


class OptimizeMaskPanelAdapter:
    """Keep optimize mask panel updates out of the panel workflow body."""

    def __init__(self, mask_panel: OptimizeMaskPanel) -> None:
        """Initialize the adapter.

        Args:
            mask_panel: Optimize mask panel to update.
        """
        self._mask_panel = mask_panel

    def set_available(self, available: bool) -> None:
        """Apply whether mask editing is available.

        Args:
            available: Whether absorption regions are available.
        """
        self._mask_panel.setEnabled(available)
        self._mask_panel.set_add_button_enabled(available)
        if not available:
            self._mask_panel.set_masks([])

    def show_current_region_masks(
        self, masks: list[MaskDefinition], active_mask_id: str | None
    ) -> None:
        """Show masks owned by the region currently focused in Analysis Detail.

        Args:
            masks: Mask definitions to show.
            active_mask_id: Active mask ID, if any.
        """
        self._mask_panel.set_masks(masks)
        self._mask_panel.select_mask(active_mask_id)
