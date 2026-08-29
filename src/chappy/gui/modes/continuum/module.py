"""Continuum mode composition helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chappy.gui.modes.continuum.mode_registration import ContinuumModePanelEntry

if TYPE_CHECKING:
    from chappy.gui.modes.common.contracts import ModePanelRegistration, ModePanelWidget
    from chappy.gui.modes.common.lifecycle import ModeLifecycle


def create_continuum_registration(
    panel: ModePanelWidget, lifecycle: ModeLifecycle
) -> ModePanelRegistration:
    """Create a continuum mode panel registration.

    Args:
        panel: Panel widget for continuum mode.
        lifecycle: Required lifecycle controller.

    Returns:
        Continuum mode registration.
    """
    return ContinuumModePanelEntry(panel=panel, lifecycle=lifecycle).to_registration()
