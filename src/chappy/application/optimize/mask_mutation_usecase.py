"""Atomic region-local mask mutation use case."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol
from uuid import uuid4

from chappy.application.analysis_artifacts import (
    AnalysisMutationImpact,
    RegionLocalAtomicMutationUseCase,
    RegionLocalMutationProjectPort,
    RegionLocalMutationRequest,
)
from chappy.application.history.snapshot_mapping import mask_definition_snapshot

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager

    from chappy.application.history import MaskDefinitionSnapshot
    from chappy.core.masking import MaskDefinition


class MaskMutationKind(StrEnum):
    """User-visible kind of one mask mutation."""

    CREATE = "create"
    UPDATE = "update"
    REMOVE = "remove"


@dataclass(frozen=True, slots=True)
class CreateMaskRequest:
    """Create one new wavelength mask."""

    mask: MaskDefinition


@dataclass(frozen=True, slots=True)
class UpdateMaskRequest:
    """Replace one existing wavelength mask."""

    mask: MaskDefinition


@dataclass(frozen=True, slots=True)
class RemoveMaskRequest:
    """Remove one wavelength mask by identity."""

    mask_id: str


type MaskMutationRequest = CreateMaskRequest | UpdateMaskRequest | RemoveMaskRequest


@dataclass(frozen=True, slots=True)
class MaskMutationResult:
    """Typed committed or no-change result of one mask request."""

    kind: MaskMutationKind
    impact: AnalysisMutationImpact
    stored_mask: MaskDefinition | None = None

    @property
    def changed(self) -> bool:
        """Return whether mask science committed."""
        return self.impact.changed


class MaskMutationStoragePort(Protocol):
    """Silent transaction-only mask storage boundary."""

    def find_mask(self, identifier: str) -> MaskDefinition | None:
        """Return one mask by identity."""
        ...

    @property
    def mask_definitions(self) -> tuple[MaskDefinition, ...]:
        """Return masks in their current stable storage order."""
        ...

    @property
    def is_model_valid(self) -> bool:
        """Return current derived-model cache validity."""
        ...

    def create_mask_definition_for_transaction(self, mask: MaskDefinition) -> MaskDefinition:
        """Create one mask without notifying observers."""
        ...

    def replace_mask_definition_for_transaction(self, mask: MaskDefinition) -> MaskDefinition:
        """Replace one mask without notifying observers."""
        ...

    def remove_mask_definition_for_transaction(self, identifier: str) -> MaskDefinition | None:
        """Remove one mask without notifying observers."""
        ...

    def restore_mask_definitions_for_transaction(
        self, masks: tuple[MaskDefinition, ...], *, model_was_valid: bool
    ) -> None:
        """Restore exact mask storage and cache validity during rollback."""
        ...


class MaskMutationProjectPort(RegionLocalMutationProjectPort, Protocol):
    """Project boundary required for mask science mutations."""

    @property
    def model(self) -> MaskMutationStoragePort:
        """Return transaction-capable mask storage."""
        ...


class MaskMutationHistoryRecorder(Protocol):
    """History operations required by forward mask mutations."""

    def atomic_recording(self) -> AbstractContextManager[None]:
        """Return a history-only rollback scope."""
        ...

    def record_mask_mutation(
        self,
        *,
        kind: MaskMutationKind,
        mask_id: str,
        before: MaskDefinitionSnapshot | None,
        after: MaskDefinitionSnapshot | None,
        before_index: int | None,
        after_index: int | None,
        affected_region_ids: tuple[str, ...],
    ) -> None:
        """Record one mask create, update, or remove command."""
        ...


class MaskMutationUseCase:
    """Apply one mask request and invalidate only its owning regions."""

    def __init__(self, *, transaction: RegionLocalAtomicMutationUseCase | None = None) -> None:
        """Initialize with the shared region-local transaction."""
        self._transaction = transaction or RegionLocalAtomicMutationUseCase()

    def execute(
        self,
        project: MaskMutationProjectPort,
        request: MaskMutationRequest,
        *,
        history_recorder: MaskMutationHistoryRecorder,
    ) -> MaskMutationResult:
        """Validate and atomically commit one typed mask mutation."""
        if isinstance(request, CreateMaskRequest):
            return self._create(project, request, history_recorder)
        if isinstance(request, UpdateMaskRequest):
            return self._update(project, request, history_recorder)
        return self._remove(project, request, history_recorder)

    def _create(
        self,
        project: MaskMutationProjectPort,
        request: CreateMaskRequest,
        history: MaskMutationHistoryRecorder,
    ) -> MaskMutationResult:
        mask = self._with_stable_identifier(request.mask)
        group_id = self._required_group_id(mask)
        existing = project.model.find_mask(mask.identifier)
        if existing is not None and existing != mask:
            msg = f"Mask definition already exists: {mask.identifier}"
            raise ValueError(msg)
        stored: MaskDefinition | None = existing
        masks_before = project.model.mask_definitions
        model_was_valid = project.model.is_model_valid

        def mutate() -> bool:
            nonlocal stored
            if existing is not None:
                return False
            stored = project.model.create_mask_definition_for_transaction(mask)
            return True

        result = self._execute_transaction(
            project,
            kind=MaskMutationKind.CREATE,
            mask_id=mask.identifier,
            affected_region_ids=(group_id,),
            before=None,
            before_index=None,
            after_index=len(masks_before),
            after_mask=lambda: stored,
            mutate=mutate,
            rollback=lambda: project.model.restore_mask_definitions_for_transaction(
                masks_before, model_was_valid=model_was_valid
            ),
            history=history,
        )
        return MaskMutationResult(kind=MaskMutationKind.CREATE, impact=result, stored_mask=stored)

    @staticmethod
    def _with_stable_identifier(mask: MaskDefinition) -> MaskDefinition:
        """Return a create candidate whose identity is stable across storage and history."""
        if mask.identifier:
            return mask
        return replace(mask, identifier=str(uuid4()))

    def _update(
        self,
        project: MaskMutationProjectPort,
        request: UpdateMaskRequest,
        history: MaskMutationHistoryRecorder,
    ) -> MaskMutationResult:
        requested = request.mask
        new_group_id = self._required_group_id(requested)
        existing = project.model.find_mask(requested.identifier)
        if existing is None:
            return MaskMutationResult(
                kind=MaskMutationKind.UPDATE, impact=AnalysisMutationImpact.no_change()
            )
        old_group_id = self._required_group_id(existing)
        effective = requested.rename(existing.label) if not requested.label else requested
        before = mask_definition_snapshot(existing)
        masks_before = project.model.mask_definitions
        mask_index = self._mask_index(masks_before, requested.identifier)
        model_was_valid = project.model.is_model_valid

        result = self._execute_transaction(
            project,
            kind=MaskMutationKind.UPDATE,
            mask_id=requested.identifier,
            affected_region_ids=(old_group_id, new_group_id),
            before=before,
            before_index=mask_index,
            after_index=mask_index,
            after_mask=lambda: project.model.find_mask(requested.identifier),
            mutate=lambda: self._replace_if_changed(project, existing, effective),
            rollback=lambda: project.model.restore_mask_definitions_for_transaction(
                masks_before, model_was_valid=model_was_valid
            ),
            history=history,
        )
        return MaskMutationResult(
            kind=MaskMutationKind.UPDATE,
            impact=result,
            stored_mask=project.model.find_mask(requested.identifier),
        )

    def _remove(
        self,
        project: MaskMutationProjectPort,
        request: RemoveMaskRequest,
        history: MaskMutationHistoryRecorder,
    ) -> MaskMutationResult:
        existing = project.model.find_mask(request.mask_id)
        if existing is None:
            return MaskMutationResult(
                kind=MaskMutationKind.REMOVE, impact=AnalysisMutationImpact.no_change()
            )
        group_id = self._required_group_id(existing)
        before = mask_definition_snapshot(existing)
        masks_before = project.model.mask_definitions
        before_index = self._mask_index(masks_before, request.mask_id)
        model_was_valid = project.model.is_model_valid
        result = self._execute_transaction(
            project,
            kind=MaskMutationKind.REMOVE,
            mask_id=request.mask_id,
            affected_region_ids=(group_id,),
            before=before,
            before_index=before_index,
            after_index=None,
            after_mask=lambda: None,
            mutate=lambda: (
                project.model.remove_mask_definition_for_transaction(request.mask_id) is not None
            ),
            rollback=lambda: project.model.restore_mask_definitions_for_transaction(
                masks_before, model_was_valid=model_was_valid
            ),
            history=history,
        )
        return MaskMutationResult(kind=MaskMutationKind.REMOVE, impact=result)

    def _execute_transaction(  # noqa: PLR0913 - transaction facts stay explicit
        self,
        project: MaskMutationProjectPort,
        *,
        kind: MaskMutationKind,
        mask_id: str,
        affected_region_ids: tuple[str, ...],
        before: MaskDefinitionSnapshot | None,
        before_index: int | None,
        after_index: int | None,
        after_mask: Callable[[], MaskDefinition | None],
        mutate: Callable[[], bool],
        rollback: Callable[[], None],
        history: MaskMutationHistoryRecorder,
    ) -> AnalysisMutationImpact:
        normalized_ids = tuple(dict.fromkeys(affected_region_ids))

        def record_history() -> None:
            after_value = after_mask()
            history.record_mask_mutation(
                kind=kind,
                mask_id=mask_id,
                before=before,
                after=mask_definition_snapshot(after_value) if after_value is not None else None,
                before_index=before_index,
                after_index=after_index,
                affected_region_ids=normalized_ids,
            )

        result = self._transaction.execute(
            project,
            RegionLocalMutationRequest(affected_region_ids=normalized_ids),
            mutate=mutate,
            rollback=rollback,
            record_history=record_history,
            history_scope=history.atomic_recording,
        )
        return result.impact

    @staticmethod
    def _replace_if_changed(
        project: MaskMutationProjectPort, existing: MaskDefinition, requested: MaskDefinition
    ) -> bool:
        """Replace one mask only when its effective value differs."""
        if existing == requested:
            return False
        project.model.replace_mask_definition_for_transaction(requested)
        return True

    @staticmethod
    def _required_group_id(mask: MaskDefinition) -> str:
        """Return the required owning region identity."""
        if not mask.group_id:
            msg = "MaskDefinition.group_id is required"
            raise ValueError(msg)
        return mask.group_id

    @staticmethod
    def _mask_index(masks: tuple[MaskDefinition, ...], mask_id: str) -> int:
        """Return the exact storage index for a required mask identity."""
        for index, mask in enumerate(masks):
            if mask.identifier == mask_id:
                return index
        msg = f"Mask definition index not found: {mask_id}"
        raise ValueError(msg)


__all__ = [
    "CreateMaskRequest",
    "MaskMutationHistoryRecorder",
    "MaskMutationKind",
    "MaskMutationProjectPort",
    "MaskMutationRequest",
    "MaskMutationResult",
    "MaskMutationStoragePort",
    "MaskMutationUseCase",
    "RemoveMaskRequest",
    "UpdateMaskRequest",
]
