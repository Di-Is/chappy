"""Tests for optimize fit workflow controller."""

from __future__ import annotations

from chappy.application.optimize import (
    FitResultApplication,
    FitResultPayload,
    FitResultRawPayload,
    FitResultStatusKind,
    FitWorkflowStatus,
    FitWorkflowStatusKind,
)
from chappy.core.analysis import FitSummary
from chappy.gui.modes.analysis.region_detail.workflows.fit_outcome_messages import (
    localized_primary_message,
)
from chappy.gui.modes.analysis.region_detail.workflows.fit_workflow_controller import (
    OptimizeFitWorkflowController,
)


class _Editor:
    """Fit editor test double."""

    def __init__(self) -> None:
        self.fitting = False
        self.start_count = 0

    def is_fitting(self) -> bool:
        """Return configured running state."""
        return self.fitting

    def start_fit(self) -> None:
        """Record fit start requests."""
        self.start_count += 1


class _Port:
    """Fit workflow port test double."""

    def __init__(self) -> None:
        self.enabled = True
        self.current_region_id: str | None = "region-1"
        self.has_rows = True
        self.button_refresh_count = 0
        self.statuses: list[FitWorkflowStatus] = []
        self.refresh_count = 0
        self.successful_fit_refreshes: list[str] = []

    def should_enable_fit_workflow(self) -> bool:
        """Return configured enablement."""
        return self.enabled

    def update_fit_button_workflow_state(self) -> None:
        """Record button state refresh requests."""
        self.button_refresh_count += 1

    def current_fit_region_id(self) -> str | None:
        """Return the configured current Analysis region."""
        return self.current_region_id

    def apply_fit_workflow_status(self, status: FitWorkflowStatus) -> None:
        """Record workflow status updates."""
        self.statuses.append(status)

    def has_fit_model_rows(self) -> bool:
        """Return configured row presence."""
        return self.has_rows

    def refresh_fit_model_rows(self) -> None:
        """Record row refreshes."""
        self.refresh_count += 1

    def refresh_successful_fit(self, group_id: str) -> None:
        """Record successful post-commit refreshes."""
        self.successful_fit_refreshes.append(group_id)


class _Parser:
    """Fit result parser test double."""

    def __init__(self, payload: FitResultPayload) -> None:
        self.payload = payload
        self.parsed_payloads: list[FitResultRawPayload] = []

    def parse(self, payload: FitResultRawPayload) -> FitResultPayload:
        """Record and return configured result payload."""
        self.parsed_payloads.append(payload)
        return self.payload


class _UseCase:
    """Fit result use case test double."""

    def __init__(self) -> None:
        self.applications: list[FitResultApplication] = [
            FitResultApplication(
                status_kind=FitResultStatusKind.CHI2,
                status_value=1.5,
                reduced_status_value=0.75,
                raw_message=None,
                summary=None,
                analysis_ready=False,
            )
        ]
        self.calls: list[tuple[FitResultPayload, FitSummary | None]] = []

    def apply(
        self, payload: FitResultPayload, fit_statistics: FitSummary | None = None
    ) -> FitResultApplication:
        """Record payload application requests."""
        self.calls.append((payload, fit_statistics))
        return self.applications[len(self.calls) - 1]


def test_optimize_clicked_starts_editor_when_enabled() -> None:
    """Optimize click requests a fit; running state follows the editor's fit_started."""
    editor = _Editor()
    port = _Port()
    controller = OptimizeFitWorkflowController(
        editor, port, parser=_Parser(FitResultPayload(success=True)), usecase=_UseCase()
    )

    controller.optimize_clicked()

    assert editor.start_count == 1
    assert port.button_refresh_count == 0


