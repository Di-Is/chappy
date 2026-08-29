"""Use cases for editing parameter tie set membership."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import uuid4

from chappy.application.history.snapshot_builders import component_parameter_state
from chappy.application.history.snapshot_mapping import tie_set_snapshot
from chappy.core.components.tie_set import FULL_TIE_MASK, ParameterTieSet, participation_unit_count

if TYPE_CHECKING:
    from chappy.application.history.ports import ComponentParameterState, TieSetSnapshot
    from chappy.application.optimize.parameter_mutation_usecase import (
        OptimizeParameterMutationUseCase,
    )
    from chappy.core.components.absorber import AbsorberComponent
    from chappy.core.components.tie_set import TieParameterName
    from chappy.core.spectrum_model import SpectrumModel

__all__ = [
    "TieSetCreated",
    "TieSetCreationNeedsConfirmation",
    "TieSetCreationRejected",
    "TieSetCreationResult",
    "TieSetEditRejectionReason",
    "TieSetEditUseCase",
    "TieSetRemovalApplied",
    "TieSetRemovalRejected",
    "TieSetRemovalResult",
]


class TieSetEditRejectionReason(StrEnum):
    """Reason a tie set creation or removal request was rejected."""

    INVALID_MASK = "invalid_mask"
    MIXED_SPECIES = "mixed_species"
    TOO_FEW_COMPONENTS = "too_few_components"
    ALREADY_TIED = "already_tied"
    NOT_TIED = "not_tied"


_VALID_CREATE_MASKS: frozenset[frozenset[TieParameterName]] = frozenset(
    {FULL_TIE_MASK, frozenset({"redshift", "b_parameter"}), frozenset({"redshift"})}
)

_SPECIES_SENSITIVE_NAMES: frozenset[TieParameterName] = frozenset(
    {"column_density", "covering_factor"}
)


@dataclass(frozen=True, slots=True)
class TieSetCreationRejected:
    """A tie set creation request was rejected before mutating any state."""

    reason: TieSetEditRejectionReason


@dataclass(frozen=True, slots=True)
class TieSetCreationNeedsConfirmation:
    """A tie set creation request requires confirming redshift divergence."""

    max_delta_z: float
    adopted_redshift: float


@dataclass(frozen=True, slots=True)
class TieSetCreated:
    """A tie set was created successfully."""

    tie_set: ParameterTieSet
    before_component_states: tuple[ComponentParameterState, ...]


TieSetCreationResult = TieSetCreationRejected | TieSetCreationNeedsConfirmation | TieSetCreated


@dataclass(frozen=True, slots=True)
class TieSetRemovalRejected:
    """A tie set membership removal request was rejected."""

    reason: TieSetEditRejectionReason


@dataclass(frozen=True, slots=True)
class TieSetRemovalApplied:
    """State of one affected tie set before and after a membership removal."""

    uid: str
    before_snapshot: TieSetSnapshot
    after_snapshot: TieSetSnapshot | None
    after_component_states: tuple[ComponentParameterState, ...]


TieSetRemovalResult = TieSetRemovalRejected | tuple[TieSetRemovalApplied, ...]


def _collapse_removals_by_uid(
    applied: list[TieSetRemovalApplied],
) -> tuple[TieSetRemovalApplied, ...]:
    """Merge per-mutation deltas that target the same tie set into one entry.

    Detaching several inner tie sets that share a parent emits one parent delta
    per child. Relying on append order == mutation order, keep the first
    occurrence's ``before_snapshot`` (pristine pre-edit state) and the last
    occurrence's ``after_snapshot`` (terminal state), concatenating component
    states so the collapsed entry records the net before/after exactly once.
    """
    order: list[str] = []
    merged: dict[str, TieSetRemovalApplied] = {}
    states: dict[str, tuple[ComponentParameterState, ...]] = {}
    for entry in applied:
        if entry.uid not in merged:
            order.append(entry.uid)
            merged[entry.uid] = entry
            states[entry.uid] = entry.after_component_states
            continue
        merged[entry.uid] = replace(merged[entry.uid], after_snapshot=entry.after_snapshot)
        states[entry.uid] = states[entry.uid] + entry.after_component_states
    return tuple(replace(merged[uid], after_component_states=states[uid]) for uid in order)


class TieSetEditUseCase:
    """Create parameter tie sets and edit their membership under domain invariants."""

    def __init__(
        self, *, redshift_tolerance: float, parameter_mutation: OptimizeParameterMutationUseCase
    ) -> None:
        """Initialize the tie set edit use case.

        Args:
            redshift_tolerance: Maximum redshift spread across components
                allowed without explicit confirmation.
            parameter_mutation: Seam used to mark freshly-unbound covering
                factor parameters as already initialized.
        """
        self._redshift_tolerance = redshift_tolerance
        self._parameter_mutation = parameter_mutation

    def create_tie_set(
        self,
        model: SpectrumModel,
        components: tuple[AbsorberComponent, ...],
        mask: frozenset[TieParameterName],
        *,
        confirmed_redshift_divergence: bool = False,
    ) -> TieSetCreationResult:
        """Create a user tie set binding the given components under a mask.

        Args:
            model: Spectrum model the tie set is registered on.
            components: Components to bind together.
            mask: Parameter names to share across the components.
            confirmed_redshift_divergence: Whether the caller already
                confirmed proceeding despite a redshift spread beyond
                tolerance.

        Returns:
            Rejection, a request for confirmation, or the created tie set.
        """
        if mask not in _VALID_CREATE_MASKS:
            return TieSetCreationRejected(TieSetEditRejectionReason.INVALID_MASK)

        participant_result = self._resolve_creation_participants(components, mask)
        if participant_result is None:
            return TieSetCreationRejected(TieSetEditRejectionReason.ALREADY_TIED)
        direct_components, inner_tie_sets = participant_result

        if len(direct_components) + len(inner_tie_sets) < 2:
            return TieSetCreationRejected(TieSetEditRejectionReason.TOO_FEW_COMPONENTS)

        participant_components = tuple(
            dict.fromkeys(
                (
                    *direct_components,
                    *(component for tie in inner_tie_sets for component in tie.components),
                )
            )
        )

        if mask & _SPECIES_SENSITIVE_NAMES:
            species_values = {
                component.atomic_line.species if component.atomic_line is not None else None
                for component in participant_components
            }
            if None in species_values or len(species_values) > 1:
                return TieSetCreationRejected(TieSetEditRejectionReason.MIXED_SPECIES)

        # The first selected component represents the first participation unit
        # (its masked values are the inner master's when it is already tied), so
        # its values are adopted regardless of the resolved direct/inner split.
        adopted_values = {
            param_name: components[0].get_parameter_value(param_name) for param_name in mask
        }
        adopted_fixed_states = {
            param_name: components[0].parameters[param_name].fixed for param_name in mask
        }
        redshifts = [
            *(component.get_parameter_value("redshift") for component in direct_components),
            *(tie.components[0].get_parameter_value("redshift") for tie in inner_tie_sets),
        ]
        adopted_redshift = adopted_values["redshift"]
        max_delta_z = max(abs(z - adopted_redshift) for z in redshifts)
        if max_delta_z > self._redshift_tolerance and not confirmed_redshift_divergence:
            return TieSetCreationNeedsConfirmation(
                max_delta_z=max_delta_z, adopted_redshift=adopted_redshift
            )

        before_component_states = tuple(
            component_parameter_state(component) for component in participant_components
        )

        tie_id = f"user-{uuid4().hex}"
        tie_set = ParameterTieSet(tie_id, name=tie_id, mask=mask, origin="user")
        for component in direct_components:
            tie_set.add_component(component)
        for inner_tie_set in inner_tie_sets:
            tie_set.attach_tie_set(inner_tie_set)
        # Overwrite the masters seeded by add_component/attach so the adopted
        # first-selection values win over the direct/inner resolution order.
        for param_name in mask:
            master = tie_set.shared_parameters[param_name]
            master.set_value(adopted_values[param_name])
            master.fixed = adopted_fixed_states[param_name]
        model.add_tie_set(tie_set)

        if "covering_factor" in mask:
            self._parameter_mutation.mark_parameter_initialized(
                tie_set.shared_parameters["covering_factor"]
            )

        return TieSetCreated(tie_set=tie_set, before_component_states=before_component_states)

    def _resolve_creation_participants(
        self, components: tuple[AbsorberComponent, ...], mask: frozenset[TieParameterName]
    ) -> tuple[tuple[AbsorberComponent, ...], tuple[ParameterTieSet, ...]] | None:
        """Resolve selected components to direct components and nested tie sets."""
        direct_components: dict[str, AbsorberComponent] = {}
        inner_tie_sets: dict[int, ParameterTieSet] = {}

        for component in components:
            tie_set = component.tie_set
            if tie_set is None:
                direct_components[component.id] = component
                continue

            if mask == FULL_TIE_MASK:
                return None
            if (
                tie_set.mask != FULL_TIE_MASK
                or tie_set.parent_tie is not None
                or tie_set.member_uids
            ):
                return None
            inner_tie_sets[id(tie_set)] = tie_set

        return tuple(direct_components.values()), tuple(inner_tie_sets.values())

    def remove_from_tie_set(
        self, model: SpectrumModel, components: tuple[AbsorberComponent, ...]
    ) -> TieSetRemovalResult:
        """Remove the given components from their parameter tie sets.

        Untied components are ignored. Each affected tie set is converted
        from "multiplet" to "user" origin (copy-on-write) even if it
        survives the removal, and is dissolved when one or fewer members
        remain.

        Args:
            model: Spectrum model the tie sets are registered on.
            components: Components to unbind from their tie sets.

        Returns:
            A rejection when no selected component is tied, otherwise one
            result per affected tie set.
        """
        tied_components = [component for component in components if component.tie_set is not None]
        if not tied_components:
            return TieSetRemovalRejected(TieSetEditRejectionReason.NOT_TIED)

        groups: dict[str, list[AbsorberComponent]] = {}
        tie_sets_by_uid: dict[str, ParameterTieSet] = {}
        for component in tied_components:
            tie_set = component.tie_set
            if tie_set is None:
                continue
            groups.setdefault(tie_set.uid, []).append(component)
            tie_sets_by_uid[tie_set.uid] = tie_set

        applied: list[TieSetRemovalApplied] = []
        for uid, members in groups.items():
            applied.extend(self._apply_removal(model, tie_sets_by_uid[uid], members))
        return _collapse_removals_by_uid(applied)

    def remove_from_parent_tie_set(
        self, model: SpectrumModel, components: tuple[AbsorberComponent, ...]
    ) -> TieSetRemovalResult:
        """Detach selected direct tie sets from their external parent tie set."""
        inner_tie_sets: dict[int, ParameterTieSet] = {}
        for component in components:
            tie_set = component.tie_set
            if tie_set is None or tie_set.parent_tie is None:
                continue
            inner_tie_sets[id(tie_set)] = tie_set

        if not inner_tie_sets:
            return TieSetRemovalRejected(TieSetEditRejectionReason.NOT_TIED)

        applied: list[TieSetRemovalApplied] = []
        for inner_tie_set in inner_tie_sets.values():
            applied.extend(self._apply_parent_detach(model, inner_tie_set))
        return _collapse_removals_by_uid(applied)

    def _apply_parent_detach(
        self, model: SpectrumModel, inner_tie_set: ParameterTieSet
    ) -> tuple[TieSetRemovalApplied, ...]:
        """Detach one inner tie set from its parent and dissolve parent if needed."""
        parent = inner_tie_set.parent_tie
        if parent is None:
            return ()

        before_parent = tie_set_snapshot(parent)
        before_inner = tie_set_snapshot(inner_tie_set)
        affected = list(inner_tie_set.components)

        parent.detach_tie_set(inner_tie_set)
        after_inner = tie_set_snapshot(inner_tie_set)
        after_parent: TieSetSnapshot | None
        if participation_unit_count(parent) <= 1:
            affected.extend(self._dissolve_tie_set(model, parent))
            after_parent = None
        else:
            after_parent = tie_set_snapshot(parent)

        after_states = tuple(component_parameter_state(component) for component in affected)
        applied = [
            TieSetRemovalApplied(
                uid=before_parent.uid,
                before_snapshot=before_parent,
                after_snapshot=after_parent,
                after_component_states=after_states,
            ),
            TieSetRemovalApplied(
                uid=before_inner.uid,
                before_snapshot=before_inner,
                after_snapshot=after_inner,
                after_component_states=(),
            ),
        ]
        return tuple(applied)

    @staticmethod
    def _parent_removal_applied(
        before_parent: TieSetSnapshot, after_parent: TieSetSnapshot | None
    ) -> TieSetRemovalApplied:
        """Build the parent tie set history entry for a nested removal."""
        return TieSetRemovalApplied(
            uid=before_parent.uid,
            before_snapshot=before_parent,
            after_snapshot=after_parent,
            after_component_states=(),
        )

    def _apply_removal(
        self,
        model: SpectrumModel,
        tie_set: ParameterTieSet,
        members_to_remove: list[AbsorberComponent],
    ) -> tuple[TieSetRemovalApplied, ...]:
        """Unbind selected members from one tie set and dissolve it if needed."""
        before_snapshot = tie_set_snapshot(tie_set)
        # Capture before remove_component mutates the parent's flat membership.
        parent = tie_set.parent_tie
        before_parent = tie_set_snapshot(parent) if parent is not None else None
        unbound: list[AbsorberComponent] = []

        for component in members_to_remove:
            tie_set.remove_component(component)
            unbound.append(component)

        if tie_set.origin == "multiplet":
            tie_set.origin = "user"

        parent_applied: TieSetRemovalApplied | None = None
        if participation_unit_count(tie_set) <= 1:
            if parent is not None and before_parent is not None:
                parent.detach_tie_set(tie_set)
                if participation_unit_count(parent) <= 1:
                    unbound.extend(self._dissolve_tie_set(model, parent))
                    after_parent = None
                else:
                    after_parent = tie_set_snapshot(parent)
                parent_applied = self._parent_removal_applied(before_parent, after_parent)
            unbound.extend(self._dissolve_tie_set(model, tie_set))
            after_snapshot = None
        else:
            after_snapshot = tie_set_snapshot(tie_set)
            if parent is not None and before_parent is not None:
                # The inner tie set stays nested, but removing members detaches
                # the parent's flat membership; record it so undo re-attaches.
                parent_applied = self._parent_removal_applied(
                    before_parent, tie_set_snapshot(parent)
                )

        if "covering_factor" in before_snapshot.mask:
            for component in unbound:
                self._parameter_mutation.mark_parameter_initialized(
                    component.parameters["covering_factor"]
                )

        after_component_states = tuple(
            component_parameter_state(component) for component in unbound
        )

        inner_applied = TieSetRemovalApplied(
            uid=before_snapshot.uid,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            after_component_states=after_component_states,
        )
        if parent_applied is not None:
            return (parent_applied, inner_applied)
        return (inner_applied,)

    def _dissolve_tie_set(
        self, model: SpectrumModel, tie_set: ParameterTieSet
    ) -> list[AbsorberComponent]:
        """Dissolve one tie set using parent-safe teardown order."""
        unbound: list[AbsorberComponent] = []
        for nested_uid in tuple(tie_set.member_uids):
            nested = next(
                (
                    candidate
                    for candidate in model.iter_tie_sets()
                    if candidate.uid == nested_uid and candidate.parent_tie is tie_set
                ),
                None,
            )
            if nested is not None:
                tie_set.detach_tie_set(nested)
                unbound.extend(nested.components)
        for component in [
            component for component in tie_set.components if component.tie_set is tie_set
        ]:
            tie_set.remove_component(component)
            unbound.append(component)
        model.remove_tie_set(tie_set)
        return unbound
