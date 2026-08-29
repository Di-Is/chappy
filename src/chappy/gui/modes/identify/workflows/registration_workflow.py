"""Registration workflow for identify mode."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from chappy.application.analysis_artifacts import run_postcommit_actions_isolated
from chappy.application.history.snapshot_mapping import absorption_region_snapshot
from chappy.application.identify import (
    AtomicRegisterSelectedLinesRequest,
    AtomicRegisterSelectedLinesResult,
    BuildRegionPreviewsRequest,
    BuildRegionPreviewsUseCase,
    CandidateLineSnapshot,
    ExistingRegionSnapshot,
    RegistrationOutcome,
)
from chappy.core.absorption_display import format_region_display
from chappy.core.constants import LIGHT_SPEED_KMS
from chappy.core.editing_mode import FittingGroupCollection, FittingGroupSummary
from chappy.core.velocity_ranges import DEFAULT_IDENTIFY_MULTIPLET_GROUPING_TOLERANCE
from chappy.gui.modes.identify.application_adapters import (
    candidate_line_to_snapshot,
    region_preview_from_snapshot,
)
from chappy.gui.modes.identify.registration_controller import IdentifyRegistrationResult

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence
    from contextlib import AbstractContextManager

    from chappy.application.history import AbsorptionRegionSnapshot
    from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
    from chappy.core.change_set import ChangeSet
    from chappy.core.identify_state import CandidateLine, IdentifySessionState, RegionPreview
    from chappy.core.spectroscopy_project import SpectroscopyProject


class IdentifyRegistrationModeStatePort(Protocol):
    """Mode state operations required after registration."""

    @property
    def fitting_groups(self) -> Mapping[str, FittingGroupSummary]:
        """Return current fitting group summaries."""
        ...

    def set_fitting_groups(self, groups: FittingGroupCollection) -> ChangeSet:
        """Replace fitting group summaries."""
        ...


class IdentifyRegistrationHistoryRecorder(Protocol):
    """History operation required by registration confirmation."""

    def atomic_recording(self) -> AbstractContextManager[None]:
        """Return a rollback scope covering the complete history stack."""
        ...

    def record_ident_register_selected(
        self,
        project: SpectroscopyProject,
        created_line_ids: list[str],
        created_region_ids: list[str],
        _removed_system_ids: list[str],
        candidate_snapshots: tuple[CandidateLineSnapshot, ...],
        affected_region_ids: list[str],
        before_affected_region_snapshots: tuple[AbsorptionRegionSnapshot, ...],
    ) -> None:
        """Record identify registration confirmation."""
        ...


class IdentifyRegistrationUseCasePort(Protocol):
    """Atomic registration command consumed by the GUI workflow."""

    def register(
        self, request: AtomicRegisterSelectedLinesRequest
    ) -> AtomicRegisterSelectedLinesResult:
        """Commit one exact-preflighted registration command."""
        ...


@dataclass(frozen=True, slots=True)
class IdentifyRegistrationWorkflowMessages:
    """Translated messages emitted by registration workflow."""

    cannot_register_without_project: str
    no_candidates_to_register: str
    candidate_lines_could_not_register: str
    registered_template: str
    registered_details_template: str
    new_regions_template: str
    appended_template: str
    detail_separator: str
    multi_overlap_warning: str
    missing_atomic_template: str
    unknown: str


@dataclass(frozen=True, slots=True)
class IdentifyRegistrationWorkflowPorts:
    """External state required by identify registration workflow."""

    project_provider: Callable[[], SpectroscopyProject | None]
    session_provider: Callable[[], IdentifySessionState]
    mode_state_provider: Callable[[], IdentifyRegistrationModeStatePort | None]
    history_recorder_provider: Callable[[], IdentifyRegistrationHistoryRecorder | None]
    primary_members_provider: Callable[[], dict[str, tuple[str, ...]]]
    messages_provider: Callable[[], IdentifyRegistrationWorkflowMessages]


class IdentifyRegistrationWorkflow:
    """Build grouping results and register identify candidates immediately."""

    def __init__(
        self,
        ports: IdentifyRegistrationWorkflowPorts,
        preview_usecase: BuildRegionPreviewsUseCase,
        register_usecase: IdentifyRegistrationUseCasePort,
    ) -> None:
        """Initialize the workflow."""
        self._ports = ports
        self._preview_usecase = preview_usecase
        self._register_usecase = register_usecase

    def expand_multiplet_candidate_lines(self, selected_ids: Sequence[str]) -> list[str]:
        """Expand selected primary IDs to all multiplet member IDs."""
        primary_to_members = self._ports.primary_members_provider()
        expanded: list[str] = []
        seen: set[str] = set()

        for primary_id in selected_ids:
            if primary_id in primary_to_members:
                for member_id in primary_to_members[primary_id]:
                    if member_id not in seen:
                        expanded.append(member_id)
                        seen.add(member_id)
            elif primary_id not in seen:
                expanded.append(primary_id)
                seen.add(primary_id)

        return expanded

    def build_region_previews(self, systems: Sequence[CandidateLine]) -> list[RegionPreview]:
        """Build registration previews for candidate systems."""
        systems_list = list(systems)
        if not systems_list:
            return []

        result = self._preview_usecase.build(
            BuildRegionPreviewsRequest(
                candidates=tuple(candidate_line_to_snapshot(system) for system in systems_list),
                existing_regions=tuple(self._existing_region_snapshots()),
                multiplet_grouping_tolerance=DEFAULT_IDENTIFY_MULTIPLET_GROUPING_TOLERANCE,
                unknown_label=self._messages().unknown,
            )
        )
        return [region_preview_from_snapshot(preview) for preview in result.previews]

    def get_region_display_name(self, region: AbsorptionRegion) -> str:
        """Return dynamic display name for an existing absorption region."""
        project = self._ports.project_provider()
        if project is None:
            return region.region_id[:8]
        return self._get_region_display_name(project, region)

    def register_candidates(self, systems: Sequence[CandidateLine]) -> IdentifyRegistrationResult:
        """Register the given candidate systems immediately.

        Args:
            systems: Candidate systems selected for registration.

        Returns:
            Registration result with the typed outcome for status display.
        """
        project = self._ports.project_provider()
        session = self._ports.session_provider()
        messages = self._messages()
        if project is None:
            return IdentifyRegistrationResult(
                messages.cannot_register_without_project,
                refresh_workflow=False,
                refresh_candidates=False,
            )

        candidate_snapshots = tuple(candidate_line_to_snapshot(system) for system in systems)
        if not candidate_snapshots:
            return IdentifyRegistrationResult(
                messages.no_candidates_to_register,
                refresh_workflow=False,
                refresh_candidates=False,
            )

        history_recorder = self._ports.history_recorder_provider()
        before_region_snapshots = {
            region.region_id: absorption_region_snapshot(region)
            for region in project.list_absorption_regions()
        }

        def record_history(outcome: RegistrationOutcome) -> None:
            if history_recorder is None:
                return
            history_recorder.record_ident_register_selected(
                project,
                list(outcome.created_line_ids),
                list(outcome.created_region_ids),
                list(outcome.processed_system_ids),
                candidate_snapshots,
                list(outcome.affected_region_ids),
                tuple(
                    before_region_snapshots[region_id]
                    for region_id in outcome.affected_region_ids
                    if region_id in before_region_snapshots
                ),
            )

        result = self._register_usecase.register(
            AtomicRegisterSelectedLinesRequest(
                project=project,
                session=session,
                candidates=candidate_snapshots,
                existing_regions=tuple(self._existing_region_snapshots()),
                region_line_memberships=tuple(
                    (region.region_id, tuple(region.line_ids))
                    for region in project.list_absorption_regions()
                ),
                multiplet_grouping_tolerance=DEFAULT_IDENTIFY_MULTIPLET_GROUPING_TOLERANCE,
                unknown_label=messages.unknown,
                record_history=record_history if history_recorder is not None else None,
                history_scope=(
                    history_recorder.atomic_recording if history_recorder is not None else None
                ),
            )
        )

        if result.outcome is None:
            return IdentifyRegistrationResult(messages.candidate_lines_could_not_register)

        sync_lines = [
            line
            for line_id in result.mode_sync_line_ids
            if (line := project.find_absorption_line(line_id)) is not None
        ]
        run_postcommit_actions_isolated(
            lambda: self._synchronise_model_region_links(project, sync_lines),
            lambda: self._synchronise_mode_groups(project, sync_lines),
        )

        message = self._registration_status_message(project, result.outcome, messages)
        return IdentifyRegistrationResult(message, outcome=result.outcome)

    def _registration_status_message(
        self,
        project: SpectroscopyProject,
        outcome: RegistrationOutcome,
        messages: IdentifyRegistrationWorkflowMessages,
    ) -> str:
        """Format the typed registration outcome into a status message."""
        message = messages.registered_template.format(count=outcome.confirmed_count)

        details: list[str] = []
        # created_region_ids also carries the auto-created unassigned region; only
        # count created regions that actually received registered lines.
        new_region_count = len(set(outcome.created_region_ids) & set(outcome.affected_region_ids))
        if new_region_count:
            details.append(messages.new_regions_template.format(count=new_region_count))
        appended_names = [
            self._get_region_display_name(project, region)
            for region_id in outcome.appended_region_ids
            if (region := project.find_absorption_region(region_id)) is not None
        ]
        details.extend(messages.appended_template.format(region=name) for name in appended_names)
        if details:
            message += messages.registered_details_template.format(
                details=messages.detail_separator.join(details)
            )

        if outcome.multi_overlap_warning:
            message = f"{message} {messages.multi_overlap_warning}"
        if outcome.failed_count:
            warning = messages.missing_atomic_template.format(count=outcome.failed_count)
            message = f"{message} {warning}"
        return message

    def _existing_region_snapshots(self) -> list[ExistingRegionSnapshot]:
        """Return existing region snapshots for preview grouping."""
        project = self._ports.project_provider()
        if project is None:
            return []

        existing_lines = project.list_absorption_lines()
        snapshots: list[ExistingRegionSnapshot] = []
        for region in project.list_absorption_regions():
            line_ranges = tuple(
                line.lambda_range
                for line in existing_lines
                if line.region_id == region.region_id and line.lambda_range is not None
            )
            snapshots.append(
                ExistingRegionSnapshot(
                    region_id=region.region_id,
                    display_name=self._get_region_display_name(project, region),
                    line_ranges=line_ranges,
                )
            )
        return snapshots

    def _synchronise_model_region_links(
        self, project: SpectroscopyProject, lines: Iterable[AbsorptionLine]
    ) -> None:
        """Ensure model components mirror updated absorption region assignments."""
        for line in lines:
            if line.model_ids:
                project.assign_line_models_to_region(line)

    def _synchronise_mode_groups(
        self, project: SpectroscopyProject, lines: Iterable[AbsorptionLine]
    ) -> None:
        """Keep optimise-mode fitting groups aligned with identify results."""
        mode_state_store = self._ports.mode_state_provider()
        if mode_state_store is None:
            return

        grouped: defaultdict[str, list[tuple[AbsorptionRegion, AbsorptionLine]]] = defaultdict(
            list
        )

        for line in lines:
            absorption_region = (
                project.find_absorption_region(line.region_id)
                if line.region_id
                else project.ensure_absorption_unassigned_region()
            )
            if absorption_region is None:
                continue

            grouped[absorption_region.region_id].append((absorption_region, line))

        if not grouped:
            return

        existing_groups = dict(mode_state_store.fitting_groups)

        for group_name, members in grouped.items():
            wavelengths_min: list[float] = []
            wavelengths_max: list[float] = []
            absorber_names: list[str] = []
            system_ids: list[str] = []
            absorber_group = members[0][0]

            for _region, line in members:
                system_ids.append(line.line_id)
                low, high = self._line_wavelength_range(line)
                wavelengths_min.append(low)
                wavelengths_max.append(high)
                for model_id in line.model_ids:
                    component = project.find_absorber_component(model_id)
                    if component is not None:
                        absorber_names.append(component.name)

            entry = FittingGroupSummary(
                name=group_name,
                group_id=absorber_group.region_id,
                system_ids=tuple(system_ids),
                absorber_names=tuple(sorted(set(absorber_names))),
                wavelength_min=min(wavelengths_min),
                wavelength_max=max(wavelengths_max),
                color=absorber_group.display_color,
            )

            existing_groups[group_name] = entry

        mode_state_store.set_fitting_groups(existing_groups)

    def _line_wavelength_range(self, line: AbsorptionLine) -> tuple[float, float]:
        """Return an observed wavelength window for optimisation previews."""
        if line.lambda_range and len(line.lambda_range) == 2:
            low, high = line.lambda_range
            return (min(low, high), max(low, high))

        observed = line.observed_wavelength()
        if not math.isfinite(observed) or observed <= 0:
            msg = f"Invalid observed wavelength for absorption line {line.line_id}: {observed}"
            raise ValueError(msg)

        session = self._ports.session_provider()
        window_kms = (
            abs(line.window_kms)
            if line.window_kms
            else session.new_candidate_analysis_half_width.kms
        )
        if not math.isfinite(window_kms) or window_kms <= 0:
            return (observed, observed)

        delta = abs(observed * (window_kms / LIGHT_SPEED_KMS))
        if not math.isfinite(delta) or delta <= 0:
            return (observed, observed)

        start = observed - delta
        end = observed + delta
        return (min(start, end), max(start, end))

    def _get_region_display_name(
        self, project: SpectroscopyProject, region: AbsorptionRegion
    ) -> str:
        """Return dynamic display name for an existing absorption region."""
        lines = [
            project.absorption_lines[line_id]
            for line_id in region.line_ids
            if line_id in project.absorption_lines
        ]
        if not lines:
            return region.region_id[:8]
        display_info = format_region_display(lines, region.analysis_range)
        return display_info.display_name

    def _messages(self) -> IdentifyRegistrationWorkflowMessages:
        """Return translated registration workflow messages."""
        return self._ports.messages_provider()