def test_fit_completed_applies_success_and_marks_group_ready() -> None:
    """Successful fit completion should refresh rows and mark the fitted region ready."""
    editor = _Editor()
    port = _Port()
    payload = FitResultPayload(success=True, chi_squared=1.5, reduced_chi_squared=0.75)
    parser = _Parser(payload)
    usecase = _UseCase()
    controller = OptimizeFitWorkflowController(editor, port, parser=parser, usecase=usecase)

    controller.fit_started()
    controller.fit_completed({"success": True})

    assert port.statuses == [
        FitWorkflowStatus(kind=FitWorkflowStatusKind.RUNNING),
        FitWorkflowStatus(kind=FitWorkflowStatusKind.CHI2, value=1.5, reduced_value=0.75),
    ]
    assert port.refresh_count == 1
    assert port.button_refresh_count == 2
    assert parser.parsed_payloads == [{"success": True}]
    assert usecase.calls == [(payload, None)]
    assert port.successful_fit_refreshes == ["region-1"]


def test_failed_fit_leaves_analysis_state_unchanged() -> None:
    """A failed or cancelled optimizer result must not invalidate prior evidence."""
    editor = _Editor()
    port = _Port()
    payload = FitResultPayload(success=False)
    parser = _Parser(payload)
    usecase = _UseCase()
    controller = OptimizeFitWorkflowController(editor, port, parser=parser, usecase=usecase)

    controller.fit_started()
    controller.fit_completed({"success": False})

    assert usecase.calls == [(payload, None)]
    assert port.successful_fit_refreshes == []


def test_successful_fit_completion_does_not_commit_evidence_again() -> None:
    """The post-commit controller should only refresh already committed evidence."""
    editor = _Editor()
    port = _Port()
    payload = FitResultPayload(success=True)
    parser = _Parser(payload)
    usecase = _UseCase()
    controller = OptimizeFitWorkflowController(editor, port, parser=parser, usecase=usecase)

    controller.fit_started()
    controller.fit_completed({"success": True})

    assert usecase.calls == [(payload, None)]
    assert port.successful_fit_refreshes == ["region-1"]


class _CustomUseCase:
    """Use case double returning a fixed CUSTOM application."""

    def __init__(self, *, outcome: str | None, raw_message: str | None) -> None:
        self._application = FitResultApplication(
            status_kind=FitResultStatusKind.CUSTOM,
            status_value=None,
            reduced_status_value=None,
            raw_message=raw_message,
            summary=None,
            analysis_ready=False,
            outcome=outcome,
        )

    def apply(
        self, payload: FitResultPayload, fit_statistics: FitSummary | None = None
    ) -> FitResultApplication:
        """Return the fixed CUSTOM application."""
        return self._application


def test_localized_primary_message_maps_non_applied_only() -> None:
    """Only non-applied outcomes have a localized primary line."""
    assert localized_primary_message("degenerate") is not None
    assert localized_primary_message("no_free_params") is not None
    assert localized_primary_message("converged") is None
    assert localized_primary_message(None) is None


def test_custom_status_uses_localized_outcome_message() -> None:
    """A non-applied outcome surfaces its localized message, not the raw optimizer text."""
    editor = _Editor()
    port = _Port()
    parser = _Parser(FitResultPayload(success=False, outcome="degenerate"))
    usecase = _CustomUseCase(outcome="degenerate", raw_message="raw optimizer text")
    controller = OptimizeFitWorkflowController(editor, port, parser=parser, usecase=usecase)

    controller.fit_completed({"success": False, "outcome": "degenerate"})

    custom = port.statuses[-1]
    assert custom.kind is FitWorkflowStatusKind.CUSTOM
    assert custom.message == localized_primary_message("degenerate")
    assert custom.message != "raw optimizer text"


def test_custom_status_falls_back_to_raw_message_for_unmapped_outcome() -> None:
    """An unmapped outcome keeps the raw optimizer message."""
    editor = _Editor()
    port = _Port()
    parser = _Parser(FitResultPayload(success=False))
    usecase = _CustomUseCase(outcome=None, raw_message="raw optimizer text")
    controller = OptimizeFitWorkflowController(editor, port, parser=parser, usecase=usecase)

    controller.fit_completed({"success": False})

    assert port.statuses[-1].message == "raw optimizer text"
