"""Qt-independent contracts for mode module boundaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from chappy.core.editing_mode import EditingMode
    from chappy.gui.modes.common.lifecycle import ModeLifecycle


class ModePanelWidget(Protocol):
    """Minimal QWidget-like surface needed by the mode panel host."""

    def setObjectName(self, name: str) -> None:  # noqa: N802
        """Set the object name used by Qt styles and tests.

        Args:
            name: Object name to assign.
        """


@dataclass(frozen=True, slots=True)
class ModePanelRegistration:
    """Registration entry for a mode panel and required lifecycle."""

    mode: EditingMode
    panel: ModePanelWidget
    lifecycle: ModeLifecycle


class ModePanelHost(Protocol):
    """Host capable of registering mode panel entries."""

    def register_panel_entry(self, registration: ModePanelRegistration) -> None:
        """Register a mode panel entry.

        Args:
            registration: Mode panel entry to register.
        """


@dataclass(slots=True)
class ModePanelRegistry:
    """Collect mode panel registrations before mounting them into the host."""

    _entries: list[ModePanelRegistration] = field(default_factory=list)

    def register(self, registration: ModePanelRegistration) -> None:
        """Add a registration entry.

        Args:
            registration: Mode panel entry to store.
        """
        self._entries.append(registration)

    def entries(self) -> tuple[ModePanelRegistration, ...]:
        """Return registered entries in insertion order.

        Returns:
            Immutable registration snapshot.
        """
        return tuple(self._entries)

    def install_into(self, host: ModePanelHost) -> None:
        """Install all registration entries into a host.

        Args:
            host: Target panel host.
        """
        for registration in self._entries:
            host.register_panel_entry(registration)
