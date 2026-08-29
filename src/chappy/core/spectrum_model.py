"""Central spectrum model coordinating all components."""

from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from logging import getLogger
from typing import Any, Literal, cast
from uuid import uuid4

import numpy as np
from numpy.typing import NDArray

# Conditional imports for component loading
from .change_set import ChangeSet
from .components.absorber import AbsorberComponent
from .components.base import ModelComponent
from .components.continuum import ContinuumComponent
from .components.tie_set import ParameterTieSet, TieParameterName
from .event_dispatcher import DomainEventDispatcher
from .events import (
    ComponentAdded,
    ComponentRemoved,
    DomainEvent,
    MasksChanged,
    ModelInvalidated,
    ModelUpdated,
    ModelUpdateProgress,
)
from .masking import MaskDefinition
from .math.instrument_resolution import (
    apply_instrument_resolution,
    apply_instrument_resolution_model,
    resolve_oversample_factor,
)
from .resolution import ResolutionState
from .spectrum import Spectrum

logger = getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SpectrumModelDerivedStateSnapshot:
    """Exact derived model state restored when a storage transaction aborts."""

    model_flux: NDArray[np.float64] | None
    residuals: NDArray[np.float64] | None
    raw_model_flux: NDArray[np.float64] | None
    model_valid: bool


