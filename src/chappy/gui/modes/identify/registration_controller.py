"""Identify-mode registration controller."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from chappy.application.analysis_artifacts import run_postcommit_actions_isolated

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from chappy.application.identify import RegistrationOutcome
    from chappy.core.identify_state import CandidateLine


class IdentifyRegistrationSessionPort(Protocol):
    """Session state required by identify registration routing."""

    @property
    def candidate_lines(self) -> Sequence[CandidateLine]:
        """Return temporary candidate lines."""
        ...


class IdentifyRegistrationWorkflowPort(Protocol):
    """Registration operations provided by identify workflow."""

    def expand_multiplet_candidate_lines(self, selected_ids: Sequence[str]) -> list[str]:
        """Expand selected primary ids to multiplet member ids."""
        ...

    def register_candidates(self, systems: Sequence[CandidateLine]) -> IdentifyRegistrationResult:
        """Register the given candidate systems immediately."""
        ...


type IdentifyRegistrationStatusCallback = Callable[[str], None]
type IdentifyRegistrationRefreshCallback = Callable[[], None]


@dataclass(frozen=True, slots=True)
class IdentifyRegistrationMessages:
    """User-facing registration messages supplied by the shell."""

    no_candidates: str
    no_selected_candidates: str


@dataclass(frozen=True, slots=True)
class IdentifyRegistrationResult:
    """Result of registering identify candidates."""

    message: str
    outcome: RegistrationOutcome | None = None
    refresh_workflow: bool = True
    refresh_candidates: bool = True

    @property
    def created_line_ids(self) -> tuple[str, ...]:
        """Expose registered line identifiers for outcome-oriented callers."""
        if self.outcome is None:
            return ()
        return self.outcome.created_line_ids


@dataclass(frozen=True, slots=True)
class IdentifyRegistrationPorts:
    """Shell callbacks required by identify registration routing."""

    session_provider: Callable[[], IdentifyRegistrationSessionPort]
    workflow_provider: Callable[[], IdentifyRegistrationWorkflowPort]
    status_callback: IdentifyRegistrationStatusCallback
    refresh_workflow_callback: IdentifyRegistrationRefreshCallback
    refresh_candidates_callback: IdentifyRegistrationRefreshCallback
    messages_provider: Callable[[], IdentifyRegistrationMessages]


class IdentifyRegistrationController:
    """Register identify candidates in a single immediate operation."""

    def __init__(self, ports: IdentifyRegistrationPorts) -> None:
        """Initialize the controller.

        Args:
            ports: Shell callbacks for session, workflow, status, and refresh.
        """
        self._ports = ports

    def register(
        self, selected_ids: Sequence[str] | None = None
    ) -> IdentifyRegistrationResult | None:
        """Register current or selected candidates immediately.

        Args:
            selected_ids: Optional primary candidate ids restricting the registration.
                When omitted or empty, all current candidates are registered.

        Returns:
            Typed successful registration result, or None when nothing was registered.
        """
        messages = self._ports.messages_provider()
        session = self._ports.session_provider()
        candidates = list(session.candidate_lines)
        if not candidates:
            self._ports.status_callback(messages.no_candidates)
            return None

        workflow = self._workflow()

        if selected_ids:
            expanded_ids = workflow.expand_multiplet_candidate_lines(selected_ids)
            selected_set = set(expanded_ids)
            target_systems = [system for system in candidates if system.system_id in selected_set]
            if not target_systems:
                self._ports.status_callback(messages.no_selected_candidates)
                return None
        else:
            target_systems = candidates

        result = workflow.register_candidates(tuple(target_systems))
        actions: list[Callable[[], object]] = [lambda: self._ports.status_callback(result.message)]
        if result.refresh_workflow:
            actions.append(self._ports.refresh_workflow_callback)
        if result.refresh_candidates:
            actions.append(self._ports.refresh_candidates_callback)
        run_postcommit_actions_isolated(*actions)
        if result.outcome is None or not result.outcome.created_line_ids:
            return None
        return result

    def _workflow(self) -> IdentifyRegistrationWorkflowPort:
        """Return the required registration workflow."""
        workflow = self._ports.workflow_provider()
        if workflow is None:
            msg = "Identify registration workflow is not configured."
            raise RuntimeError(msg)
        return workflow
