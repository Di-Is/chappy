"""Mask workflow controller for optimize mode."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Protocol

from chappy.application.analysis_artifacts import run_postcommit_actions_isolated
from chappy.application.optimize import (
    CreateMaskRequest,
    MaskMutationHistoryRecorder,
    MaskMutationRequest,
    MaskMutationUseCase,
    RemoveMaskRequest,
    UpdateMaskRequest,
)
from chappy.gui.adapters.model_event_adapter import SpectrumModelEventAdapter
from chappy.presentation.interaction.interaction_contracts import (
    InteractionPhase,
    InteractionStateSnapshot,
    MaskSelectionContext,
    MaskSelectionRequest,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from PySide6.QtCore import QObject

    from chappy.core.masking import MaskDefinition
    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.modes.analysis.region_detail.mask.mask_panel_adapter import (
        OptimizeMaskPanelAdapter,
    )


MIN_MASK_WIDTH = 0.01


class OptimizeMaskWorkflowPort(Protocol):
    """View boundary required by the optimize mask workflow controller."""

    def current_mask_group_id(self) -> str | None:
        """Return the currently selected mask group identifier."""
        ...

    def show_mask_group_masks(
        self, masks: list[MaskDefinition], active_mask_id: str | None
    ) -> None:
        """Render mask definitions for the selected group."""
        ...

    def set_mask_panel_available(self, available: bool) -> None:
        """Set whether mask editing controls are available."""
        ...

    def expand_mask_panel(self) -> None:
        """Expand the mask editor panel."""
        ...

    def set_mask_interaction_active(self, active: bool) -> None:
        """Reflect whether mask selection interaction is active."""
        ...

    def is_mask_interaction_active(self) -> bool:
        """Return whether mask selection interaction is active."""
        ...

    def is_velocity_plot_active(self) -> bool:
        """Return whether velocity plot mode is currently active."""
        ...

    def show_mask_velocity_disabled_message(self) -> None:
        """Notify the user that mask editing is unavailable in velocity mode."""
        ...

    def show_mask_group_missing_message(self) -> None:
        """Notify the user that no maskable group is selected."""
        ...

    def emit_mask_selection_request(self, request: MaskSelectionRequest) -> None:
        """Emit a mask selection request."""
        ...

    def emit_mask_focus_changed(self, mask_id: str | None) -> None:
        """Emit a mask focus change."""
        ...

    def emit_mask_cancel_requested(self) -> None:
        """Emit a mask cancel request."""
        ...

    def refresh_mask_analysis_state(self) -> None:
        """Refresh export and stale styles after committed mask science."""
        ...

    def sync_active_mask_id(self, mask_id: str | None) -> None:
        """Synchronize the active mask identifier for legacy view state."""
        ...


class OptimizeMaskWorkflowController:
    """Coordinate optimize-mode mask selection, mutation, and rendering."""

    def __init__(
        self,
        *,
        port: OptimizeMaskWorkflowPort,
        mask_adapter: OptimizeMaskPanelAdapter,
        usecase: MaskMutationUseCase,
        history: MaskMutationHistoryRecorder,
        event_parent: QObject,
    ) -> None:
        """Initialize the controller.

        Args:
            port: View boundary used for UI updates and signal emission.
            mask_adapter: Adapter that applies concrete mask panel/model updates.
            usecase: Application use case that owns mask science transactions.
            history: Required forward-history recorder.
            event_parent: QObject parent for model event adapters.
        """
        self._port = port
        self._mask_adapter = mask_adapter
        self._usecase = usecase
        self._history = history
        self._event_parent = event_parent
        self._project: SpectroscopyProject | None = None
        self._model_event_adapter: SpectrumModelEventAdapter | None = None
        self._active_mask_id: str | None = None

    @property
    def active_mask_id(self) -> str | None:
        """Return the currently active mask identifier."""
        return self._active_mask_id

    def clear_active_mask(self) -> None:
        """Clear active mask focus without emitting focus signals."""
        self._set_active_mask_id(None)

    def attach_project(self, project: SpectroscopyProject | None) -> None:
        """Attach the controller to a project and its spectrum model.

        Args:
            project: Scientific project to mutate and observe, or ``None``.
        """
        self.detach_project()
        self._project = project
        if self._project is None:
            self._port.show_mask_group_masks([], None)
            return

        self._model_event_adapter = SpectrumModelEventAdapter(
            self._project.model, self._event_parent
        )
        self._model_event_adapter.masks_changed.connect(self.on_masks_changed)
        self.on_masks_changed()

    def detach_project(self) -> None:
        """Detach from the current project and model event adapter."""
        if self._model_event_adapter is not None:
            with contextlib.suppress(TypeError, RuntimeError):
                self._model_event_adapter.masks_changed.disconnect(self.on_masks_changed)
            self._model_event_adapter.close()
            self._model_event_adapter = None
        self._project = None

    def on_masks_changed(self) -> None:
        """Refresh rendered masks after the model mask collection changes."""
        if self._project is None:
            self._port.show_mask_group_masks([], None)
            self._set_active_mask_id(None)
            return

        model = self._project.model
        definitions = model.mask_definitions
        available_ids = {mask.identifier for mask in definitions}
        if self._active_mask_id not in available_ids:
            self._set_active_mask_id(None)

        group_id = self._port.current_mask_group_id()
        group_masks = model.get_masks_for_group(group_id) if group_id else []
        self._port.show_mask_group_masks(group_masks, self._active_mask_id)

    def update_panel_state(self, *, has_regions: bool) -> None:
        """Update mask panel availability for the current project state.

        Args:
            has_regions: Whether any editable absorption regions exist.
        """
        self._port.set_mask_panel_available(has_regions)
        if has_regions:
            return

        was_active = self._port.is_mask_interaction_active()
        self.cancel_selection()
        if was_active:
            self._port.emit_mask_cancel_requested()

    def request_add_mask(self) -> None:
        """Start a new mask selection request when the current state allows it."""
        if self._port.is_velocity_plot_active():
            self._port.show_mask_velocity_disabled_message()
            return

        if self._project is None:
            return

        group_id = self._port.current_mask_group_id()
        if not group_id:
            self._port.show_mask_group_missing_message()
            return

        self._port.expand_mask_panel()
        self._port.set_mask_interaction_active(True)
        self._port.emit_mask_selection_request(
            MaskSelectionRequest(
                selection_mode="create",
                group_id=group_id,
                mask_id=None,
                initial_range=None,
                existing_mask=None,
            )
        )

    def request_edit_mask(self, mask_id: str) -> None:
        """Start an edit request for an existing mask.

        Args:
            mask_id: Identifier of the mask to edit.
        """
        if self._port.is_velocity_plot_active():
            self._port.show_mask_velocity_disabled_message()
            return

        if self._project is None:
            return

        mask = self._project.model.find_mask(mask_id)
        if mask is None:
            return

        self._port.expand_mask_panel()
        self._port.set_mask_interaction_active(True)
        self._port.emit_mask_selection_request(
            MaskSelectionRequest(
                selection_mode="edit",
                group_id=mask.group_id,
                mask_id=mask_id,
                initial_range=(mask.wavelength_min, mask.wavelength_max),
                existing_mask=mask,
            )
        )

    def select_mask(self, mask_id: str | None) -> None:
        """Set active mask focus from a view selection.

        Args:
            mask_id: Selected mask identifier, or ``None``.
        """
        self._set_active_mask_id(mask_id)
        self._port.emit_mask_focus_changed(mask_id)

    def handle_selection_snapshot(
        self, snapshot: InteractionStateSnapshot[MaskSelectionContext]
    ) -> None:
        """Apply a mask selection snapshot emitted by the state controller.

        Args:
            snapshot: Snapshot describing the current mask selection lifecycle.
        """
        phase = snapshot.phase
        context = snapshot.context

        if phase is InteractionPhase.CANCELLED:
            self.cancel_selection()
            return

        if phase in (InteractionPhase.ARMED, InteractionPhase.ACTIVE):
            self._port.expand_mask_panel()
            self._port.set_mask_interaction_active(True)
            return

        if phase is not InteractionPhase.IDLE:
            return

        if context is None or context.result_mask is None:
            self.cancel_selection()
            return

        request: MaskMutationRequest
        if context.selection_mode == "edit":
            request = UpdateMaskRequest(mask=context.result_mask)
        else:
            request = CreateMaskRequest(mask=context.result_mask)
        self.apply_mutation(request)
        self.cancel_selection()

    def cancel_selection(self) -> None:
        """Cancel active mask selection UI state."""
        self._port.set_mask_interaction_active(False)

    def apply_mutation(self, request: MaskMutationRequest) -> MaskDefinition | None:
        """Apply a mask mutation and update view state.

        Args:
            request: Typed create, update, or remove request.

        Returns:
            Stored mask definition for upsert mutations, otherwise ``None``.
        """
        project = self._project
        if project is None:
            return None
        result = self._usecase.execute(project, request, history_recorder=self._history)
        if not result.changed:
            return result.stored_mask

        next_active_id = (
            result.stored_mask.identifier
            if result.stored_mask is not None
            else self._active_mask_id
        )
        if isinstance(request, RemoveMaskRequest) and request.mask_id == self._active_mask_id:
            next_active_id = None
        focus_changed = self._active_mask_id != next_active_id
        self._active_mask_id = next_active_id

        # Every collaborator below is post-commit. Failures are logged and
        # isolated from the accepted mask/revision/history transaction.
        actions: list[Callable[[], object]] = [
            lambda: self._port.sync_active_mask_id(next_active_id),
            project.model.notify_mask_storage_changed,
        ]
        if focus_changed:
            actions.append(lambda: self._port.emit_mask_focus_changed(next_active_id))
        if result.stored_mask is not None:
            actions.append(self._port.expand_mask_panel)
        actions.append(self._port.refresh_mask_analysis_state)
        run_postcommit_actions_isolated(*actions)
        return result.stored_mask

    def remove_mask(self, mask_id: str) -> None:
        """Remove a mask definition by identifier.

        Args:
            mask_id: Identifier of the mask to remove.
        """
        self.apply_mutation(RemoveMaskRequest(mask_id=mask_id))

    def change_mask_range(self, mask_id: str, start: float, end: float) -> None:
        """Apply a dragged range update to an existing mask.

        Args:
            mask_id: Identifier of the mask to update.
            start: New range start.
            end: New range end.
        """
        if self._project is None:
            return

        mask = self._project.model.find_mask(mask_id)
        if mask is None:
            return

        if end < start:
            start, end = end, start
        if end - start < MIN_MASK_WIDTH:
            end = start + MIN_MASK_WIDTH

        updated = mask.with_range(start, end)
        self.apply_mutation(UpdateMaskRequest(mask=updated))

    def _set_active_mask_id(self, mask_id: str | None) -> None:
        """Synchronize active mask identifier state.

        Args:
            mask_id: Active mask identifier, or ``None``.
        """
        self._active_mask_id = mask_id
        self._port.sync_active_mask_id(mask_id)
