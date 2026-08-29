"""Tests for mask interaction controller fail-fast boundaries."""

from __future__ import annotations

import pytest

from chappy.gui.spectrum.mask_interaction_controller import SpectrumMaskInteractionController
from chappy.presentation.interaction.interaction_contracts import MaskSelectionRequest


class _Interactor:
    """Record mask selection interactor calls."""

    def __init__(self) -> None:
        self.begin_requests: list[MaskSelectionRequest] = []
        self.cancel_reasons: list[str | None] = []
        self.fail_begin = False
        self.fail_cancel = False

    def begin_mask_selection_interaction(self, request: MaskSelectionRequest) -> bool:
        """Record a begin request."""
        if self.fail_begin:
            raise RuntimeError("begin failed")
        self.begin_requests.append(request)
        return True

    def cancel_mask_selection_interaction(self, *, reason: str | None = None) -> bool:
        """Record a cancel request."""
        if self.fail_cancel:
            raise RuntimeError("cancel failed")
        self.cancel_reasons.append(reason)
        return True


class _PlotHost:
    """Record mask overlay plot calls."""

    def __init__(self) -> None:
        self.highlighted_masks: list[str | None] = []
        self.current_regions: list[str | None] = []
        self.fail_highlight = False
        self.fail_group = False

    def highlight_mask(self, mask_id: str | None) -> None:
        """Record a highlight request."""
        if self.fail_highlight:
            raise RuntimeError("highlight failed")
        self.highlighted_masks.append(mask_id)

    def set_active_mask_group(self, group_id: str | None) -> None:
        """Record a current Analysis region request."""
        if self.fail_group:
            raise RuntimeError("group failed")
        self.current_regions.append(group_id)


def _request() -> MaskSelectionRequest:
    """Return a representative mask selection request."""
    return MaskSelectionRequest(
        mask_id="mask-1",
        group_id="group-1",
        initial_range=None,
        existing_mask=None,
        selection_mode="replace",
    )


def test_request_mask_selection_requires_interactor() -> None:
    """Missing mask interactor is a composition error."""
    controller = SpectrumMaskInteractionController(
        interactor_provider=lambda: None,
        plot_host_provider=lambda: _PlotHost(),
        integration_provider=lambda: None,
        snapshot_callback=lambda _snapshot: None,
    )

    with pytest.raises(RuntimeError, match="interactor is required"):
        controller.request_mask_selection_interaction(_request())


def test_request_mask_selection_propagates_interactor_failure() -> None:
    """Interactor failures should not be converted to a false no-op."""
    interactor = _Interactor()
    interactor.fail_begin = True
    controller = SpectrumMaskInteractionController(
        interactor_provider=lambda: interactor,
        plot_host_provider=lambda: _PlotHost(),
        integration_provider=lambda: None,
        snapshot_callback=lambda _snapshot: None,
    )

    with pytest.raises(RuntimeError, match="begin failed"):
        controller.request_mask_selection_interaction(_request())


def test_mask_plot_operations_require_plot_host() -> None:
    """Mask overlay commands require the plot host dependency."""
    controller = SpectrumMaskInteractionController(
        interactor_provider=lambda: _Interactor(),
        plot_host_provider=lambda: None,
        integration_provider=lambda: None,
        snapshot_callback=lambda _snapshot: None,
    )

    with pytest.raises(RuntimeError, match="plot host is required"):
        controller.highlight_mask("mask-1")
    with pytest.raises(RuntimeError, match="plot host is required"):
        controller.set_active_mask_group("group-1")


def test_mask_plot_operation_failures_propagate() -> None:
    """Plot host failures should not be logged and hidden."""
    plot_host = _PlotHost()
    controller = SpectrumMaskInteractionController(
        interactor_provider=lambda: _Interactor(),
        plot_host_provider=lambda: plot_host,
        integration_provider=lambda: None,
        snapshot_callback=lambda _snapshot: None,
    )

    plot_host.fail_highlight = True
    with pytest.raises(RuntimeError, match="highlight failed"):
        controller.highlight_mask("mask-1")

    plot_host.fail_group = True
    with pytest.raises(RuntimeError, match="group failed"):
        controller.set_active_mask_group("group-1")


def test_cancel_mask_selection_requires_interactor() -> None:
    """Missing interactor during cancel is a composition error."""
    controller = SpectrumMaskInteractionController(
        interactor_provider=lambda: None,
        plot_host_provider=lambda: _PlotHost(),
        integration_provider=lambda: None,
        snapshot_callback=lambda _snapshot: None,
    )

    with pytest.raises(RuntimeError, match="interactor is required"):
        controller.cancel_mask_selection()


def test_cancel_mask_selection_propagates_interactor_failure() -> None:
    """Cancel failures should not be hidden."""
    interactor = _Interactor()
    interactor.fail_cancel = True
    controller = SpectrumMaskInteractionController(
        interactor_provider=lambda: interactor,
        plot_host_provider=lambda: _PlotHost(),
        integration_provider=lambda: None,
        snapshot_callback=lambda _snapshot: None,
    )

    with pytest.raises(RuntimeError, match="cancel failed"):
        controller.cancel_mask_selection()
