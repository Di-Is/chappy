"""Candidate-line workflow controller for identify mode."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from chappy.application.identify import (
    CandidateCreationEntry,
    CandidateLineSnapshot,
    CreateCandidateFromVelocityUseCase,
)
from chappy.core.identify_state import CandidateLineContext
from chappy.core.velocity_ranges import LineAnalysisHalfWidth
from chappy.gui.modes.identify.application_adapters import (
    VelocityPreviewAdapter,
    build_cursor_preview_entries,
    candidate_line_to_snapshot,
    preview_entry_to_model,
)
from chappy.presentation.identify import PreviewEntry, preview_entry_to_plot_payload

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from chappy.core.atomic_data import AtomicLine
    from chappy.core.identify_state import CandidateLine, IdentifySessionState
    from chappy.core.velocity_ranges import NewCandidateAnalysisHalfWidth


class IdentifyCandidateHistoryRecorder(Protocol):
    """History operations required by identify candidate workflows."""

    def record_ident_add_candidate(
        self, session: IdentifySessionState, _added_system_ids: list[str]
    ) -> None:
        """Record identify candidate-line creation."""
        ...

    def record_ident_remove_candidate(
        self, _removed_system_ids: list[str], snapshots: tuple[CandidateLineSnapshot, ...]
    ) -> None:
        """Record identify candidate-line removal."""
        ...

    def record_ident_clear_candidates(self, snapshots: tuple[CandidateLineSnapshot, ...]) -> None:
        """Record clearing identify candidate lines."""
        ...


@dataclass(frozen=True, slots=True)
class IdentifyCandidateMessages:
    """Translated messages emitted by candidate workflows."""

    invalid_wavelength: str
    baseline_required: str
    no_lines_selected: str
    invalid_baseline: str
    limit_reached: str
    add_one_template: str
    add_many_template: str
    duplicate_partial_template: str
    duplicate_existing: str
    none_selected: str
    remove_failed: str
    remove_template: str
    none_to_clear: str
    cleared: str


@dataclass(frozen=True, slots=True)
class IdentifyCandidatePorts:
    """External state and callbacks required by candidate workflows."""

    session_provider: Callable[[], IdentifySessionState]
    identify_mode_active_provider: Callable[[], bool]
    baseline_line_provider: Callable[[], AtomicLine | None]
    current_lines_provider: Callable[[], list[AtomicLine]]
    observed_bounds_provider: Callable[[], tuple[float, float] | None]
    history_recorder_provider: Callable[[], IdentifyCandidateHistoryRecorder | None]
    primary_members_provider: Callable[[], dict[str, tuple[str, ...]]]
    status_callback: Callable[[str], None]
    refresh_workflow_callback: Callable[[], None]
    refresh_candidates_callback: Callable[[], None]
    clear_cursor_preview_callback: Callable[[], None]
    messages_provider: Callable[[], IdentifyCandidateMessages]
    shift_modifier_value_provider: Callable[[], int]
    tie_group_keys_provider: Callable[[], Mapping[str, str]]


@dataclass(slots=True)
class _IdentifyCandidateMutationAdapter:
    """Adapter that applies application candidate creation entries to core state."""

    session: IdentifySessionState

    @property
    def candidate_snapshots(self) -> tuple[CandidateLineSnapshot, ...]:
        """Return immutable snapshots of current core candidate lines."""
        return tuple(
            candidate_line_snapshot(candidate) for candidate in self.session.candidate_lines
        )

    def add_candidate_creation_entry(self, creation_entry: CandidateCreationEntry) -> str:
        """Add a candidate to core state from an application creation entry.

        Args:
            creation_entry: Application creation entry selected by the use case.

        Returns:
            Created candidate system ID.
        """
        entry = creation_entry.preview_entry
        context = CandidateLineContext(
            line_id=entry.line_id,
            rest_wavelength=entry.rest_wavelength,
            multiplet_id=entry.multiplet_id,
            multiplet_label=entry.multiplet_label,
            tie_group_key=entry.tie_group_key,
            transition_name=entry.transition_name,
            oscillator_strength=entry.oscillator_strength,
            gamma_value=entry.gamma_value,
            center_z=creation_entry.redshift,
        )
        system = self.session.add_candidate_line(
            entry.species,
            entry.lambda_min,
            entry.lambda_max,
            creation_method="manual",
            context=context,
            analysis_half_width=creation_entry.analysis_half_width,
        )
        return system.system_id


def candidate_line_snapshot(candidate: CandidateLine) -> CandidateLineSnapshot:
    """Convert a core candidate line to an application snapshot.

    Args:
        candidate: Mutable candidate line from identify session state.

    Returns:
        Immutable application candidate snapshot.
    """
    return candidate_line_to_snapshot(candidate)


class IdentifyCandidateController:
    """Manage manual candidate add, deletion, clearing, and history recording."""

    def __init__(
        self,
        ports: IdentifyCandidatePorts,
        creation_usecase: CreateCandidateFromVelocityUseCase,
        preview_adapter: VelocityPreviewAdapter,
    ) -> None:
        """Initialize the controller."""
        self._ports = ports
        self._creation_usecase = creation_usecase
        self._preview_adapter = preview_adapter

    def handle_manual_candidate(
        self, *, observed_wavelength: float, modifiers: int = 0, source: str = "click"
    ) -> None:
        """Create temporary system candidates at the given wavelength."""
        if not self._ports.identify_mode_active_provider():
            return

        del source

        shift_pressed = self._modifier_active(modifiers)
        if not shift_pressed:
            return

        session = self._ports.session_provider()
        session.last_click_wavelength = observed_wavelength

        if observed_wavelength <= 0:
            self._ports.status_callback(self._messages().invalid_wavelength)
            return

        prepared = self._prepare_candidate_entries(observed_wavelength, modifiers)
        if prepared is None:
            return

        _baseline_line, redshift, analysis_half_width, entries = prepared
        session.reference_z = redshift

        created_systems, duplicate_count, limit_reached = self.create_candidates_from_entries(
            entries, redshift=redshift, new_candidate_analysis_half_width=analysis_half_width
        )

        created_count = len(created_systems)
        if created_count:
            self._ports.refresh_workflow_callback()
            self._ports.refresh_candidates_callback()
            self._ports.clear_cursor_preview_callback()
            self._emit_manual_creation_message(created_systems)

        self._emit_duplicate_message(
            created_count=created_count,
            duplicate_count=duplicate_count,
            limit_reached=limit_reached,
        )

    def create_candidates_from_entries(
        self,
        entries: list[PreviewEntry],
        *,
        redshift: float,
        new_candidate_analysis_half_width: NewCandidateAnalysisHalfWidth,
    ) -> tuple[list[tuple[CandidateLine, PreviewEntry]], int, bool]:
        """Create temporary systems from prepared entry data."""
        analysis_half_width = LineAnalysisHalfWidth(new_candidate_analysis_half_width.kms)
        creation_entries = tuple(
            CandidateCreationEntry(
                preview_entry=preview_entry_to_model(entry),
                redshift=redshift,
                analysis_half_width=analysis_half_width,
            )
            for entry in entries
        )
        session = self._ports.session_provider()
        result = self._creation_usecase.create(
            _IdentifyCandidateMutationAdapter(session), creation_entries
        )
        if result.limit_reached:
            self._ports.status_callback(self._messages().limit_reached)

        candidate_by_id = {system.system_id: system for system in session.candidate_lines}
        created_systems: list[tuple[CandidateLine, PreviewEntry]] = []
        for created in result.created:
            system = candidate_by_id.get(created.system_id)
            if system is not None:
                created_systems.append((system, preview_entry_to_plot_payload(created.entry)))

        self._record_created_candidates(created_systems)
        return (created_systems, result.duplicate_count, result.limit_reached)

    def delete_candidates(self, system_ids: list[str]) -> None:
        """Remove selected temporary candidate lines."""
        if not system_ids:
            self._ports.status_callback(self._messages().none_selected)
            return

        session = self._ports.session_provider()
        expanded_ids = self._expand_multiplet_candidate_lines(system_ids)
        expanded_id_set = set(expanded_ids)
        snapshots = tuple(
            candidate_line_snapshot(candidate)
            for candidate in session.candidate_lines
            if candidate.system_id in expanded_id_set
        )

        removed = session.remove_candidate_lines(expanded_ids)
        if not removed:
            self._ports.status_callback(self._messages().remove_failed)
            return

        history_recorder = self._ports.history_recorder_provider()
        if history_recorder is not None and snapshots:
            history_recorder.record_ident_remove_candidate(removed, snapshots)

        message = self._messages().remove_template.format(count=len(removed))
        self._ports.status_callback(message)
        self._ports.refresh_workflow_callback()
        self._ports.refresh_candidates_callback()

    def clear_candidates(self) -> None:
        """Clear all temporary candidate lines."""
        session = self._ports.session_provider()
        if not session.candidate_lines:
            self._ports.status_callback(self._messages().none_to_clear)
            return

        snapshots = tuple(
            candidate_line_snapshot(candidate) for candidate in session.candidate_lines
        )

        session.clear_candidate_lines()

        history_recorder = self._ports.history_recorder_provider()
        if history_recorder is not None and snapshots:
            history_recorder.record_ident_clear_candidates(snapshots)

        self._ports.status_callback(self._messages().cleared)
        self._ports.refresh_workflow_callback()
        self._ports.refresh_candidates_callback()

    def _prepare_candidate_entries(
        self, observed_wavelength: float, modifiers: int
    ) -> tuple[AtomicLine, float, NewCandidateAnalysisHalfWidth, list[PreviewEntry]] | None:
        """Validate prerequisites and build preview entries for placement."""
        messages = self._messages()
        baseline_line = self._ports.baseline_line_provider()
        if baseline_line is None:
            self._ports.status_callback(messages.baseline_required)
            return None

        session = self._ports.session_provider()
        analysis_half_width = session.new_candidate_analysis_half_width

        lines = self._ports.current_lines_provider()
        if not lines:
            self._ports.status_callback(messages.no_lines_selected)
            return None

        rest_wavelength = baseline_line.wavelength_angstrom
        if rest_wavelength <= 0:
            self._ports.status_callback(messages.invalid_baseline)
            return None
        redshift = (observed_wavelength / rest_wavelength) - 1.0

        entries = build_cursor_preview_entries(
            preview_builder=self._preview_adapter,
            lines=tuple(lines),
            baseline_line=baseline_line,
            redshift=redshift,
            new_candidate_analysis_half_width=analysis_half_width,
            shift_pressed=self._modifier_active(modifiers),
            tie_group_keys=self._ports.tie_group_keys_provider(),
            data_bounds=self._ports.observed_bounds_provider(),
            for_preview=False,
        )

        if not entries:
            self._ports.status_callback(messages.no_lines_selected)
            return None

        return (baseline_line, redshift, analysis_half_width, entries)

    def _record_created_candidates(
        self, created_systems: list[tuple[CandidateLine, PreviewEntry]]
    ) -> None:
        """Record newly created candidate lines in history."""
        if not created_systems:
            return
        history_recorder = self._ports.history_recorder_provider()
        if history_recorder is None:
            return
        created_ids = [system.system_id for system, _entry in created_systems]
        history_recorder.record_ident_add_candidate(self._ports.session_provider(), created_ids)

    def _emit_manual_creation_message(
        self, created_systems: list[tuple[CandidateLine, PreviewEntry]]
    ) -> None:
        """Emit the manual candidate creation status message."""
        messages = self._messages()
        created_count = len(created_systems)
        if created_count == 1:
            _system, entry = created_systems[0]
            message = messages.add_one_template.format(
                species=entry["species"], start=entry["lambda_min"], end=entry["lambda_max"]
            )
        else:
            message = messages.add_many_template.format(count=created_count)
        self._ports.status_callback(message)

    def _emit_duplicate_message(
        self, *, created_count: int, duplicate_count: int, limit_reached: bool
    ) -> None:
        """Emit duplicate candidate feedback after a create request."""
        if duplicate_count and created_count:
            self._ports.status_callback(
                self._messages().duplicate_partial_template.format(
                    created=created_count, skipped=duplicate_count
                )
            )
        elif duplicate_count and not created_count and not limit_reached:
            self._ports.status_callback(self._messages().duplicate_existing)

    def _expand_multiplet_candidate_lines(self, primary_ids: list[str]) -> list[str]:
        """Expand selected primary IDs to all multiplet member IDs."""
        primary_to_members = self._ports.primary_members_provider()
        expanded: list[str] = []
        seen: set[str] = set()

        for primary_id in primary_ids:
            if primary_id in primary_to_members:
                for member_id in primary_to_members[primary_id]:
                    if member_id not in seen:
                        expanded.append(member_id)
                        seen.add(member_id)
            elif primary_id not in seen:
                expanded.append(primary_id)
                seen.add(primary_id)

        return expanded

    def _modifier_active(self, modifiers: int) -> bool:
        """Return True if the configured shift modifier bit is active."""
        return bool(modifiers & self._ports.shift_modifier_value_provider())

    def _messages(self) -> IdentifyCandidateMessages:
        """Return translated messages for candidate workflows."""
        return self._ports.messages_provider()
