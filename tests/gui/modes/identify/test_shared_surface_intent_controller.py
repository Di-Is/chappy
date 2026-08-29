"""Tests for identify shared-spectrum velocity routing."""

from __future__ import annotations

from dataclasses import dataclass, field

from chappy.gui.modes.identify.shared_surface_intent_controller import (
    IdentifySharedSurfaceIntentController,
)


@dataclass
class _Workflow:
    """Minimal workflow exposing typed Shift-preview state."""

    verification_wavelength: float | None
    preview_lock: bool = False
    cleared_previews: int = 0
    manual_candidates: list[tuple[float, int, str]] = field(default_factory=list)

    def handle_manual_candidate(
        self, *, observed_wavelength: float, modifiers: int, source: str
    ) -> None:
        self.manual_candidates.append((observed_wavelength, modifiers, source))

    def set_preview_always_on(self, enabled: bool) -> None:
        self.preview_lock = enabled

    def preview_always_on(self) -> bool:
        return self.preview_lock

    def velocity_verification_wavelength(self) -> float | None:
        return self.verification_wavelength

    def clear_cursor_preview(self) -> None:
        self.cleared_previews += 1


def _controller(
    workflow: _Workflow,
) -> tuple[IdentifySharedSurfaceIntentController, list[float | None], list[str]]:
    toggles: list[float | None] = []
    pending: list[str] = []
    controller = IdentifySharedSurfaceIntentController(
        workflow_provider=lambda: workflow,
        velocity_toggle_callback=toggles.append,
        velocity_pending_callback=lambda: pending.append("pending"),
    )
    return controller, toggles, pending


def test_velocity_shortcut_uses_exact_shift_preview_wavelength() -> None:
    """An active typed Shift preview opens velocity at its exact observed cursor."""
    workflow = _Workflow(verification_wavelength=4527.125)
    controller, toggles, pending = _controller(workflow)

    controller.handle_mode_velocity_shortcut()

    assert toggles == [4527.125]
    assert pending == []
    assert workflow.cleared_previews == 1


def test_velocity_shortcut_without_valid_shift_preview_enters_pending() -> None:
    """Missing or invalid Shift preview preserves the V-then-click workflow."""
    workflow = _Workflow(verification_wavelength=None)
    controller, toggles, pending = _controller(workflow)

    controller.handle_mode_velocity_shortcut()

    assert toggles == []
    assert pending == ["pending"]
    assert workflow.cleared_previews == 0


def test_preview_lock_does_not_bypass_velocity_pending() -> None:
    """A forced preview lock is not an active Shift verification preview."""
    workflow = _Workflow(verification_wavelength=None, preview_lock=True)
    controller, toggles, pending = _controller(workflow)

    controller.handle_mode_velocity_shortcut()

    assert toggles == []
    assert pending == ["pending"]
    assert workflow.cleared_previews == 0
