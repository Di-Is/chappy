"""Container for typed domain changes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeGuard

from chappy.core.events import DomainEvent

if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass(frozen=True, slots=True)
class ChangeSet:
    """Immutable collection of domain events."""

    events: tuple[DomainEvent, ...] = ()

    @classmethod
    def empty(cls) -> ChangeSet:
        """Return an empty change set."""
        return cls(())

    @classmethod
    def of(cls, *events: DomainEvent) -> ChangeSet:
        """Create a change set from events."""
        return cls(tuple(events))

    def extend(self, *changes: ChangeSet | DomainEvent) -> ChangeSet:
        """Return a new change set with additional events appended."""
        events = list(self.events)
        for change in changes:
            if isinstance(change, ChangeSet):
                events.extend(change.events)
            else:
                events.append(change)
        return ChangeSet(tuple(events))

    def contains[TEvent: DomainEvent](self, event_type: type[TEvent]) -> bool:
        """Return whether this change set includes the requested event type."""
        return any(isinstance(event, event_type) for event in self.events)

    def filter[TEvent: DomainEvent](self, event_type: type[TEvent]) -> tuple[TEvent, ...]:
        """Return events matching the requested type."""
        return tuple(event for event in self.events if _is_event_type(event, event_type))

    def __bool__(self) -> bool:
        """Return whether the change set contains events."""
        return bool(self.events)

    def __iter__(self) -> Iterator[DomainEvent]:
        """Iterate over contained events."""
        return iter(self.events)


def _is_event_type[TEvent: DomainEvent](
    event: DomainEvent, event_type: type[TEvent]
) -> TypeGuard[TEvent]:
    """Return whether an event matches the requested event type."""
    return isinstance(event, event_type)
