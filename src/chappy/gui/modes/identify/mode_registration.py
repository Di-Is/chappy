"""Mode panel registration for identify mode."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from chappy.core.editing_mode import EditingMode
from chappy.gui.modes.common.contracts import ModePanelRegistration, ModePanelWidget

if TYPE_CHECKING:
    from chappy.gui.modes.common.lifecycle import ModeLifecycle


@dataclass(frozen=True, slots=True)
class IdentifyModePanelEntry:
    """Identify mode panel registration builder."""

    panel: ModePanelWidget
    lifecycle: ModeLifecycle

    def to_registration(self) -> ModePanelRegistration:
        """Build a mode panel registration.

        Returns:
            Identify mode panel registration.
        """
        return ModePanelRegistration(
            mode=EditingMode.IDENTIFY, panel=self.panel, lifecycle=self.lifecycle
        )
