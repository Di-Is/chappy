"""Editing mode management for Chappy.

This module provides the infrastructure for switching between different editing modes:
- Start mode: Application launch state guiding users to load data
- Identify mode: Map detected features to absorption lines and velocity windows
- Analysis mode: Review regions, edit structure, and refine absorber models
- Continuum editing mode: Focus on continuum fitting and adjustment
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from chappy.core.change_set import ChangeSet
from chappy.core.event_dispatcher import DomainEventDispatcher
from chappy.core.events import (
    DomainEvent,
    FittingGroupAdded,
    FittingGroupModified,
    FittingGroupRemoved,
    ModeChanged,
)

if TYPE_CHECKING:
    from chappy.core.spectroscopy_project import SpectroscopyProject


@dataclass(slots=True)
class FittingGroupSummary:
    """Lightweight snapshot describing a fitting group."""

    name: str
    wavelength_min: float | None
    wavelength_max: float | None
    system_ids: tuple[str, ...] = ()
    absorber_names: tuple[str, ...] = ()
    group_id: str | None = None
    color: str | None = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> FittingGroupSummary:
        """Build a summary instance from a mapping payload."""

        def _as_optional_float(value: object | None) -> float | None:
            if isinstance(value, int | float):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value)
                except ValueError:
                    return None
            return None

        def _as_tuple_of_str(value: object) -> tuple[str, ...]:
            if isinstance(value, str):
                return (value,)
            if isinstance(value, Sequence):
                return tuple(str(item) for item in value if isinstance(item, str))
            return ()

        name = str(payload.get("name", ""))
        group_id_raw = payload.get("group_id")
        color_raw = payload.get("color")

        # Accept both legacy key "system_ids" and new key "line_ids"
        sys_ids = payload.get("line_ids")
        if not sys_ids:
            sys_ids = payload.get("system_ids")

        return cls(
            name=name,
            wavelength_min=_as_optional_float(payload.get("wavelength_min")),
            wavelength_max=_as_optional_float(payload.get("wavelength_max")),
            system_ids=_as_tuple_of_str(sys_ids),
            absorber_names=_as_tuple_of_str(payload.get("absorber_names")),
            group_id=str(group_id_raw) if isinstance(group_id_raw, str) else None,
            color=str(color_raw) if isinstance(color_raw, str) else None,
        )

    def as_range(self) -> tuple[float, float] | None:
        """Return the wavelength range when both bounds are available."""
        if self.wavelength_min is None or self.wavelength_max is None:
            return None
        if self.wavelength_min >= self.wavelength_max:
            return None
        return (float(self.wavelength_min), float(self.wavelength_max))

    @property
    def line_ids(self) -> tuple[str, ...]:
        """Alias to renamed field after terminology update.

        Returns:
            Tuple of absorption line identifiers in this fitting group.
        """
        return self.system_ids


FittingGroupPayload = Mapping[str, str | float | Sequence[str] | None]
FittingGroupCollection = Mapping[str, FittingGroupSummary | FittingGroupPayload]


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
    """Manages editing modes and their state.

    This class handles switching between different editing modes and maintains
    mode-specific state such as active fitting range groups.

    Mode changes are emitted as typed events through ``events``.
    """

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
        self._fitting_groups: dict[str, FittingGroupSummary] = {}

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
        if project:
            # Load any project-specific fitting groups
            self._load_project_groups()
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

    def _load_project_groups(self) -> None:
        """Load fitting groups from project data."""
        if not self.project:
            return

        # Groups will be loaded from project XML when that feature is implemented
        # For now, just clear existing groups
        self._fitting_groups.clear()
        logger.debug("Loaded project fitting groups")

    @property
    def fitting_groups(self) -> Mapping[str, FittingGroupSummary]:
        """Return registered fitting groups keyed by name."""
        return self._fitting_groups

    def get_fitting_group(self, name: str) -> FittingGroupSummary | None:
        """Return a fitting group by name if available."""
        return self._fitting_groups.get(name)

    def set_fitting_groups(self, groups: FittingGroupCollection) -> ChangeSet:
        """Replace registered fitting groups and return emitted changes.

        Args:
            groups: Fitting group summaries keyed by group name.

        Returns:
            Domain changes describing added, removed, and modified groups.
        """
        normalised = self._normalise_fitting_groups(groups)
        previous = self._fitting_groups
        events: list[DomainEvent] = [
            FittingGroupRemoved(group_name=group_name)
            for group_name in previous
            if group_name not in normalised
        ]

        for group_name, group in normalised.items():
            old_group = previous.get(group_name)
            if old_group is None:
                events.append(FittingGroupAdded(group_name=group_name))
            elif old_group != group:
                events.append(FittingGroupModified(group_name=group_name))

        self._fitting_groups = normalised
        change_set = ChangeSet.of(*events)
        self.events.dispatch(change_set)
        return change_set

    def _normalise_fitting_groups(
        self, groups: FittingGroupCollection
    ) -> dict[str, FittingGroupSummary]:
        """Return supported fitting group payloads as summaries.

        Args:
            groups: Fitting group summaries keyed by group name.

        Returns:
            Normalized fitting group summaries keyed by group name.
        """
        normalised: dict[str, FittingGroupSummary] = {}
        for name, value in groups.items():
            if isinstance(value, FittingGroupSummary):
                normalised[name] = value
            elif isinstance(value, Mapping):
                normalised[name] = FittingGroupSummary.from_mapping(value)
            else:
                logger.debug("Ignoring unsupported fitting group payload for '%s'", name)
        return normalised
