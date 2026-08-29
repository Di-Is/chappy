"""Tests for OptimizeSpectrumIntegration mask selection failure handling."""

from __future__ import annotations

from collections.abc import Callable
import pytest
from typing import TYPE_CHECKING, cast

from chappy.core.masking import MaskDefinition
from chappy.gui.modes.analysis.region_detail.spectrum_integration import (
    OptimizeSpectrumIntegration,
)
from chappy.gui.modes.analysis.region_detail.panel import RegionDetailPanel
from chappy.presentation.interaction.interaction_contracts import (
    MaskSelectionRequest,
    OptimizeLineSelectionChange,
    OptimizeMaskFocusChange,
    OptimizeMaskGroupChange,
)

if TYPE_CHECKING:
    from chappy.gui.spectrum.spectrum_interaction_coordinator import SpectrumInteractionCoordinator

type FakeSignalPayload = (
    MaskSelectionRequest
    | OptimizeLineSelectionChange
    | OptimizeMaskFocusChange
    | OptimizeMaskGroupChange
)


class FakeSignal:
    """Small signal stand-in that records connected slots and can emit payloads."""

    def __init__(self) -> None:
        self._slots: list[Callable[..., None]] = []

    def connect(self, slot: Callable[..., None]) -> None:
        """Register a slot for later emission."""
        self._slots.append(slot)

    def emit(self, *args: FakeSignalPayload) -> None:
        """Invoke all connected slots with the supplied payload."""
        for slot in self._slots:
            slot(*args)


class RecordingOptimizePanel:
    """Optimize panel fake that exposes the public signal surface used by integration."""

    def __init__(self) -> None:
        self.line_selected = FakeSignal()
        self.mask_selection_requested = FakeSignal()
        self.mask_focus_changed = FakeSignal()
        self.mask_cancel_requested = FakeSignal()
        self.mask_group_changed = FakeSignal()
        self.cancel_count = 0
        self._current_region_id = "test_group"
        self.mask_definitions: dict[str, MaskDefinition] = {}

    def add_model_at_wavelength(self, _wavelength: float) -> None:
        """Accept model-add signal connections from OptimizeSpectrumIntegration."""

    def cancel_mask_selection(self) -> None:
        """Record that the panel was reset after a failed request."""
        self.cancel_count += 1

    def get_mask_definition(self, mask_id: str | None) -> MaskDefinition | None:
        """Return a stored mask definition if the requested mask exists."""
        if mask_id is None:
            return None
        return self.mask_definitions.get(mask_id)

    def current_region_id(self) -> str | None:
        """Return the current Analysis region identifier."""
        return self._current_region_id


class PresenterView:
    """Minimal presenter view for integration construction."""

    spectrum_input_adapter: None = None


class RecordingSpectrumInteractionCoordinator:
    """Presenter fake that records mask interaction and current-region changes."""

    def __init__(self) -> None:
        self.view = PresenterView()
        self.request_result = True
        self.last_mask_request: MaskSelectionRequest | None = None
        self.active_mask_group: str | None = None
        self.selected_absorbers: set[str] | None = None
        self.highlighted_mask_id: str | None = None
        self.cancel_count = 0
        self.velocity_visible = False
        self.toggle_count = 0
        self.raise_on_set_active_mask_group: set[str | None] = set()
        self.raise_on_highlight_mask_for: set[str | None] = set()
        self.raise_on_cancel_mask_selection = False

    def set_absorber_drag_candidates(self, absorber_ids: set[str] | None) -> None:
        """Record selected absorber ids."""
        self.selected_absorbers = absorber_ids

    def request_mask_selection_interaction(self, request: MaskSelectionRequest) -> bool:
        """Record the request and return the configured interaction outcome."""
        self.last_mask_request = request
        return self.request_result

    def highlight_mask(self, mask_id: str | None) -> None:
        """Record mask highlight requests."""
        if mask_id in self.raise_on_highlight_mask_for:
            msg = f"highlight mask request failed for {mask_id}"
            raise RuntimeError(msg)
        self.highlighted_mask_id = mask_id

    def set_active_mask_group(self, group_id: str | None) -> None:
        """Record active mask group synchronization from the panel."""
        if group_id in self.raise_on_set_active_mask_group:
            msg = f"set active mask group failed for {group_id}"
            raise RuntimeError(msg)
        self.active_mask_group = group_id

    def cancel_mask_selection(self) -> None:
        """Record spectrum-side cancellation requests."""
        if self.raise_on_cancel_mask_selection:
            raise RuntimeError("cancel mask selection failed")
        self.cancel_count += 1

    def context_menu_parent_widget(self) -> PresenterView:
        """Return context-menu parent fake."""
        return self.view

    def is_velocity_overlay_visible(self) -> bool:
        """Return configured velocity overlay state."""
        return self.velocity_visible

    def toggle_velocity_plot(self) -> None:
        """Record optimize velocity toggle requests."""
        self.toggle_count += 1


