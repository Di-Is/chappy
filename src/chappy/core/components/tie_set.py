"""Parameter tie set management for parameter synchronization."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal, cast
from uuid import uuid4

from chappy.core.change_set import ChangeSet
from chappy.core.event_dispatcher import DomainEventDispatcher
from chappy.core.events import ComponentAdded, ComponentChanged

from .base import Parameter

if TYPE_CHECKING:
    from .absorber import AbsorberComponent

logger = logging.getLogger(__name__)

TieParameterName = Literal["redshift", "column_density", "b_parameter", "covering_factor"]

FULL_TIE_MASK: frozenset[TieParameterName] = frozenset(
    {"redshift", "column_density", "b_parameter", "covering_factor"}
)


def _default_parameter(name: TieParameterName) -> Parameter:
    """Create a master parameter with the standard bounds for one tie name."""
    if name == "redshift":
        return Parameter("redshift", 0.0, min_val=-0.1, max_val=10.0, unit="")
    if name == "column_density":
        return Parameter("column_density", 14.0, min_val=10.0, max_val=22.0, unit="log(cm⁻²)")
    if name == "b_parameter":
        return Parameter("b_parameter", 10.0, min_val=1.0, max_val=1000.0, unit="km/s")
    return Parameter("covering_factor", 1.0, min_val=0.0, max_val=1.0, fixed=True, unit="")


class ParameterTieSet:
    """Binds a set of absorber components to shared master parameters.

    A tie set ensures that member components share the same ``Parameter``
    objects for every name in ``mask``, so an edit to one member is
    reflected on all others. The mask determines which of the four fittable
    parameters (redshift, column_density, b_parameter, covering_factor) are
    shared; unmasked parameters remain individual to each component.

    Tie set changes are emitted as typed domain events through ``events``.
    """

    def __init__(
        self,
        tie_id: str,
        *,
        uid: str | None = None,
        name: str = "",
        mask: frozenset[TieParameterName] = FULL_TIE_MASK,
        origin: Literal["multiplet", "user"] = "multiplet",
    ) -> None:
        """Initialize a parameter tie set.

        Args:
            tie_id: Display/grouping identifier (e.g., "CIV_doublet"); not unique.
            uid: Immutable unique object identifier. Generated when omitted.
            name: Human-readable name for the tie set
            mask: Parameter names shared across member components
            origin: Whether the tie set is auto-managed ("multiplet") or
                user-edited ("user")
        """
        self.tie_id = tie_id
        self.uid = uid or uuid4().hex
        self.name = name or f"Tie_{tie_id}"
        self.mask = mask
        self.origin = origin
        self.components: list[AbsorberComponent] = []
        self.parent_tie: ParameterTieSet | None = None
        self.member_uids: set[str] = set()
        self.events = DomainEventDispatcher()

        # Master parameters shared by all components, one per masked name
        self.shared_parameters: dict[TieParameterName, Parameter] = {
            param_name: _default_parameter(param_name) for param_name in mask
        }

        logger.info("Created parameter tie set: %s (%s)", self.name, self.tie_id)

    def add_component(self, component: AbsorberComponent) -> ChangeSet:
        """Add component to the tie set.

        Args:
            component: Absorber component to add
        """
        if component in self.components:
            msg = f"Component '{component.name}' is already in tie set '{self.name}'"
            raise ValueError(msg)

        original_parameters = {
            param_name: component.parameters[param_name] for param_name in self.mask
        }

        # If this is the first component, use its scientific state as the master.
        if not self.components:
            for param_name, parameter in original_parameters.items():
                master = self.shared_parameters[param_name]
                master.set_value(parameter.value)
                master.fixed = parameter.fixed

        # Bind component parameters to master parameters
        self._bind_component_parameters(component)

        # Add to components list
        self.components.append(component)

        # Set back-reference to this tie set in the component
        component.tie_set = self

        logger.info("Added component %s to tie set %s", component.name, self.name)
        change_set = ChangeSet.of(ComponentAdded(component_id=component.id))
        self.events.dispatch(change_set)
        return change_set

    def _bind_component_parameters(self, component: AbsorberComponent) -> None:
        """Replace component's masked parameters with tie set masters.

        Args:
            component: Component to bind parameters for
        """
        for param_name in self.shared_parameters:
            # Replace component's parameter with reference to master parameter
            component.parameters[param_name] = self.shared_parameters[param_name]

        logger.debug("Bound parameters for component %s", component.name)

    def attach_tie_set(self, inner: ParameterTieSet) -> ChangeSet:
        """Attach another tie set as one nested participation unit.

        The inner components keep their direct ``component.tie_set`` reference.
        Only masked parameter object bindings and this tie set's flat component
        list are synchronized.
        """
        self._validate_attach_target(inner)

        for param_name in self.mask:
            master = self.shared_parameters[param_name]
            inner.shared_parameters[param_name] = master
            for component in inner.components:
                component.parameters[param_name] = master
                if component not in self.components:
                    self.components.append(component)

        inner.parent_tie = self
        self.member_uids.add(inner.uid)

        change_set = _component_changes(inner.components)
        self._dispatch_component_changes(change_set)
        self.events.dispatch(change_set)
        return change_set

    def _validate_attach_target(self, inner: ParameterTieSet) -> None:
        """Validate that ``inner`` can be attached to this tie set."""
        if inner is self:
            msg = "A tie set cannot attach itself"
            raise ValueError(msg)
        if self.parent_tie is not None:
            msg = f"Tie set '{self.name}' is already nested and cannot be a parent"
            raise ValueError(msg)
        if inner.parent_tie is not None:
            msg = f"Tie set '{inner.name}' is already attached to another tie set"
            raise ValueError(msg)
        if inner.member_uids:
            msg = f"Tie set '{inner.name}' is a parent and cannot be nested"
            raise ValueError(msg)
        missing = self.mask.difference(inner.mask)
        if missing:
            missing_names = ", ".join(sorted(missing))
            msg = f"Tie set '{inner.name}' does not share required parameters: {missing_names}"
            raise ValueError(msg)

    def detach_tie_set(self, inner: ParameterTieSet) -> ChangeSet:
        """Detach a nested tie set and recreate its masked masters.

        New inner masters copy the external master's current value and fixed
        flag. Their error is reset to zero, matching regular unbind behavior.
        """
        if inner.parent_tie is not self:
            msg = f"Tie set '{inner.name}' is not attached to '{self.name}'"
            raise ValueError(msg)

        for param_name in self.mask:
            external_master = self.shared_parameters[param_name]
            inner_master = Parameter(
                param_name,
                external_master.value,
                min_val=external_master.min_val,
                max_val=external_master.max_val,
                fixed=external_master.fixed,
                error=0.0,
                unit=external_master.unit,
            )
            inner.shared_parameters[param_name] = inner_master
            for component in inner.components:
                component.parameters[param_name] = inner_master
                if component in self.components:
                    self.components.remove(component)

        inner.parent_tie = None
        self.member_uids.discard(inner.uid)

        change_set = _component_changes(inner.components)
        self._dispatch_component_changes(change_set)
        self.events.dispatch(change_set)
        return change_set

    def remove_component(self, component: AbsorberComponent) -> ChangeSet:
        """Remove component from the tie set, unbinding its shared parameters.

        The component receives a fresh ``Parameter`` per masked name, copying
        the master's current value and ``fixed`` flag. ``error`` is reset to
        0.0 since the shared-tie error does not describe the individual
        component. Callers are responsible for dissolving the tie set when
        only one component remains.

        Args:
            component: Absorber component to remove

        Returns:
            Change set describing the component change
        """
        for param_name, master in self.shared_parameters.items():
            component.parameters[param_name] = Parameter(
                param_name,
                master.value,
                min_val=master.min_val,
                max_val=master.max_val,
                fixed=master.fixed,
                error=0.0,
                unit=master.unit,
            )

        component.tie_set = None
        if component in self.components:
            self.components.remove(component)
        if self.parent_tie is not None:
            self.parent_tie._remove_nested_component(component)

        logger.info("Removed component %s from tie set %s", component.name, self.name)
        change_set = ChangeSet.of(ComponentChanged(component_id=component.id))
        self.events.dispatch(change_set)
        return change_set

    def _remove_nested_component(self, component: AbsorberComponent) -> None:
        """Remove one nested component from this tie set's flat member list."""
        if component in self.components:
            self.components.remove(component)

    def set_shared_parameter(self, name: str, value: float) -> ChangeSet:
        """Set value of a shared parameter.

        Args:
            name: Parameter name
            value: New value

        Raises:
            KeyError: If parameter name is not shared
            ValueError: If value is outside parameter bounds
        """
        if self.parent_tie is not None and name in self.parent_tie.mask:
            return self.parent_tie.set_shared_parameter(name, value)

        if name not in self.shared_parameters:
            msg = f"Parameter '{name}' is not a shared parameter"
            raise KeyError(msg)
        tie_name = cast("TieParameterName", name)

        # Set the master parameter value
        self.shared_parameters[tie_name].set_value(value)

        logger.debug("Set shared parameter %s = %f for tie set %s", name, value, self.name)
        change_set = ChangeSet.of(
            *(ComponentChanged(component_id=component.id) for component in self.components)
        )
        for component in self.components:
            component.events.dispatch(ChangeSet.of(ComponentChanged(component_id=component.id)))
        self.events.dispatch(change_set)
        return change_set

    def fix_parameter(self, name: str, *, fixed: bool = True) -> ChangeSet:
        """Fix or unfix a shared parameter.

        Args:
            name: Parameter name
            fixed: Whether to fix parameter

        Raises:
            KeyError: If parameter name is not shared
        """
        if self.parent_tie is not None and name in self.parent_tie.mask:
            return self.parent_tie.fix_parameter(name, fixed=fixed)

        if name not in self.shared_parameters:
            msg = f"Parameter '{name}' is not a shared parameter"
            raise KeyError(msg)
        tie_name = cast("TieParameterName", name)

        self.shared_parameters[tie_name].fixed = fixed

        logger.debug("Set parameter %s fixed=%s for tie set %s", name, fixed, self.name)
        change_set = ChangeSet.of(
            *(ComponentChanged(component_id=component.id) for component in self.components)
        )
        for component in self.components:
            component.events.dispatch(ChangeSet.of(ComponentChanged(component_id=component.id)))
        self.events.dispatch(change_set)
        return change_set

    def direct_participation_count(self) -> int:
        """Return direct component participation units in this tie set."""
        return sum(1 for component in self.components if component.tie_set is self)

    def participation_unit_count(self) -> int:
        """Return direct components plus nested tie sets as participation units."""
        return self.direct_participation_count() + len(self.member_uids)

    def _dispatch_component_changes(self, change_set: ChangeSet) -> None:
        """Dispatch component changes to every affected component."""
        for event in change_set.filter(ComponentChanged):
            for component in self.components:
                if component.id == event.component_id:
                    component.events.dispatch(ChangeSet.of(event))
                    break

    def __repr__(self) -> str:
        """String representation."""
        return f"ParameterTieSet({self.name}: {len(self.components)} components)"


def _component_changes(components: list[AbsorberComponent]) -> ChangeSet:
    """Build component-changed events for unique components in order."""
    seen: set[str] = set()
    events: list[ComponentChanged] = []
    for component in components:
        if component.id in seen:
            continue
        seen.add(component.id)
        events.append(ComponentChanged(component_id=component.id))
    return ChangeSet.of(*events)


def effective_tie_set_for_parameter(
    component: AbsorberComponent, param_name: str
) -> ParameterTieSet | None:
    """Return the effective tie set for a component parameter."""
    tie_set = component.tie_set
    if tie_set is None or param_name not in tie_set.mask:
        return None
    if tie_set.parent_tie is not None and param_name in tie_set.parent_tie.mask:
        return tie_set.parent_tie
    return tie_set


def participation_unit_count(tie_set: ParameterTieSet) -> int:
    """Return direct components plus nested tie sets as participation units."""
    return tie_set.participation_unit_count()
