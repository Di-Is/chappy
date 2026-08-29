"""Controller for optimize parameter tie set share/remove actions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from chappy.application.analysis_artifacts import (
    GlobalAnalysisMutationUseCase,
    run_postcommit_actions_isolated,
)
from chappy.application.history.snapshot_mapping import tie_set_snapshot
from chappy.application.optimize import (
    AbsorberModelTopologyUseCase,
    TieSetCreated,
    TieSetCreationNeedsConfirmation,
    TieSetCreationResult,
    TieSetEditUseCase,
    TieSetRemovalRejected,
    TieSetRemovalResult,
    component_topology_change_set,
)
from chappy.core.components.tie_set import FULL_TIE_MASK

if TYPE_CHECKING:
    from collections.abc import Iterable
    from contextlib import AbstractContextManager

    from chappy.application.history.ports import ComponentParameterState, TieSetSnapshot
    from chappy.core.components.absorber import AbsorberComponent
    from chappy.core.components.tie_set import TieParameterName
    from chappy.core.spectroscopy_project import SpectroscopyProject

_SHARE_REDSHIFT_MASK: frozenset[TieParameterName] = frozenset({"redshift"})
_SHARE_REDSHIFT_AND_B_MASK: frozenset[TieParameterName] = frozenset({"redshift", "b_parameter"})


class OptimizeTieSetEditPort(Protocol):
    """Panel operations required by tie set share/remove actions."""

    def tie_set_edit_project(self) -> SpectroscopyProject | None:
        """Return the active project."""
        ...

    def confirm_tie_set_redshift_divergence(
        self, max_delta_z: float, adopted_redshift: float
    ) -> bool:
        """Return whether the user confirmed sharing despite redshift divergence."""
        ...

    def record_tie_set_created(
        self,
        uid: str,
        before_component_states: tuple[ComponentParameterState, ...],
        after_tie_set: TieSetSnapshot,
        after_tie_set_index: int,
    ) -> None:
        """Record tie set creation in history."""
        ...

    def record_tie_set_removed(
        self,
        uids: tuple[str, ...],
        before_tie_sets: tuple[TieSetSnapshot, ...],
        before_tie_set_indices: tuple[int, ...],
        after_tie_sets: tuple[TieSetSnapshot, ...],
        after_tie_set_indices: tuple[int, ...],
        after_component_states: tuple[ComponentParameterState, ...],
    ) -> None:
        """Record tie set member removal or dissolution in history."""
        ...

    def refresh_after_tie_set_edit(self) -> None:
        """Refresh the tree and dependent panel state after a tie set edit."""
        ...

    def tie_set_history_atomic_recording(self) -> AbstractContextManager[None]:
        """Return the required atomic history scope."""
        ...


class OptimizeTieSetEditController:
    """Coordinate parameter tie set creation and membership removal."""

    def __init__(
        self,
        *,
        usecase: TieSetEditUseCase,
        port: OptimizeTieSetEditPort,
        topology: AbsorberModelTopologyUseCase | None = None,
        mutations: GlobalAnalysisMutationUseCase | None = None,
    ) -> None:
        """Initialize the controller.

        Args:
            usecase: Application use case enforcing tie set edit invariants.
            port: Panel operations needed by the workflow.
            topology: Exact absorber topology snapshot use case.
            mutations: Global scientific mutation transaction.
        """
        self._usecase = usecase
        self._port = port
        self._topology = topology or AbsorberModelTopologyUseCase()
        self._mutations = mutations or GlobalAnalysisMutationUseCase()

    @staticmethod
    def has_min_component_count(components: Iterable[AbsorberComponent]) -> bool:
        """Return whether at least two components are selected."""
        return len(tuple(components)) >= 2

    @staticmethod
    def all_untied(components: Iterable[AbsorberComponent]) -> bool:
        """Return whether none of the components already belong to a tie set."""
        return all(component.tie_set is None for component in components)

    @staticmethod
    def any_tied(components: Iterable[AbsorberComponent]) -> bool:
        """Return whether at least one component already belongs to a tie set."""
        return any(component.tie_set is not None for component in components)

    @staticmethod
    def any_parent_tied(components: Iterable[AbsorberComponent]) -> bool:
        """Return whether at least one component belongs to an externally shared tie set."""
        return any(
            component.tie_set is not None and component.tie_set.parent_tie is not None
            for component in components
        )

    @staticmethod
    def same_species(components: Iterable[AbsorberComponent]) -> bool:
        """Return whether every component shares the same known ion species."""
        species_values = {
            component.atomic_line.species if component.atomic_line is not None else None
            for component in components
        }
        return None not in species_values and len(species_values) == 1

    def can_share_redshift(self, components: Iterable[AbsorberComponent]) -> bool:
        """Return whether redshift sharing can be created for the selection."""
        components = tuple(components)
        return self._can_share_external_mask(components)

    def can_share_redshift_and_b(self, components: Iterable[AbsorberComponent]) -> bool:
        """Return whether redshift-and-b sharing can be created for the selection."""
        return self.can_share_redshift(components)

    def can_share_all_parameters(self, components: Iterable[AbsorberComponent]) -> bool:
        """Return whether full-parameter sharing can be created for the selection."""
        components = tuple(components)
        return (
            self.has_min_component_count(components)
            and self.all_untied(components)
            and self.same_species(components)
        )

    def _can_share_external_mask(self, components: tuple[AbsorberComponent, ...]) -> bool:
        """Return whether z/z+b sharing can be created for selected participation units."""
        unit_count = 0
        seen_tie_sets: set[int] = set()
        for component in components:
            tie_set = component.tie_set
            if tie_set is None:
                unit_count += 1
                continue
            if (
                tie_set.mask != FULL_TIE_MASK
                or tie_set.parent_tie is not None
                or tie_set.member_uids
            ):
                return False
            tie_key = id(tie_set)
            if tie_key not in seen_tie_sets:
                seen_tie_sets.add(tie_key)
                unit_count += 1
        return unit_count >= 2

    def can_remove_from_shared_group(self, components: Iterable[AbsorberComponent]) -> bool:
        """Return whether at least one selected component can leave its tie set."""
        return self.any_tied(components)

    def can_remove_from_external_group(self, components: Iterable[AbsorberComponent]) -> bool:
        """Return whether at least one selected component can leave an external parent tie set."""
        return self.any_parent_tied(components)

    def share_redshift(self, components: tuple[AbsorberComponent, ...]) -> None:
        """Create a redshift-only tie set for the selected components."""
        self._create(components, _SHARE_REDSHIFT_MASK)

    def share_redshift_and_b(self, components: tuple[AbsorberComponent, ...]) -> None:
        """Create a redshift-and-b tie set for the selected components."""
        self._create(components, _SHARE_REDSHIFT_AND_B_MASK)

    def share_all_parameters(self, components: tuple[AbsorberComponent, ...]) -> None:
        """Create a full-parameter tie set for the selected components."""
        self._create(components, FULL_TIE_MASK)

    def remove_from_shared_group(self, components: tuple[AbsorberComponent, ...]) -> None:
        """Remove the selected components from their parameter tie sets."""
        self._remove(components, external_parent=False)

    def remove_from_external_group(self, components: tuple[AbsorberComponent, ...]) -> None:
        """Detach selected multiplet tie sets from their external parent tie set."""
        self._remove(components, external_parent=True)

    def _remove(self, components: tuple[AbsorberComponent, ...], *, external_parent: bool) -> None:
        """Remove selected components from direct or external shared groups."""
        project = self._port.tie_set_edit_project()
        if project is None or project.model is None:
            return

        topology_before = self._topology.capture(project, additional_components=components)
        result: TieSetRemovalResult | None = None

        def mutate() -> bool:
            nonlocal result
            result = (
                self._usecase.remove_from_parent_tie_set(project.model, components)
                if external_parent
                else self._usecase.remove_from_tie_set(project.model, components)
            )
            return not isinstance(result, TieSetRemovalRejected) and bool(result)

        def record_history() -> None:
            if result is None or isinstance(result, TieSetRemovalRejected):
                msg = "Cannot record a rejected tie set removal."
                raise RuntimeError(msg)
            uids = tuple(applied.uid for applied in result)
            before_tie_sets = tuple(applied.before_snapshot for applied in result)
            after_tie_sets = tuple(
                applied.after_snapshot for applied in result if applied.after_snapshot is not None
            )
            after_component_states = tuple(
                state for applied in result for state in applied.after_component_states
            )
            before_index_by_uid = {
                state.tie_set.uid: index for index, state in enumerate(topology_before.tie_sets)
            }
            after_index_by_uid = {
                tie_set.uid: index for index, tie_set in enumerate(project.model.iter_tie_sets())
            }
            self._port.record_tie_set_removed(
                uids,
                before_tie_sets,
                tuple(before_index_by_uid[snapshot.uid] for snapshot in before_tie_sets),
                after_tie_sets,
                tuple(after_index_by_uid[snapshot.uid] for snapshot in after_tie_sets),
                after_component_states,
            )

        impact = self._mutations.execute(
            project,
            mutate=mutate,
            rollback=lambda: self._topology.restore(project, topology_before),
            record_history=record_history,
            history_scope=self._port.tie_set_history_atomic_recording,
            postcommit_changes=lambda: component_topology_change_set(
                changed_ids=tuple(component.id for component in topology_before.components)
            ),
        )
        if impact.changed:
            run_postcommit_actions_isolated(self._port.refresh_after_tie_set_edit)

    def _create(
        self, components: tuple[AbsorberComponent, ...], mask: frozenset[TieParameterName]
    ) -> None:
        project = self._port.tie_set_edit_project()
        if project is None or project.model is None:
            return

        result = self._commit_create(project, components, mask, confirmed=False)
        if isinstance(result, TieSetCreationNeedsConfirmation):
            if not self._port.confirm_tie_set_redshift_divergence(
                result.max_delta_z, result.adopted_redshift
            ):
                return
            self._commit_create(project, components, mask, confirmed=True)

    def _commit_create(
        self,
        project: SpectroscopyProject,
        components: tuple[AbsorberComponent, ...],
        mask: frozenset[TieParameterName],
        *,
        confirmed: bool,
    ) -> TieSetCreationResult:
        """Attempt one tie creation and commit global invalidation when changed."""
        topology_before = self._topology.capture(project, additional_components=components)
        result: TieSetCreationResult | None = None

        def mutate() -> bool:
            nonlocal result
            result = self._usecase.create_tie_set(
                project.model, components, mask, confirmed_redshift_divergence=confirmed
            )
            return isinstance(result, TieSetCreated)

        def record_history() -> None:
            if not isinstance(result, TieSetCreated):
                msg = "Cannot record a rejected tie set creation."
                raise TypeError(msg)
            self._port.record_tie_set_created(
                result.tie_set.uid,
                result.before_component_states,
                tie_set_snapshot(result.tie_set),
                tuple(project.model.iter_tie_sets()).index(result.tie_set),
            )

        impact = self._mutations.execute(
            project,
            mutate=mutate,
            rollback=lambda: self._topology.restore(project, topology_before),
            record_history=record_history,
            history_scope=self._port.tie_set_history_atomic_recording,
            postcommit_changes=lambda: component_topology_change_set(
                changed_ids=tuple(component.id for component in topology_before.components)
            ),
        )
        if impact.changed:
            run_postcommit_actions_isolated(self._port.refresh_after_tie_set_edit)
        if result is None:
            msg = "Tie set creation returned no result."
            raise RuntimeError(msg)
        return result