def _build_integration(
    presenter: RecordingSpectrumInteractionCoordinator, panel: RecordingOptimizePanel
) -> OptimizeSpectrumIntegration:
    """Create integration while keeping the fake boundary explicit."""
    return OptimizeSpectrumIntegration(
        spectrum_interaction_coordinator=cast("SpectrumInteractionCoordinator", presenter),
        optimize_panel=cast(RegionDetailPanel, panel),
        velocity_visible_provider=lambda: presenter.velocity_visible,
        velocity_toggle_callback=lambda: setattr(
            presenter, "toggle_count", presenter.toggle_count + 1
        ),
        cursor_feedback_callback=lambda _cursor_mode: None,
    )


def test_channel_mutex_rejection_resets_panel_state() -> None:
    """When channel mutex rejects a valid request, the panel exits mask selection."""
    presenter = RecordingSpectrumInteractionCoordinator()
    presenter.request_result = False
    panel = RecordingOptimizePanel()
    _build_integration(presenter, panel)

    panel.mask_selection_requested.emit(
        MaskSelectionRequest(
            selection_mode="create",
            group_id="test_group",
            mask_id=None,
            initial_range=None,
            existing_mask=None,
        )
    )

    assert panel.cancel_count == 1
    assert presenter.last_mask_request is not None
    assert presenter.last_mask_request.selection_mode == "create"
    assert presenter.last_mask_request.group_id == "test_group"


def test_initial_group_sync_uses_typed_group_event() -> None:
    """Integration should sync the panel's active mask group on construction."""
    presenter = RecordingSpectrumInteractionCoordinator()
    panel = RecordingOptimizePanel()
    _build_integration(presenter, panel)

    assert presenter.active_mask_group == "test_group"


def test_focus_changed_propagates_highlight_failure() -> None:
    """Mask focus change should propagate highlight failure from spectrum interaction facade."""
    presenter = RecordingSpectrumInteractionCoordinator()
    presenter.raise_on_highlight_mask_for.add("broken-mask")
    panel = RecordingOptimizePanel()
    _build_integration(presenter, panel)

    with pytest.raises(RuntimeError, match="highlight mask request failed for broken-mask"):
        panel.mask_focus_changed.emit(OptimizeMaskFocusChange(mask_id="broken-mask"))


def test_group_changed_propagates_region_activation_failure() -> None:
    """Mask group change should propagate active mask group synchronization failure."""
    presenter = RecordingSpectrumInteractionCoordinator()
    presenter.raise_on_set_active_mask_group.add("broken-group")
    panel = RecordingOptimizePanel()
    _build_integration(presenter, panel)

    with pytest.raises(RuntimeError, match="set active mask group failed for broken-group"):
        panel.mask_group_changed.emit(OptimizeMaskGroupChange(group_id="broken-group"))


def test_cancel_mask_selection_propagates_cancel_facade_failure() -> None:
    """Cancellation failure in facade should be propagated as exception."""
    presenter = RecordingSpectrumInteractionCoordinator()
    presenter.raise_on_cancel_mask_selection = True
    panel = RecordingOptimizePanel()
    _build_integration(presenter, panel)

    with pytest.raises(RuntimeError, match="cancel mask selection failed"):
        integration = _build_integration(presenter, panel)
        integration.cancel_mask_selection()


def test_cancel_mask_selection_propagates_highlight_none_failure() -> None:
    """Cancellation should propagate failures when clearing highlight with None."""
    presenter = RecordingSpectrumInteractionCoordinator()
    presenter.raise_on_highlight_mask_for.add(None)
    panel = RecordingOptimizePanel()
    integration = _build_integration(presenter, panel)

    with pytest.raises(RuntimeError, match="highlight mask request failed for None"):
        integration.cancel_mask_selection()
