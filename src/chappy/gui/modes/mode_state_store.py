"""Qt-backed editing mode state store."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QSettings, Signal

from chappy.core.editing_mode import (
    EditingMode,
    EditingModeState,
    FittingGroupCollection,
    FittingGroupSummary,
)
from chappy.core.events import FittingGroupRemoved, ModeChanged

if TYPE_CHECKING:
    from collections.abc import Mapping

    from chappy.core.change_set import ChangeSet
    from chappy.core.spectroscopy_project import SpectroscopyProject


logger = logging.getLogger(__name__)


class ModeStateStore(QObject):
    """Expose core editing mode state as Qt signals."""

    mode_changed = Signal(EditingMode)
    group_removed = Signal(str)

    def __init__(
        self, project: SpectroscopyProject | None = None, parent: QObject | None = None
    ) -> None:
        """Initialize mode state store.

        Args:
            project: Associated project.
            parent: Optional Qt parent object.
        """
        super().__init__(parent)
        self._settings = QSettings("Chappy", "Chappy")
        self._core = EditingModeState(
            project=project,
            initial_mode=self._restore_mode_value("editing_mode/current"),
            previous_mode=self._restore_mode_value("editing_mode/previous"),
        )
        self._core.events.subscribe(self._apply_core_events)

    @property
    def current_mode(self) -> EditingMode:
        """Get current editing mode."""
        return self._core.current_mode

    @property
    def previous_mode(self) -> EditingMode:
        """Get previous editing mode."""
        return self._core.previous_mode

    @property
    def fitting_groups(self) -> Mapping[str, FittingGroupSummary]:
        """Return registered fitting groups keyed by name."""
        return self._core.fitting_groups

    @property
    def project(self) -> SpectroscopyProject | None:
        """Return associated project."""
        return self._core.project

    def set_project(self, project: SpectroscopyProject | None) -> None:
        """Set the associated project."""
        self._core.set_project(project)

    def switch_mode(self, mode: EditingMode) -> ChangeSet:
        """Switch to a different editing mode."""
        return self._core.switch_mode(mode)

    def get_fitting_group(self, name: str) -> FittingGroupSummary | None:
        """Return a fitting group by name if available."""
        return self._core.get_fitting_group(name)

    def set_fitting_groups(self, groups: FittingGroupCollection) -> ChangeSet:
        """Replace registered fitting groups.

        Args:
            groups: Fitting group summaries keyed by group name.

        Returns:
            Domain changes emitted by the core mode state store.
        """
        return self._core.set_fitting_groups(groups)

    def _restore_mode_value(self, key: str) -> EditingMode:
        """Restore a mode value from settings.

        Settings are external boundary data; unknown values (e.g. mode names
        from older releases such as "browse") degrade to START instead of
        failing startup.
        """
        raw_value = self._settings.value(key, EditingMode.START.value)
        if isinstance(raw_value, EditingMode):
            return raw_value
        if isinstance(raw_value, str):
            if raw_value in {"optimize", "organize"}:
                return EditingMode.ANALYSIS
            try:
                return EditingMode(raw_value)
            except ValueError:
                logger.warning("Discarding unknown stored editing mode for %r: %r", key, raw_value)
                return EditingMode.START
        return EditingMode.START

    def _save_mode_state(self) -> None:
        """Save current mode state to settings."""
        self._settings.setValue("editing_mode/current", self.current_mode.value)
        self._settings.setValue("editing_mode/previous", self.previous_mode.value)

    def _apply_core_events(self, change_set: ChangeSet) -> None:
        """Emit Qt signals for core mode events.

        Args:
            change_set: Domain changes emitted by the core layer.
        """
        for event in change_set:
            if isinstance(event, ModeChanged):
                self._save_mode_state()
                self.mode_changed.emit(EditingMode(event.mode))
                continue
            if isinstance(event, FittingGroupRemoved):
                self.group_removed.emit(event.group_name)
                continue
