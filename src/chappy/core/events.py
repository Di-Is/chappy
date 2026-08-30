"""Typed domain events emitted by core model operations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelInvalidated:
    """Event emitted when a spectrum model cache becomes stale."""


@dataclass(frozen=True, slots=True)
class ModelUpdateProgress:
    """Event emitted while a spectrum model is being recalculated."""

    percent: int
    message: str


@dataclass(frozen=True, slots=True)
class ModelUpdated:
    """Event emitted when a spectrum model has been recalculated."""


@dataclass(frozen=True, slots=True)
class ComponentAdded:
    """Event emitted when a model component is added."""

    component_id: str


@dataclass(frozen=True, slots=True)
class ComponentRemoved:
    """Event emitted when a model component is removed."""

    component_id: str


@dataclass(frozen=True, slots=True)
class ComponentChanged:
    """Event emitted when a model component's state changes."""

    component_id: str


@dataclass(frozen=True, slots=True)
class ComponentEnabledChanged:
    """Event emitted when a component enabled flag changes."""

    component_id: str
    enabled: bool


@dataclass(frozen=True, slots=True)
class MasksChanged:
    """Event emitted when spectrum mask definitions change."""


@dataclass(frozen=True, slots=True)
class ModeChanged:
    """Event emitted when the active editing mode changes."""

    mode: str


@dataclass(frozen=True, slots=True)
class RegionTopologyChanged:
    """Event emitted after one committed absorption-region topology change."""

    created_region_ids: tuple[str, ...] = ()
    removed_region_ids: tuple[str, ...] = ()
    impacted_surviving_region_ids: tuple[str, ...] = ()
    changed_surviving_line_ids: tuple[str, ...] = ()


type DomainEvent = (
    ModelInvalidated
    | ModelUpdateProgress
    | ModelUpdated
    | ComponentAdded
    | ComponentRemoved
    | ComponentChanged
    | ComponentEnabledChanged
    | MasksChanged
    | ModeChanged
    | RegionTopologyChanged
)