class SpectrumModel:
    """Central model for spectral analysis.

    This class manages the observed spectrum, model components,
    and coordinates updates between them. It follows the observer
    pattern to notify views of changes.

    Model operations dispatch typed domain events through ``events``.
    """

    def __init__(self) -> None:
        """Initialize spectrum model."""
        # Data
        self.observed_spectrum: Spectrum | None = None
        self.model_spectrum: Spectrum | None = None
        self.components: list[ModelComponent] = []
        self._tie_sets: dict[str, list[ParameterTieSet]] = {}
        self._component_by_id: dict[str, ModelComponent] = {}

        # Cached calculations
        self._residuals: NDArray[np.float64] | None = None
        self._model_valid = False
        self._raw_model_flux: NDArray[np.float64] | None = None

        # Instrumental resolution configuration (None -> disabled)
        self._resolution_state: ResolutionState | None = None

        # Fitting configuration
        self.fit_wavelength_range: tuple[float, float] | None = None
        self._mask_definitions: list[MaskDefinition] = []

        self.events = DomainEventDispatcher()

    def add_tie_set(self, tie_set: ParameterTieSet) -> None:
        """Register a parameter tie set with the model."""
        tie_sets = self._tie_sets.setdefault(tie_set.tie_id, [])
        tie_sets.append(tie_set)

    def remove_tie_set(self, tie_set: ParameterTieSet) -> None:
        """Remove a parameter tie set from the model.

        Args:
            tie_set: The parameter tie set to remove.
        """
        tie_sets = self._tie_sets.get(tie_set.tie_id)
        if not tie_sets:
            return
        try:
            tie_sets.remove(tie_set)
        except ValueError:
            return
        if not tie_sets:
            self._tie_sets.pop(tie_set.tie_id, None)

    def iter_tie_sets(self) -> Iterator[ParameterTieSet]:
        """Iterate over registered parameter tie sets."""
        for tie_sets in self._tie_sets.values():
            yield from tie_sets

    def rebuild_tie_sets(self, tie_sets_payload: Iterable[Mapping[str, Any]] | None) -> None:
        """Recreate parameter tie sets from serialized payload.

        Each payload entry is a mapping with keys ``tie_id`` (str),
        ``name`` (str), ``origin`` (``"multiplet"`` or ``"user"``),
        ``mask`` (list of ``TieParameterName``), ``component_ids``
        (list of component IDs), and ``shared_parameters`` (mapping of
        parameter name to ``{"value": float, "fixed": bool}``).
        """
        if not tie_sets_payload:
            return

        component_map = {
            component.id: component
            for component in self.components
            if isinstance(component, AbsorberComponent)
        }

        pending_attach: list[tuple[ParameterTieSet, tuple[str, ...]]] = []

        for entry in tie_sets_payload:
            component_ids = [cid for cid in entry.get("component_ids", []) if cid in component_map]
            member_uids = tuple(str(member_uid) for member_uid in entry.get("member_uids", ()))
            if len(component_ids) + len(member_uids) < 2:
                continue
            if not member_uids and len(component_ids) < 2:
                continue

            tie_id = entry.get("tie_id", "")
            uid = entry.get("uid")
            name = entry.get("name", "")
            origin = cast("Literal['multiplet', 'user']", entry.get("origin", "multiplet"))
            mask = frozenset(cast("Iterable[TieParameterName]", entry.get("mask", ())))

            tie_set = ParameterTieSet(tie_id, uid=uid, name=name, mask=mask, origin=origin)

            # Attach components first so shared parameters bind correctly.
            for component_id in component_ids:
                component = component_map[component_id]
                tie_set.add_component(component)

            if not member_uids and len(tie_set.components) < 2:
                continue

            shared_parameters = entry.get("shared_parameters", {})
            for param_name, metadata in shared_parameters.items():
                parameter = tie_set.shared_parameters.get(param_name)
                if parameter is None:
                    continue

                value = metadata.get("value")
                if value is not None:
                    try:
                        parameter.set_value(float(value))
                    except (TypeError, ValueError):
                        logger.warning(
                            "Skipping invalid value %r for parameter %s in tie set %s",
                            value,
                            param_name,
                            tie_id,
                        )

                if "fixed" in metadata:
                    parameter.fixed = bool(metadata["fixed"])

            # Notify components that shared parameters may have changed.
            for component in tie_set.components:
                component.notify_changed()

            self.add_tie_set(tie_set)
            if member_uids:
                pending_attach.append((tie_set, member_uids))

        tie_sets_by_uid = {tie_set.uid: tie_set for tie_set in self.iter_tie_sets()}
        for outer, member_uids in pending_attach:
            for member_uid in member_uids:
                inner = tie_sets_by_uid.get(member_uid)
                if inner is None:
                    continue
                try:
                    outer.attach_tie_set(inner)
                except ValueError:
                    logger.warning(
                        "Skipping invalid nested tie set %s -> %s", outer.uid, member_uid
                    )

    def tie_sets_for_components(self, component_ids: list[str]) -> tuple[ParameterTieSet, ...]:
        """Return all parameter tie sets containing any of these components.

        Args:
            component_ids: List of component IDs to check for tie set membership.

        Returns:
            Parameter tie sets containing any target component.
        """
        component_id_set = set(component_ids)
        tie_sets: list[ParameterTieSet] = []
        seen_tie_set_keys: set[int] = set()

        for tie_set in self.iter_tie_sets():
            # Check if any component in this tie set is in our target list
            tie_set_component_ids = {c.id for c in tie_set.components}
            if not tie_set_component_ids.intersection(component_id_set):
                continue

            # Avoid duplicates (same tie set via different components)
            tie_set_key = id(tie_set)  # Use object id since tie_id is not unique
            if tie_set_key in seen_tie_set_keys:
                continue
            seen_tie_set_keys.add(tie_set_key)
            tie_sets.append(tie_set)

        return tuple(tie_sets)

    def set_observed_spectrum(self, spectrum: Spectrum) -> ChangeSet:
        """Set the observed spectrum.

        Args:
            spectrum: Observed spectrum data
        """
        self.observed_spectrum = spectrum
        self._initialize_model_spectrum()
        return self.invalidate_model().extend(self.update_model())

    @property
    def resolution_state(self) -> ResolutionState | None:
        """Instrumental resolution configuration, if any."""
        return self._resolution_state

    def set_resolution_state(self, state: ResolutionState | None) -> ChangeSet:
        """Configure instrumental resolution for model calculations."""
        if state is None and self._resolution_state is None:
            return ChangeSet.empty()

        if state is None:
            self._resolution_state = None
            return self.invalidate_model()

        # Ensure local copy to avoid accidental external mutation
        new_state = ResolutionState(value=float(state.value), enabled=bool(state.enabled))

        if self._resolution_state == new_state:
            return ChangeSet.empty()

        self._resolution_state = new_state
        return self.invalidate_model()

    @property
    def mask_definitions(self) -> tuple[MaskDefinition, ...]:
        """Return all mask definitions, including disabled ones."""
        return tuple(self._mask_definitions)

    @mask_definitions.setter
    def mask_definitions(self, masks: list[MaskDefinition] | tuple[MaskDefinition, ...]) -> None:
        normalized: list[MaskDefinition] = []
        for mask in masks:
            if not mask.group_id:
                msg = "MaskDefinition.group_id is required"
                raise ValueError(msg)
            normalized.append(self._ensure_identifier(mask))

        self._mask_definitions = normalized
        self.invalidate_model()
        self._dispatch(MasksChanged())

    @property
    def is_model_valid(self) -> bool:
        """Return whether the cached model spectrum is up to date."""
        return self._model_valid

    def mask_ranges(self) -> list[tuple[float, float]]:
        """Return enabled mask ranges without metadata.

        Returns:
            List of wavelength spans extracted from enabled masks.
        """
        ranges: list[tuple[float, float]] = []
        for mask in self._mask_definitions:
            if not mask.enabled:
                continue
            try:
                ranges.append(mask.as_tuple())
            except ValueError:
                logger.warning(
                    "Skipping malformed mask without range", extra={"mask_id": mask.identifier}
                )
        return ranges

    def get_masks_for_group(self, group_id: str) -> list[MaskDefinition]:
        """Return masks associated with a given absorption region."""
        return [mask for mask in self._mask_definitions if mask.group_id == group_id]

    def mask_ranges_for_group(self, group_id: str) -> list[tuple[float, float]]:
        """Return enabled mask ranges filtered by absorption region.

        Args:
            group_id: Identifier of the absorption region.

        Returns:
            List of wavelength spans that apply to the requested group.
        """
        regions: list[tuple[float, float]] = []
        for mask in self._mask_definitions:
            if not mask.enabled:
                continue
            try:
                span = mask.as_tuple()
            except ValueError:
                logger.warning(
                    "Skipping malformed mask without range", extra={"mask_id": mask.identifier}
                )
                continue
            if mask.group_id == group_id:
                regions.append(span)
        return regions

    def add_mask_definition(self, mask: MaskDefinition) -> MaskDefinition:
        """Add a mask to the model and emit change notifications.

        Args:
            mask: Mask definition to register with the model.

        Returns:
            Mask stored in the model after ensuring identifiers and labels.
        """
        final_mask = self.create_mask_definition_for_transaction(mask)
        self.notify_mask_storage_changed()
        return final_mask

    def update_mask_definition(self, mask: MaskDefinition) -> MaskDefinition:
        """Update an existing mask or add it if missing.

        Args:
            mask: Mask definition containing updated information.

        Returns:
            Mask instance managed by the model after the update.
        """
        if self.find_mask(mask.identifier) is not None:
            final_mask = self.replace_mask_definition_for_transaction(mask)
            self.notify_mask_storage_changed()
            return final_mask
        return self.add_mask_definition(mask)

    def remove_mask(self, identifier: str) -> bool:
        """Remove a mask from the model by identifier.

        Args:
            identifier: Mask identifier to remove.

        Returns:
            True when a mask was removed.
        """
        removed = self.remove_mask_definition_for_transaction(identifier)
        if removed is None:
            return False
        self.notify_mask_storage_changed()
        return True

    def create_mask_definition_for_transaction(self, mask: MaskDefinition) -> MaskDefinition:
        """Create one mask without dispatching observer notifications.

        This explicit storage boundary is reserved for application transactions;
        callers must invoke :meth:`notify_mask_storage_changed` after commit.
        """
        if not mask.group_id:
            msg = "MaskDefinition.group_id is required"
            raise ValueError(msg)
        final_mask = self._ensure_identifier(mask)
        if self.find_mask(final_mask.identifier) is not None:
            msg = f"Mask definition already exists: {final_mask.identifier}"
            raise ValueError(msg)
        if not final_mask.label:
            final_mask = final_mask.rename(self._suggest_mask_label())
        self._mask_definitions.append(final_mask)
        self._model_valid = False
        return final_mask

    def replace_mask_definition_for_transaction(self, mask: MaskDefinition) -> MaskDefinition:
        """Replace one mask without dispatching observer notifications."""
        if not mask.group_id:
            msg = "MaskDefinition.group_id is required"
            raise ValueError(msg)
        for index, existing in enumerate(self._mask_definitions):
            if existing.identifier != mask.identifier:
                continue
            final_mask = self._ensure_identifier(mask)
            if not final_mask.label and existing.label:
                final_mask = final_mask.rename(existing.label)
            self._mask_definitions[index] = final_mask
            self._model_valid = False
            return final_mask
        msg = f"Mask definition not found: {mask.identifier}"
        raise ValueError(msg)

    def remove_mask_definition_for_transaction(self, identifier: str) -> MaskDefinition | None:
        """Remove one mask without dispatching observer notifications."""
        for index, existing in enumerate(self._mask_definitions):
            if existing.identifier != identifier:
                continue
            del self._mask_definitions[index]
            self._model_valid = False
            return existing
        return None

    def restore_mask_definition_for_transaction(
        self, identifier: str, mask: MaskDefinition | None, *, index: int | None
    ) -> None:
        """Restore one exact mask state and collection position silently."""
        existing_index = next(
            (
                index
                for index, existing in enumerate(self._mask_definitions)
                if existing.identifier == identifier
            ),
            None,
        )
        if existing_index is not None:
            del self._mask_definitions[existing_index]
        if mask is None:
            if index is not None:
                msg = "A removed mask cannot have a storage index."
                raise ValueError(msg)
        else:
            if index is None or not 0 <= index <= len(self._mask_definitions):
                msg = f"Mask storage index is out of bounds: {index}"
                raise ValueError(msg)
            self._mask_definitions.insert(index, mask)
        self._model_valid = False

    def restore_mask_definitions_for_transaction(
        self, masks: tuple[MaskDefinition, ...], *, model_was_valid: bool
    ) -> None:
        """Restore exact mask ordering and cache validity during rollback."""
        self._mask_definitions = list(masks)
        self._model_valid = model_was_valid

    def notify_mask_storage_changed(self) -> None:
        """Notify observers after a mask storage transaction has committed."""
        self.publish_storage_changes(ChangeSet.of(ModelInvalidated(), MasksChanged()))

    def rebuild_mask_storage(self) -> ChangeSet:
        """Recalculate mask-dependent caches and return post-commit events."""
        return self.rebuild_model_storage().extend(MasksChanged())

    def remove_masks_for_group(self, group_id: str) -> int:
        """Remove all masks associated with the specified group.

        Args:
            group_id: Identifier of the group to remove masks for.

        Returns:
            Number of masks removed.
        """
        existing_count = len(self._mask_definitions)
        self._mask_definitions = [
            mask for mask in self._mask_definitions if mask.group_id != group_id
        ]
        removed = existing_count - len(self._mask_definitions)
        if removed:
            self.invalidate_model()
            self._dispatch(MasksChanged())
        return removed

    def reassign_masks_to_group(self, source_group_id: str, target_group_id: str) -> int:
        """Reassign all masks from one group identifier to another.

        Args:
            source_group_id: Identifier of the group currently associated with the masks.
            target_group_id: Identifier of the group to associate masks with.

        Returns:
            Number of masks updated.
        """
        updated = 0
        updated_masks: list[MaskDefinition] = []
        for mask in self._mask_definitions:
            if mask.group_id == source_group_id:
                updated += 1
                updated_masks.append(mask.with_group_id(target_group_id))
            else:
                updated_masks.append(mask)

        if updated:
            self._mask_definitions = updated_masks
            self.invalidate_model()
            self._dispatch(MasksChanged())
        return updated

    def find_mask(self, identifier: str) -> MaskDefinition | None:
        """Look up a mask by identifier.

        Args:
            identifier: Mask identifier to locate.

        Returns:
            Matching mask definition if found, otherwise ``None``.
        """
        for mask in self._mask_definitions:
            if mask.identifier == identifier:
                return mask
        return None

    def _ensure_identifier(self, mask: MaskDefinition) -> MaskDefinition:
        if mask.identifier:
            return mask
        return MaskDefinition(
            identifier=str(uuid4()),
            label=mask.label,
            mode=mask.mode,
            start_wavelength=mask.start_wavelength,
            end_wavelength=mask.end_wavelength,
            center=mask.center,
            half_width=mask.half_width,
            note=mask.note,
            color=mask.color,
            enabled=mask.enabled,
            group_id=mask.group_id,
        )

    def _suggest_mask_label(self) -> str:
        next_index = 1
        existing_indices: set[int] = set()
        for mask in self._mask_definitions:
            label = mask.label
            if not label:
                continue
            if label.startswith("Mask "):
                _, _, suffix = label.partition(" ")
                if suffix.isdigit():
                    existing_indices.add(int(suffix))
        if existing_indices:
            next_index = max(existing_indices) + 1
        return f"Mask {next_index}"

    def _build_mask_index(self, wavelength: NDArray[np.float64]) -> NDArray[np.bool_]:
        mask = np.zeros_like(wavelength, dtype=bool)
        for min_wave, max_wave in self.mask_ranges():
            mask |= (wavelength >= min_wave) & (wavelength <= max_wave)
        return mask

    def apply_resolution_effect(
        self, wavelength: NDArray[np.float64], flux: NDArray[np.float64]
    ) -> NDArray[np.float64]:
        """Apply configured instrumental resolution to flux values."""
        state = self._resolution_state
        if state is None or not state.enabled:
            return np.asarray(flux, dtype=np.float64)

        value = float(state.value)
        if value <= 0:
            return np.asarray(flux, dtype=np.float64)

        return apply_instrument_resolution(
            wavelength, np.asarray(flux, dtype=np.float64), resolution=value
        )

    def oversample_factor(self, wavelength: NDArray[np.float64]) -> int:
        """Fine-grid oversampling for the narrowest enabled absorber on this grid.

        External-continuum absorbers scale absorption against a continuum cached on the
        observed grid only, so they cannot be evaluated on a finer grid; their presence
        forces a factor of 1.
        """
        absorbers = [c for c in self.components if c.enabled and isinstance(c, AbsorberComponent)]
        if any(a.has_active_external_continuum() for a in absorbers):
            return 1
        b_values = [a.parameters["b_parameter"].value for a in absorbers]
        return resolve_oversample_factor(wavelength, min(b_values) if b_values else None)

    def convolve_model_flux(
        self,
        wavelength: NDArray[np.float64],
        raw_flux: NDArray[np.float64],
        model_flux: Callable[[NDArray[np.float64]], NDArray[np.float64]],
    ) -> NDArray[np.float64]:
        """Apply instrumental resolution, oversampling narrow lines onto a fine grid.

        Args:
            wavelength: Contiguous pixel grid the convolved model is returned on.
            raw_flux: Pre-convolution model flux already evaluated on ``wavelength``.
            model_flux: Recomputes raw flux on an arbitrary grid (for oversampling).
        """
        state = self._resolution_state
        if state is None or not state.enabled:
            return np.asarray(raw_flux, dtype=np.float64)

        value = float(state.value)
        if value <= 0:
            return np.asarray(raw_flux, dtype=np.float64)

        oversample = self.oversample_factor(wavelength)
        if oversample <= 1:
            return apply_instrument_resolution(
                wavelength, np.asarray(raw_flux, dtype=np.float64), resolution=value
            )
        return apply_instrument_resolution_model(
            wavelength, model_flux, resolution=value, oversample=oversample
        )

    def _initialize_model_spectrum(self) -> None:
        """Initialize model spectrum with same wavelength grid as observed."""
        if self.observed_spectrum:
            self.model_spectrum = Spectrum(
                wavelength=self.observed_spectrum.wavelength.copy(),
                flux=np.ones_like(self.observed_spectrum.wavelength),
                error=None,
                header={"MODEL": True},
            )

    def add_component(self, component: ModelComponent) -> ChangeSet:
        """Add a model component.

        Args:
            component: Component to add
        """
        logger.info("🔥 Adding component: %s (%s)", component.name, type(component).__name__)

        can_incremental_update = self._can_incremental_update_for_add()

        self.components.append(component)
        self._component_by_id[component.id] = component
        component.events.subscribe(self._handle_component_change)
        change_set = self._dispatch(ComponentAdded(component_id=component.id))

        # If this is an absorber and we have active shared continuums, apply them
        if isinstance(component, AbsorberComponent):
            change_set = change_set.extend(self._apply_active_continuum_to_absorber(component))

        incremental_change_set = (
            self._try_incremental_update_for_add(component) if can_incremental_update else None
        )
        if incremental_change_set is not None:
            logger.info("✅ Component %s added and model updated (incremental)", component.name)
            return change_set.extend(incremental_change_set)

        change_set = change_set.extend(self.invalidate_model(), self.update_model())
        logger.info("✅ Component %s added and model updated (full)", component.name)
        return change_set

    def add_component_storage(self, component: ModelComponent) -> ChangeSet:
        """Add component storage without derived calculation or observer notification."""
        if component in self.components or component.id in self._component_by_id:
            msg = f"Model component already exists: {component.id}"
            raise ValueError(msg)
        self.components.append(component)
        self._component_by_id[component.id] = component
        component.events.subscribe(self._handle_component_change)
        change_set = ChangeSet.of(ComponentAdded(component_id=component.id))
        if isinstance(component, AbsorberComponent):
            with component.events.suppress_dispatching():
                change_set = change_set.extend(self._apply_active_continuum_to_absorber(component))
        self._model_valid = False
        return change_set.extend(ModelInvalidated())

    def remove_component(self, component: ModelComponent) -> ChangeSet:
        """Remove a model component.

        Args:
            component: Component to remove
        """
        if component in self.components:
            component.events.unsubscribe(self._handle_component_change)
            self.components.remove(component)
            self._component_by_id.pop(component.id, None)
            return self._dispatch(ComponentRemoved(component_id=component.id)).extend(
                self.invalidate_model(), self.update_model()
            )
        return ChangeSet.empty()

    def remove_component_storage(self, component: ModelComponent) -> ChangeSet:
        """Remove component storage without derived calculation or observer notification."""
        if component not in self.components:
            return ChangeSet.empty()
        component.events.unsubscribe(self._handle_component_change)
        self.components.remove(component)
        self._component_by_id.pop(component.id, None)
        self._model_valid = False
        return ChangeSet.of(ComponentRemoved(component_id=component.id), ModelInvalidated())

    @contextmanager
    def suppress_scientific_notifications(
        self, additional_components: Iterable[ModelComponent] = ()
    ) -> Iterator[None]:
        """Suppress model, component, and tie listeners during atomic storage mutation."""
        with ExitStack() as stack:
            stack.enter_context(self.events.suppress_dispatching())
            components = tuple(dict.fromkeys((*self.components, *additional_components)))
            for component in components:
                stack.enter_context(component.events.suppress_dispatching())
            for tie_set in tuple(self.iter_tie_sets()):
                stack.enter_context(tie_set.events.suppress_dispatching())
            yield

    def rebuild_model_storage(self) -> ChangeSet:
        """Recalculate derived model state without dispatching synchronous observers."""
        with self.events.suppress_dispatching():
            return self.invalidate_model().extend(self.update_model())

    def snapshot_derived_state_for_transaction(self) -> SpectrumModelDerivedStateSnapshot:
        """Capture exact cached arrays and validity before a storage transaction."""
        return SpectrumModelDerivedStateSnapshot(
            model_flux=(None if self.model_spectrum is None else self.model_spectrum.flux.copy()),
            residuals=None if self._residuals is None else self._residuals.copy(),
            raw_model_flux=(None if self._raw_model_flux is None else self._raw_model_flux.copy()),
            model_valid=self._model_valid,
        )

    def restore_derived_state_for_transaction(
        self, snapshot: SpectrumModelDerivedStateSnapshot
    ) -> None:
        """Restore cached arrays and validity without notifying observers."""
        if snapshot.model_flux is not None:
            if self.model_spectrum is None:
                msg = "Cannot restore model flux without an initialized model spectrum."
                raise RuntimeError(msg)
            self.model_spectrum.flux = snapshot.model_flux.copy()
        self._residuals = None if snapshot.residuals is None else snapshot.residuals.copy()
        self._raw_model_flux = (
            None if snapshot.raw_model_flux is None else snapshot.raw_model_flux.copy()
        )
        self._model_valid = snapshot.model_valid

    def publish_storage_changes(self, change_set: ChangeSet) -> None:
        """Publish a committed storage mutation to synchronous observers."""
        self.events.dispatch_isolated(change_set)

    def restore_component_order_for_transaction(
        self, ordered_components: tuple[ModelComponent, ...]
    ) -> None:
        """Restore exact component identity order, subscriptions, and lookup state."""
        expected_ids = tuple(component.id for component in ordered_components)
        if len(set(expected_ids)) != len(expected_ids):
            msg = "Component rollback order contains duplicate identities."
            raise ValueError(msg)

        expected_object_ids = {id(component) for component in ordered_components}
        for component in tuple(self.components):
            if id(component) not in expected_object_ids:
                component.events.unsubscribe(self._handle_component_change)
        self.components[:] = ordered_components
        self._rebuild_component_index()
        for component in self.components:
            component.events.subscribe(self._handle_component_change)
        self._model_valid = False

    def restore_tie_set_order_for_transaction(
        self, ordered_tie_sets: tuple[ParameterTieSet, ...]
    ) -> None:
        """Restore exact tie-set identities and iteration order without notification."""
        uids = tuple(tie_set.uid for tie_set in ordered_tie_sets)
        if len(set(uids)) != len(uids):
            msg = "Tie-set rollback order contains duplicate identities."
            raise ValueError(msg)

        restored: dict[str, list[ParameterTieSet]] = {}
        for tie_set in ordered_tie_sets:
            restored.setdefault(tie_set.tie_id, []).append(tie_set)
        self._tie_sets = restored
        self._model_valid = False

    def invalidate_model(self) -> ChangeSet:
        """Mark model as needing recalculation."""
        self._model_valid = False
        return self._dispatch(ModelInvalidated())

    def raw_model_flux_on(self, wavelength: NDArray[np.float64]) -> NDArray[np.float64]:
        """Product of all enabled component contributions on an arbitrary grid."""
        flux = np.ones_like(wavelength, dtype=np.float64)
        for component in self.components:
            if component.enabled:
                flux *= component.calculate(wavelength)
        return flux

    def component_transmissions_on(
        self, wavelength: NDArray[np.float64]
    ) -> tuple[tuple[str, NDArray[np.float64]], ...]:
        """Per-absorber transmission curves on the given grid, in component order.

        Each curve is convolved on its own, so the product of the returned curves
        matches the composite model only when instrumental resolution is disabled.
        """
        masked_index = self._build_mask_index(wavelength)
        transmissions: list[tuple[str, NDArray[np.float64]]] = []
        for component in self.components:
            if not component.enabled or not isinstance(component, AbsorberComponent):
                continue
            raw_flux = component.calculate(wavelength)
            flux = self.convolve_model_flux(wavelength, raw_flux, component.calculate)
            if masked_index.any():
                flux = flux.copy()
                flux[masked_index] = np.nan
            transmissions.append((component.id, flux))
        return tuple(transmissions)

    def update_model(self) -> ChangeSet:
        """Recalculate model from all components."""
        if self.observed_spectrum is None or self._model_valid:
            return ChangeSet.empty()
        change_set = self._dispatch(ModelUpdateProgress(0, "Updating model..."))

        wavelength = self.observed_spectrum.wavelength
        raw_model_flux = np.ones_like(wavelength, dtype=np.float64)

        # Calculate contribution from each enabled component
        n_components = len([c for c in self.components if c.enabled])

        for i, component in enumerate(self.components):
            if component.enabled:
                contribution = component.calculate(wavelength)
                raw_model_flux *= contribution

                # Update progress
                progress = int((i + 1) / n_components * 100)
                change_set = change_set.extend(
                    self._dispatch(
                        ModelUpdateProgress(progress, f"Processing {component.name}...")
                    )
                )

        # Apply instrumental resolution effects if configured
        self._raw_model_flux = raw_model_flux
        model_flux = self.convolve_model_flux(wavelength, raw_model_flux, self.raw_model_flux_on)

        masked_index = self._build_mask_index(wavelength)
        if masked_index.any():
            model_flux = model_flux.copy()
            model_flux[masked_index] = np.nan

        # Update model spectrum
        logger.info(
            "Model updated: flux range %.4f - %.4f",
            float(np.nanmin(model_flux)),
            float(np.nanmax(model_flux)),
        )
        if self.model_spectrum is not None:
            self.model_spectrum.flux = model_flux

        # Calculate residuals
        self._calculate_residuals()

        self._model_valid = True
        return change_set.extend(
            self._dispatch(ModelUpdateProgress(100, "Model updated"), ModelUpdated())
        )

    def get_component_by_id(self, component_id: str) -> ModelComponent | None:
        """Lookup model component by identifier.

        Args:
            component_id: Component identifier.

        Returns:
            Component instance if found.
        """
        if not component_id:
            return None

        component = self._component_by_id.get(component_id)
        if component is not None:
            return component

        self._rebuild_component_index()
        return self._component_by_id.get(component_id)

    def get_absorber_component_by_id(self, component_id: str) -> AbsorberComponent | None:
        """Lookup absorber component by identifier.

        Args:
            component_id: Component identifier.

        Returns:
            Absorber component if present.
        """
        component = self.get_component_by_id(component_id)
        return component if isinstance(component, AbsorberComponent) else None

    def _rebuild_component_index(self) -> None:
        """Rebuild cached component lookup table."""
        self._component_by_id = {component.id: component for component in self.components}

    def _can_incremental_update_for_add(self) -> bool:
        """Return whether component addition can use incremental updates."""
        if not self._model_valid:
            return False
        return self._has_incremental_state()

    def _try_incremental_update_for_add(self, component: ModelComponent) -> ChangeSet | None:
        """Apply an incremental model update after adding one component.

        Args:
            component: Newly added component.

        Returns:
            Change set when the update succeeds.
        """
        if not self._has_incremental_state():
            return None

        change_set = self._dispatch(ModelUpdateProgress(0, "Updating model..."))

        if not component.enabled:
            self._model_valid = True
            return change_set.extend(
                self._dispatch(ModelUpdateProgress(100, "Model updated"), ModelUpdated())
            )

        if (
            self.observed_spectrum is None
            or self.model_spectrum is None
            or self._raw_model_flux is None
        ):
            return None

        wavelength = self.observed_spectrum.wavelength
        # Incremental convolution reuses the cached coarse product, which is only exact
        # without oversampling. Narrow lines need a full fine-grid rebuild.
        if self.oversample_factor(wavelength) > 1:
            return None

        contribution = component.calculate(wavelength)
        contribution_arr = np.asarray(contribution, dtype=np.float64)
        if contribution_arr.shape != self._raw_model_flux.shape:
            msg = (
                "Component contribution shape does not match model flux: "
                f"{contribution_arr.shape} vs {self._raw_model_flux.shape}"
            )
            raise ValueError(msg)

        self._raw_model_flux *= contribution_arr

        model_flux = self.apply_resolution_effect(wavelength, self._raw_model_flux)

        masked_index = self._build_mask_index(wavelength)
        if masked_index.any():
            model_flux = model_flux.copy()
            model_flux[masked_index] = np.nan

        self.model_spectrum.flux = model_flux
        self._calculate_residuals()
        self._model_valid = True
        return change_set.extend(
            self._dispatch(ModelUpdateProgress(100, "Model updated"), ModelUpdated())
        )

    def _has_incremental_state(self) -> bool:
        """Return whether incremental model state is available."""
        if self.observed_spectrum is None or self.model_spectrum is None:
            return False
        if self._raw_model_flux is None:
            return False
        return len(self._raw_model_flux) == len(self.observed_spectrum.wavelength)

    def _calculate_residuals(self) -> None:
        """Calculate residuals between observed and model.

        Note: Raw residuals are stored. Error weighting is applied
        during chi-squared calculation for flexibility.
        """
        if self.observed_spectrum and self.model_spectrum:
            # Calculate raw residuals (observed - model)
            self._residuals = self.observed_spectrum.flux - self.model_spectrum.flux

            wavelength = self.observed_spectrum.wavelength
            if wavelength is not None:
                masked_index = self._build_mask_index(wavelength)
                if masked_index.any():
                    self._residuals = self._residuals.copy()
                    self._residuals[masked_index] = np.nan

    @property
    def residuals(self) -> NDArray[np.float64] | None:
        """Get residuals array."""
        return self._residuals

    def get_shared_continuums(self) -> list[tuple[str, Any]]:
        """Get list of continuum components that are available for sharing with absorption mode.

        Returns:
            List of tuples (continuum_name, continuum_component) for shareable continuums
        """
        return [
            (component.name, component)
            for component in self.components
            if isinstance(component, ContinuumComponent) and component.is_shared_with_absorption
        ]

    def _apply_active_continuum_to_absorber(self, absorber: AbsorberComponent) -> ChangeSet:
        """Apply the first available shared continuum to a new absorber.

        Args:
            absorber: The absorber component to configure
        """
        # Get available shared continuums
        shared_continuums = self.get_shared_continuums()
        if not shared_continuums:
            logger.debug("No shared continuums available for new absorber '%s'", absorber.name)
            return ChangeSet.empty()

        # Use the first available continuum
        continuum_name, continuum_component = shared_continuums[0]

        if self.observed_spectrum is None:
            logger.warning("No observed spectrum available for continuum export")
            return ChangeSet.empty()

        # Export continuum data
        wavelength = self.observed_spectrum.wavelength
        continuum_flux = continuum_component.export_for_absorption(wavelength)

        if continuum_flux is not None:
            change_set = absorber.set_external_continuum(
                continuum_name, wavelength, continuum_flux
            )
            logger.info(
                "Applied active continuum '%s' to new absorber '%s'", continuum_name, absorber.name
            )
            return change_set

        logger.warning("Failed to export continuum '%s' for new absorber", continuum_name)
        return ChangeSet.empty()

    def _handle_component_change(self, change_set: ChangeSet) -> None:
        """Forward component changes and invalidate cached model data."""
        self._model_valid = False
        self._dispatch(change_set.extend(ModelInvalidated()))

    def _dispatch(self, *changes: ChangeSet | DomainEvent) -> ChangeSet:
        """Dispatch events through the model dispatcher and return them."""
        change_set = ChangeSet.empty().extend(*changes)
        self.events.dispatch(change_set)
        return change_set
