"""Editing mode management for Chappy.

This module provides the infrastructure for switching between different editing modes:
- Start mode: Application launch state guiding users to load data
- Identify mode: Map detected features to absorption lines and velocity windows
- Analysis mode: Review regions, edit structure, and refine absorber models
- Continuum editing mode: Focus on continuum fitting and adjustment
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import TYPE_CHECKING

from chappy.core.change_set import ChangeSet
from chappy.core.event_dispatcher import DomainEventDispatcher
from chappy.core.events import ModeChanged

if TYPE_CHECKING:
    from chappy.core.spectroscopy_project import SpectroscopyProject


logger = logging.getLogger(__name__)


class EditingMode(Enum):
    """Enumeration for different editing modes."""

    START = "start"
    IDENTIFY = "identify"
    ANALYSIS = "analysis"
    CONTINUUM = "continuum"


# Canonical workflow order for mode-switching UI (buttons, menus, tutorials,
# manual). Start is excluded because it has no mode-switch button.
MODE_WORKFLOW_ORDER: tuple[EditingMode, ...] = (
    EditingMode.IDENTIFY,
    EditingMode.ANALYSIS,
    EditingMode.CONTINUUM,
)


class EditingModeState:
    """Manage editing mode transitions and emit typed events."""

    def __init__(
        self,
        project: SpectroscopyProject | None = None,
        initial_mode: EditingMode = EditingMode.START,
        previous_mode: EditingMode = EditingMode.START,
    ) -> None:
        """Initialize editing mode state.

        Args:
            project: Associated project (can be None initially)
            initial_mode: Initial editing mode.
            previous_mode: Previous editing mode.
        """
        self.project = project
        self.events = DomainEventDispatcher()

        # Current mode state
        self._current_mode = initial_mode
        self._previous_mode = previous_mode

        logger.debug("EditingModeState initialized with mode: %s", self._current_mode)

    @property
    def current_mode(self) -> EditingMode:
        """Get current editing mode."""
        return self._current_mode

    def set_project(self, project: SpectroscopyProject | None) -> None:
        """Set the associated project.

        Args:
            project: Project to associate with this state
        """
        self.project = project
        logger.debug("Set project in EditingModeState")

    @property
    def previous_mode(self) -> EditingMode:
        """Get previous editing mode."""
        return self._previous_mode

    def switch_mode(self, mode: EditingMode) -> ChangeSet:
        """Switch to a different editing mode.

        Args:
            mode: Target editing mode
        """
        if mode == self._current_mode:
            return ChangeSet.empty()

        self._previous_mode = self._current_mode
        self._current_mode = mode

        logger.info("Switched editing mode: %s -> %s", self._previous_mode.value, mode.value)
        change_set = ChangeSet.of(ModeChanged(mode=mode.value))
        self.events.dispatch(change_set)
        return change_set
