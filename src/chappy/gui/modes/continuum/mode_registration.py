"""Mode panel registration for continuum mode."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from chappy.core.editing_mode import EditingMode
from chappy.gui.modes.common.contracts import ModePanelRegistration, ModePanelWidget

if TYPE_CHECKING:
    from chappy.gui.modes.common.lifecycle import ModeLifecycle


@dataclass(frozen=True, slots=True)
class ContinuumModePanelEntry:
    """Continuum mode panel registration builder."""

    panel: ModePanelWidget
    lifecycle: ModeLifecycle

    def to_registration(self) -> ModePanelRegistration:
        """Build a mode panel registration.

        Returns:
            Continuum mode panel registration.
        """
        return ModePanelRegistration(
            mode=EditingMode.CONTINUUM, panel=self.panel, lifecycle=self.lifecycle
        )
