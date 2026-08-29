"""Protocol boundary for mode state coordination."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from PySide6.QtCore import SignalInstance

    from chappy.core.editing_mode import EditingMode


class ModeStateStorePort(Protocol):
    """Mode state surface required by shared spectrum components."""

    @property
    def current_mode(self) -> EditingMode:
        """Return the currently active editing mode."""
        ...

    @property
    def mode_changed(self) -> SignalInstance:
        """Return the mode changed signal."""
        ...
