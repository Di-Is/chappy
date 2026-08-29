"""Identify mode composition helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chappy.gui.modes.identify.mode_registration import IdentifyModePanelEntry

if TYPE_CHECKING:
    from chappy.gui.modes.common.contracts import ModePanelRegistration, ModePanelWidget
    from chappy.gui.modes.common.lifecycle import ModeLifecycle


def create_identify_registration(
    panel: ModePanelWidget, lifecycle: ModeLifecycle
) -> ModePanelRegistration:
    """Create an identify mode panel registration.

    Args:
        panel: Panel widget for identify mode.
        lifecycle: Required lifecycle controller.

    Returns:
        Identify mode registration.
    """
    return IdentifyModePanelEntry(panel=panel, lifecycle=lifecycle).to_registration()
