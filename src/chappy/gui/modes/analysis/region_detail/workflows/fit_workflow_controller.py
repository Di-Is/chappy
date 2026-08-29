"""Controller for optimize fit workflow orchestration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from chappy.application.optimize import (
    FitResultApplication,
    FitResultPayload,
    FitResultRawPayload,
    FitResultStatusKind,
    FitWorkflowStatus,
    FitWorkflowStatusKind,
)

from .fit_outcome_messages import localized_primary_message

if TYPE_CHECKING:
    from chappy.core.analysis import FitSummary

__all__ = [
    "FitResultRawPayload",
    "FitWorkflowStatus",
    "FitWorkflowStatusKind",
    "OptimizeFitEditorPort",
    "OptimizeFitWorkflowController",
]


class OptimizeFitEditorPort(Protocol):
    """Optimize editor operations required by the fit workflow."""

    def is_fitting(self) -> bool:
        """Return whether a fit is currently running."""
        ...

    def start_fit(self) -> None:
        """Start fitting through the editor."""
        ...


class OptimizeFitWorkflowPort(Protocol):
    """Panel operations required by the fit workflow controller."""

    def should_enable_fit_workflow(self) -> bool:
        """Return whether fit execution is currently allowed."""
        ...

    def update_fit_button_workflow_state(self) -> None:
        """Refresh optimize button state for fit execution."""
        ...

    def current_fit_region_id(self) -> str | None:
        """Return the current Analysis region ID for fit result tracking."""
        ...

    def apply_fit_workflow_status(self, status: FitWorkflowStatus) -> None:
        """Apply a fit workflow status to the panel."""
        ...

    def has_fit_model_rows(self) -> bool:
        """Return whether model rows are visible."""
        ...

    def refresh_fit_model_rows(self) -> None:
        """Refresh model rows after a fit."""
        ...

    def refresh_successful_fit(self, group_id: str) -> None:
        """Refresh views after the editor atomically committed a successful fit."""
        ...


class FitResultPayloadParserPort(Protocol):
    """Parser boundary required by the fit workflow controller."""

    def parse(self, payload: FitResultRawPayload) -> FitResultPayload:
        """Parse a raw fit result payload."""
        ...


class ApplyFitResultUseCasePort(Protocol):
    """Fit-result application boundary required by the workflow controller."""

    def apply(
        self, payload: FitResultPayload, fit_statistics: FitSummary | None = None
    ) -> FitResultApplication:
        """Apply a normalized fit result payload."""
        ...


class OptimizeFitWorkflowController:
    """Coordinate optimize fit start and completion handling."""

    def __init__(
        self,
        editor: OptimizeFitEditorPort,
        port: OptimizeFitWorkflowPort,
        parser: FitResultPayloadParserPort,
        usecase: ApplyFitResultUseCasePort,
    ) -> None:
        """Initialize the controller.

        Args:
            editor: Fit editor port.
            port: Panel workflow port.
            parser: Fit result parser.
            usecase: Fit result use case.
        """
        self._editor = editor
        self._port = port
        self._parser = parser
        self._usecase = usecase
        self._running_fit_region_id: str | None = None

    def optimize_clicked(self) -> None:
        """Handle optimize button activation."""
        if self._editor.is_fitting() or not self._port.should_enable_fit_workflow():
            return
        self._editor.start_fit()

    def fit_started(self) -> None:
        """Handle fit-start signal from the editor."""
        self._running_fit_region_id = self._port.current_fit_region_id()
        self._port.apply_fit_workflow_status(FitWorkflowStatus(kind=FitWorkflowStatusKind.RUNNING))
        self._port.update_fit_button_workflow_state()

    def fit_completed(self, results: FitResultRawPayload) -> None:
        """Handle fit-completed signal from the editor.

        Args:
            results: Raw optimizer result payload from the editor boundary.
        """
        payload = self._parser.parse(results)
        application = self._usecase.apply(payload)
        self._apply_result_status(application)

        if self._port.has_fit_model_rows():
            self._port.refresh_fit_model_rows()

        self._port.update_fit_button_workflow_state()

        region_id = self._running_fit_region_id
        self._running_fit_region_id = None
        if region_id is None:
            return

        if payload.success:
            self._port.refresh_successful_fit(region_id)

    def _apply_result_status(self, application: FitResultApplication) -> None:
        """Apply result status to the panel port."""
        if application.status_kind is FitResultStatusKind.CHI2:
            self._port.apply_fit_workflow_status(
                FitWorkflowStatus(
                    kind=FitWorkflowStatusKind.CHI2,
                    value=application.status_value,
                    reduced_value=application.reduced_status_value,
                )
            )
        elif application.status_kind is FitResultStatusKind.CUSTOM:
            message = (
                localized_primary_message(application.outcome) or application.raw_message or ""
            )
            self._port.apply_fit_workflow_status(
                FitWorkflowStatus(kind=FitWorkflowStatusKind.CUSTOM, message=message)
            )
        else:
            self._port.apply_fit_workflow_status(
                FitWorkflowStatus(kind=FitWorkflowStatusKind(application.status_kind.value))
            )
