"""Small synchronous dispatcher for domain change sets."""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import contextmanager
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from chappy.core.change_set import ChangeSet

DomainChangeListener = Callable[[ChangeSet], None]

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Iterator


class DomainEventDispatcher:
    """Dispatch domain change sets to subscribed listeners."""

    def __init__(self) -> None:
        """Initialize an empty dispatcher."""
        self._listeners: list[DomainChangeListener] = []
        self._suppression_depth = 0

    def __deepcopy__(self, memo: dict[int, Any]) -> DomainEventDispatcher:
        """Copy the dispatcher while detaching observers outside the copied graph.

        Deep copies produce detached domain objects (e.g. the optimizer's
        working model). Listeners bound to objects inside the copied graph are
        rebound to their copies so internal invalidation wiring keeps working,
        while external observers (GUI callbacks, plain functions, builtin
        methods) are dropped so detached mutations never notify live observers.
        """
        copied = DomainEventDispatcher()
        memo[id(self)] = copied
        for listener in self._listeners:
            bound_self = getattr(listener, "__self__", None)
            if bound_self is not None and id(bound_self) in memo:
                copied._listeners.append(deepcopy(listener, memo))
        return copied

    def subscribe(self, listener: DomainChangeListener) -> None:
        """Subscribe a listener if it is not already registered."""
        if listener not in self._listeners:
            self._listeners.append(listener)

    def unsubscribe(self, listener: DomainChangeListener) -> None:
        """Unsubscribe a listener if it is registered."""
        try:
            self._listeners.remove(listener)
        except ValueError:
            return

    def dispatch(self, change_set: ChangeSet) -> None:
        """Dispatch a change set to all listeners."""
        if not change_set or self._suppression_depth:
            return
        for listener in tuple(self._listeners):
            listener(change_set)

    def dispatch_isolated(self, change_set: ChangeSet) -> None:
        """Dispatch a post-commit change set while isolating listener failures."""
        if not change_set or self._suppression_depth:
            return
        for listener in tuple(self._listeners):
            try:
                listener(change_set)
            except Exception:
                logger.exception("Domain listener failed during isolated post-commit dispatch")

    @contextmanager
    def suppress_dispatching(self) -> Iterator[None]:
        """Suppress synchronous listeners while scientific storage is transactional."""
        self._suppression_depth += 1
        try:
            yield
        finally:
            self._suppression_depth -= 1
