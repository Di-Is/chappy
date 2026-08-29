"""Route shell mode lifecycle ownership to mode-local lifecycle objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from chappy.core.editing_mode import EditingMode
from chappy.gui.modes.common import ModeLifecycle, ModeRefreshRequest

if TYPE_CHECKING:
    from collections.abc import Mapping

    from chappy.core.spectroscopy_project import SpectroscopyProject


@dataclass
class ModeLifecycleRouter:
    """Own lifecycle activation and refresh dispatch for shell modes."""

    lifecycles: Mapping[EditingMode, ModeLifecycle]
    active_mode: EditingMode | None = None

    def lifecycle_for_mode(self, mode: EditingMode) -> ModeLifecycle:
        """Return the registered lifecycle for a mode."""
        lifecycle = self.lifecycles.get(mode)
        if lifecycle is None:
            msg = f"No lifecycle registered for mode: {mode.value}"
            raise RuntimeError(msg)
        return lifecycle

    def set_project(self, project: SpectroscopyProject | None) -> None:
        """Propagate the active project to every lifecycle."""
        for lifecycle in self.lifecycles.values():
            lifecycle.set_project(project)

    def sync_mode(self, mode: EditingMode, *, reason: str) -> None:
        """Activate or refresh the lifecycle for the requested mode."""
        if mode is EditingMode.START:
            self._deactivate_active_mode()
            return

        if self.active_mode == mode:
            self.lifecycle_for_mode(mode).refresh(ModeRefreshRequest(mode=mode, reason=reason))
            return

        self._deactivate_active_mode()
        lifecycle = self.lifecycle_for_mode(mode)
        lifecycle.activate()
        lifecycle.refresh(ModeRefreshRequest(mode=mode, reason=reason))
        self.active_mode = mode

    def refresh_line_overlays(self, mode: EditingMode) -> None:
        """Refresh line overlays through the lifecycle owner for a mode."""
        if mode is EditingMode.START:
            return
        self.lifecycle_for_mode(mode).refresh(
            ModeRefreshRequest(mode=mode, reason="line-overlays-refreshed")
        )

    def _deactivate_active_mode(self) -> None:
        """Deactivate the currently active lifecycle, if any."""
        if self.active_mode is None:
            return
        self.lifecycle_for_mode(self.active_mode).deactivate()
        self.active_mode = None


__all__ = ["ModeLifecycleRouter"]
