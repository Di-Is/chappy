"""Use cases for identify candidate registration preparation."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from chappy.application.identify.grouping import UnionFind
from chappy.application.identify.models import (
    AbsorptionLineRegistrationRequest,
    AbsorptionLineRegistrationResult,
    BuildRegionAssignmentRequest,
    BuildRegionAssignmentResult,
    BuildRegionPreviewsRequest,
    BuildRegionPreviewsResult,
    BuildRegistrationOutcomeRequest,
    CandidateLineSnapshot,
    ExistingRegionSnapshot,
    IdentifyRegistrationImpactPreview,
    IdentifyRegistrationMultipletGroup,
    IdentifyRegistrationPlan,
    RegionAssignmentOperation,
    RegionAssignmentOperationKind,
    RegionPreviewSnapshot,
    RegisteredLineReference,
    RegisteredLineState,
    RegistrationErrorCode,
    RegistrationOutcome,
)
from chappy.application.structure.models import StructureMutationOutcome
from chappy.core.absorption.models import UNASSIGNED_REGION_ID
from chappy.core.absorption.multiplet_service import setup_multiplet_cross_references
from chappy.core.constants import LIGHT_SPEED_KMS

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
    from chappy.core.velocity_ranges import MultipletGroupingVelocityTolerance


class IdentifyProjectMutationPort(Protocol):
    """Project operations required by identify registration."""

    def add_absorption_line(  # noqa: PLR0913 - project API exposes explicit fields
        self,
        *,
        species: str,
        rest_wavelength: float,
        center_z: float,
        window_kms: float,
        multiplet_label: str,
        transition_name: str,
        oscillator_strength: float,
        gamma_value: float,
        lambda_range: tuple[float, float] | None,
        region_id: str | None = None,
        multiplet_ids: Sequence[str] | None = None,
        created_by: str = "identify",
    ) -> AbsorptionLine:
        """Register one absorption line."""

    def find_absorption_region(self, region_id: str) -> AbsorptionRegion | None:
        """Return an absorption region by ID."""

    def assign_line_to_region(self, line_id: str, region_id: str | None) -> None:
        """Assign one line to a region."""

    def create_region_with_lines(self, line_ids: Sequence[str]) -> AbsorptionRegion:
        """Create a region with line IDs."""

    def ensure_absorption_unassigned_region(self) -> AbsorptionRegion:
        """Ensure the unassigned absorption region exists."""

    def list_absorption_regions(self) -> list[AbsorptionRegion]:
        """Return current absorption regions."""


class RegistrationSessionCleanupPort(Protocol):
    """Session operations required by identify registration."""

    def remove_candidate_lines(self, system_ids: Iterable[str]) -> list[str]:
        """Remove processed candidate lines."""


@dataclass(frozen=True, slots=True)
class RegisterSelectedLinesRequest:
    """Request for registering selected identify candidates."""

    project: IdentifyProjectMutationPort
    session: RegistrationSessionCleanupPort
    plan: IdentifyRegistrationPlan


@dataclass(frozen=True, slots=True)
class RegisterSelectedLinesResult:
    """Result of confirming selected identify candidates."""

    outcome: RegistrationOutcome | None
    mode_sync_line_ids: tuple[str, ...]


class BuildAbsorptionLineRegistrationRequestUseCase:
    """Build typed absorption line creation data from a candidate line."""

    def build(self, candidate: CandidateLineSnapshot) -> AbsorptionLineRegistrationResult:
        """Build an absorption line registration request.

        Args:
            candidate: Candidate line selected for registration.

        Returns:
            Registration request result. The request is None when required atomic data is
            invalid.
        """
        if candidate.rest_wavelength <= 0:
            return AbsorptionLineRegistrationResult(
                request=None, error_code=RegistrationErrorCode.INVALID_REST_WAVELENGTH
            )

        request = AbsorptionLineRegistrationRequest(
            system_id=candidate.system_id,
            atomic_line_id=candidate.line_id,
            species=candidate.species,
            rest_wavelength=candidate.rest_wavelength,
            center_z=candidate.center_z,
            window_kms=candidate.analysis_half_width.kms,
            multiplet_label=candidate.multiplet_label,
            transition_name=candidate.transition_name,
            oscillator_strength=candidate.oscillator_strength,
            gamma_value=candidate.gamma_value,
            lambda_range=(candidate.lambda_min, candidate.lambda_max),
            created_by=candidate.creation_method,
        )
        return AbsorptionLineRegistrationResult(request=request)


class BuildIdentifyRegistrationPlanUseCase:
    """Normalize candidate registration decisions into one immutable plan."""

    def __init__(self) -> None:
        """Create pure planning dependencies."""
        self._line_request_usecase = BuildAbsorptionLineRegistrationRequestUseCase()
        self._region_preview_usecase = BuildRegionPreviewsUseCase()

    def build(self, request: BuildRegionPreviewsRequest) -> IdentifyRegistrationPlan:
        """Build a plan shared by side-effect-free preview and registration mutation."""
        normalized_candidates = request.candidates
        normalized_system_ids = tuple(candidate.system_id for candidate in normalized_candidates)
        if len(normalized_system_ids) != len(set(normalized_system_ids)):
            msg = "Identify registration candidate identities must be unique."
            raise ValueError(msg)

        existing_region_ids = tuple(region.region_id for region in request.existing_regions)
        if len(existing_region_ids) != len(set(existing_region_ids)):
            msg = "Identify registration region snapshot identities must be unique."
            raise ValueError(msg)

        registerable_candidates: list[CandidateLineSnapshot] = []
        registration_requests: list[AbsorptionLineRegistrationRequest] = []
        rejected_system_ids: list[str] = []
        for candidate in normalized_candidates:
            prepared = self._line_request_usecase.build(candidate)
            if prepared.request is None:
                rejected_system_ids.append(candidate.system_id)
            else:
                registerable_candidates.append(candidate)
                registration_requests.append(prepared.request)

        previews = self._region_preview_usecase.build(request).previews
        registerable_system_ids = tuple(
            candidate.system_id for candidate in registerable_candidates
        )
        registerable_id_set = set(registerable_system_ids)
        impactful_previews = tuple(
            preview
            for preview in previews
            if registerable_id_set.intersection(preview.member_system_ids)
        )
        affected_existing_region_id_set = {
            preview.existing_group_id
            for preview in impactful_previews
            if preview.existing_group_id is not None
        }
        affected_existing_region_ids = tuple(
            region_id
            for region_id in existing_region_ids
            if region_id in affected_existing_region_id_set
        )
        changed = bool(registerable_candidates)
        created_region_count = 0
        if changed:
            created_region_count = sum(
                preview.existing_group_id is None for preview in impactful_previews
            )
            if UNASSIGNED_REGION_ID not in existing_region_ids:
                created_region_count += 1

        grouped_system_ids: dict[str, list[str]] = defaultdict(list)
        for candidate in registerable_candidates:
            if candidate.tie_group_key:
                grouped_system_ids[candidate.tie_group_key].append(candidate.system_id)
        multiplet_groups = tuple(
            IdentifyRegistrationMultipletGroup(
                tie_group_key=tie_group_key, system_ids=tuple(system_ids)
            )
            for tie_group_key, system_ids in grouped_system_ids.items()
            if len(system_ids) >= 2
        )
        impact = IdentifyRegistrationImpactPreview(
            mutation_outcome=(
                StructureMutationOutcome.CHANGED if changed else StructureMutationOutcome.NO_CHANGE
            ),
            normalized_system_ids=normalized_system_ids,
            registerable_system_ids=registerable_system_ids,
            rejected_system_ids=tuple(rejected_system_ids),
            affected_existing_region_ids=affected_existing_region_ids,
            created_region_count=created_region_count,
            created_line_count=len(registerable_candidates),
            affected_model_component_ids=(),
            affected_mask_ids=(),
            multiplet_groups=multiplet_groups,
            multi_overlap_warning=(
                any(preview.overlap_warning for preview in impactful_previews)
                if changed
                else False
            ),
        )
        return IdentifyRegistrationPlan(
            normalized_candidates=normalized_candidates,
            registration_requests=tuple(registration_requests),
            region_previews=previews,
            impact=impact,
        )


class BuildRegionAssignmentUseCase:
    """Build region assignment operations for registered absorption lines."""

    def build(self, request: BuildRegionAssignmentRequest) -> BuildRegionAssignmentResult:
        """Build operations from previews and registered line references.

        Args:
            request: Current registration previews and created absorption line references.

        Returns:
            Ordered region assignment operations. Previews without registered members are
            ignored.
        """
        line_id_by_system_id = {line.system_id: line.line_id for line in request.registered_lines}
        operations: list[RegionAssignmentOperation] = []

        for preview in request.previews:
            member_line_ids = tuple(
                line_id_by_system_id[system_id]
                for system_id in preview.member_system_ids
                if system_id in line_id_by_system_id
            )
            if not member_line_ids:
                continue

            if preview.existing_group_id:
                operations.append(
                    RegionAssignmentOperation(
                        kind=RegionAssignmentOperationKind.ADD_TO_EXISTING,
                        line_ids=member_line_ids,
                        existing_region_id=preview.existing_group_id,
                    )
                )
            else:
                operations.append(
                    RegionAssignmentOperation(
                        kind=RegionAssignmentOperationKind.CREATE_REGION, line_ids=member_line_ids
                    )
                )

        return BuildRegionAssignmentResult(operations=tuple(operations))


class BuildRegistrationOutcomeUseCase:
    """Build typed outcome IDs after candidate registration."""

    def build(self, request: BuildRegistrationOutcomeRequest) -> RegistrationOutcome:
        """Build a registration outcome from before/after project snapshots.

        Args:
            request: Existing region IDs, current region IDs, registered line states, and
                failed system IDs.

        Returns:
            Typed outcome for session cleanup, history, and status messages.
        """
        existing_region_ids = set(request.existing_region_ids)
        created_region_ids = tuple(
            region_id
            for region_id in request.all_region_ids_after
            if region_id not in existing_region_ids
        )
        created_line_ids = tuple(line.line_id for line in request.registered_lines)
        failed_system_ids = tuple(request.failed_system_ids)
        processed_system_ids = (
            tuple(line.system_id for line in request.registered_lines) + failed_system_ids
        )
        affected_region_ids_list: list[str] = []
        seen_region_ids: set[str] = set()
        for line in request.registered_lines:
            if line.region_id is None or line.region_id in seen_region_ids:
                continue
            affected_region_ids_list.append(line.region_id)
            seen_region_ids.add(line.region_id)

        appended_region_ids = tuple(
            region_id for region_id in affected_region_ids_list if region_id in existing_region_ids
        )
        return RegistrationOutcome(
            created_line_ids=created_line_ids,
            created_region_ids=created_region_ids,
            processed_system_ids=processed_system_ids,
            affected_region_ids=tuple(affected_region_ids_list),
            appended_region_ids=appended_region_ids,
            confirmed_count=len(created_line_ids),
            failed_count=len(failed_system_ids),
            multi_overlap_warning=request.multi_overlap_warning,
        )


class RegisterSelectedLinesUseCase:
    """Register selected identify candidates through project and session ports."""

    def __init__(self) -> None:
        """Create registration use case dependencies."""
        self._assignment_usecase = BuildRegionAssignmentUseCase()
        self._outcome_usecase = BuildRegistrationOutcomeUseCase()

    def register(self, request: RegisterSelectedLinesRequest) -> RegisterSelectedLinesResult:
        """Group candidates, register them, and clean up processed session state.

        Args:
            request: Registration request containing mutation ports and grouping inputs.

        Returns:
            Registration result. The outcome is None when no lines could be created.
        """
        plan = request.plan
        if plan.impact.mutation_outcome is StructureMutationOutcome.NO_CHANGE:
            return RegisterSelectedLinesResult(outcome=None, mode_sync_line_ids=())

        existing_region_ids = tuple(
            region.region_id for region in request.project.list_absorption_regions()
        )
        created_lines: dict[str, AbsorptionLine] = {}

        for line_request in plan.registration_requests:
            registered = self._materialize_registration_request(request.project, line_request)
            created_lines[line_request.system_id] = registered

        if not created_lines:
            msg = "Changed Identify registration plan produced no registered lines."
            raise RuntimeError(msg)

        setup_multiplet_cross_references(
            grouped_lines={
                group.tie_group_key: [created_lines[system_id] for system_id in group.system_ids]
                for group in plan.impact.multiplet_groups
            }
        )

        self._assign_groups_from_previews(
            project=request.project, previews=plan.region_previews, lines_by_id=created_lines
        )

        request.project.ensure_absorption_unassigned_region()

        outcome = self._outcome_usecase.build(
            BuildRegistrationOutcomeRequest(
                existing_region_ids=existing_region_ids,
                all_region_ids_after=tuple(
                    region.region_id for region in request.project.list_absorption_regions()
                ),
                registered_lines=tuple(
                    RegisteredLineState(
                        system_id=system_id, line_id=line.line_id, region_id=line.region_id
                    )
                    for system_id, line in created_lines.items()
                ),
                failed_system_ids=plan.impact.rejected_system_ids,
                multi_overlap_warning=plan.impact.multi_overlap_warning,
            )
        )

        request.session.remove_candidate_lines(set(outcome.processed_system_ids))

        return RegisterSelectedLinesResult(
            outcome=outcome, mode_sync_line_ids=outcome.created_line_ids
        )

    @staticmethod
    def _materialize_registration_request(
        project: IdentifyProjectMutationPort, line_request: AbsorptionLineRegistrationRequest
    ) -> AbsorptionLine:
        """Create one absorption line from a normalized registration request.

        Args:
            project: Project mutation port.
            line_request: Prepared line creation data retained by the preview plan.

        Returns:
            Created absorption line.
        """
        return project.add_absorption_line(
            species=line_request.species,
            rest_wavelength=line_request.rest_wavelength,
            center_z=line_request.center_z,
            window_kms=line_request.window_kms,
            multiplet_label=line_request.multiplet_label,
            transition_name=line_request.transition_name,
            oscillator_strength=line_request.oscillator_strength,
            gamma_value=line_request.gamma_value,
            lambda_range=line_request.lambda_range,
            multiplet_ids=(),
            created_by=line_request.created_by,
        )

    def _assign_groups_from_previews(
        self,
        *,
        project: IdentifyProjectMutationPort,
        previews: tuple[RegionPreviewSnapshot, ...],
        lines_by_id: dict[str, AbsorptionLine],
    ) -> None:
        """Apply region assignment operations through the project port.

        Args:
            project: Project mutation port.
            previews: Registration previews.
            lines_by_id: Created absorption lines keyed by candidate system ID.
        """
        assignment_result = self._assignment_usecase.build(
            BuildRegionAssignmentRequest(
                previews=previews,
                registered_lines=tuple(
                    RegisteredLineReference(system_id=system_id, line_id=line.line_id)
                    for system_id, line in lines_by_id.items()
                ),
            )
        )
        for operation in assignment_result.operations:
            if operation.kind is RegionAssignmentOperationKind.ADD_TO_EXISTING:
                if operation.existing_region_id is None:
                    msg = "Existing-region assignment operation requires a region id."
                    raise RuntimeError(msg)
                existing_region = project.find_absorption_region(operation.existing_region_id)
                if existing_region is None:
                    msg = (
                        "Existing-region assignment target was not found: "
                        f"{operation.existing_region_id}"
                    )
                    raise RuntimeError(msg)
                for line_id in operation.line_ids:
                    project.assign_line_to_region(line_id, existing_region.region_id)
            else:
                project.create_region_with_lines(operation.line_ids)


class BuildRegionPreviewsUseCase:
    """Build registration previews from candidate lines and existing regions."""

    def build(self, request: BuildRegionPreviewsRequest) -> BuildRegionPreviewsResult:
        """Build preview groups based on wavelength overlap and multiplet proximity.

        Args:
            request: Preview grouping request.

        Returns:
            Region preview result.
        """
        systems_list = list(request.candidates)
        if not systems_list:
            return BuildRegionPreviewsResult(previews=())

        uf = UnionFind(len(systems_list))
        _union_by_wavelength_overlap(uf, systems_list)
        _union_by_tie_group(uf, systems_list, request.multiplet_grouping_tolerance)
        _merge_overlapping_groups(uf, systems_list)

        groups: dict[int, list[CandidateLineSnapshot]] = defaultdict(list)
        for index, system in enumerate(systems_list):
            groups[uf.find(index)].append(system)

        component_to_overlapping_regions: dict[int, tuple[str, ...]] = {}
        for root, group_systems in groups.items():
            component_to_overlapping_regions[root] = _overlapping_existing_region_ids(
                group_systems, request.existing_regions
            )

        region_names = {
            existing.region_id: existing.display_name for existing in request.existing_regions
        }
        previews: list[RegionPreviewSnapshot] = []
        for preview_index, (root_index, group_systems) in enumerate(groups.items(), start=1):
            species_counts = _count_species_in_group(group_systems, request.unknown_label)
            overlapping_region_ids = component_to_overlapping_regions[root_index]
            # Absorb into the first overlapping region; the warning surfaces the ambiguity.
            overlap_warning = len(overlapping_region_ids) > 1
            existing_group_id = overlapping_region_ids[0] if overlapping_region_ids else None

            if existing_group_id is not None:
                group_name = f"→ {region_names.get(existing_group_id, existing_group_id)}"
                preview_id = f"add-to-{existing_group_id}"
            else:
                lambda_min = min(system.lambda_min for system in group_systems)
                lambda_max = max(system.lambda_max for system in group_systems)
                main_species = max(species_counts.items(), key=lambda item: item[1])[0]
                group_name = f"{main_species} @ {lambda_min:.1f}-{lambda_max:.1f}Å"
                preview_id = f"preview-{preview_index}"

            previews.append(
                RegionPreviewSnapshot(
                    group_id=preview_id,
                    name=group_name,
                    member_system_ids=tuple(system.system_id for system in group_systems),
                    overlap_warning=overlap_warning,
                    existing_group_id=existing_group_id,
                )
            )

        return BuildRegionPreviewsResult(previews=tuple(previews))


def _derive_redshift(system: CandidateLineSnapshot) -> float | None:
    """Derive redshift from a candidate line.

    Args:
        system: Candidate line.

    Returns:
        Redshift or None when invalid.
    """
    if math.isfinite(system.center_z):
        return system.center_z
    if system.rest_wavelength > 0:
        center = system.center_wavelength
        if math.isfinite(center) and center > 0:
            return (center / system.rest_wavelength) - 1.0
    return None


def _should_union_by_redshift(
    left: CandidateLineSnapshot,
    right: CandidateLineSnapshot,
    multiplet_grouping_tolerance: MultipletGroupingVelocityTolerance,
) -> bool:
    """Return whether two candidates should be grouped by redshift proximity."""
    left_z = _derive_redshift(left)
    right_z = _derive_redshift(right)
    if left_z is None or right_z is None:
        return False

    delta_velocity = abs(left_z - right_z) * LIGHT_SPEED_KMS
    return delta_velocity <= multiplet_grouping_tolerance.kms


def _union_by_tie_group(
    uf: UnionFind,
    systems: Sequence[CandidateLineSnapshot],
    multiplet_grouping_tolerance: MultipletGroupingVelocityTolerance,
) -> None:
    """Union candidates with the same declared tie group and close redshift."""
    tie_group_map: dict[str, list[int]] = defaultdict(list)
    for index, system in enumerate(systems):
        if system.tie_group_key:
            tie_group_map[system.tie_group_key].append(index)

    for indices in tie_group_map.values():
        if len(indices) < 2:
            continue
        for left_offset, left_index in enumerate(indices):
            for right_index in indices[left_offset + 1 :]:
                if _should_union_by_redshift(
                    systems[left_index], systems[right_index], multiplet_grouping_tolerance
                ):
                    uf.union(left_index, right_index)


def _has_wavelength_overlap(left: CandidateLineSnapshot, right: CandidateLineSnapshot) -> bool:
    """Return whether two candidate wavelength ranges overlap."""
    return not (left.lambda_max < right.lambda_min or right.lambda_max < left.lambda_min)


def _union_by_wavelength_overlap(uf: UnionFind, systems: Sequence[CandidateLineSnapshot]) -> None:
    """Union candidates with overlapping wavelength ranges."""
    for left_index, left in enumerate(systems):
        for right_index in range(left_index + 1, len(systems)):
            if _has_wavelength_overlap(left, systems[right_index]):
                uf.union(left_index, right_index)


def _merge_overlapping_groups(uf: UnionFind, systems: Sequence[CandidateLineSnapshot]) -> None:
    """Merge groups where any member ranges overlap across groups."""
    roots = list({uf.find(index) for index in range(len(systems))})
    for left_offset, left_root in enumerate(roots):
        for right_root in roots[left_offset + 1 :]:
            current_left = uf.find(left_root)
            current_right = uf.find(right_root)
            if current_left == current_right:
                continue
            if _groups_have_overlapping_lines(uf, systems, current_left, current_right):
                uf.union(left_root, right_root)


def _groups_have_overlapping_lines(
    uf: UnionFind, systems: Sequence[CandidateLineSnapshot], left_root: int, right_root: int
) -> bool:
    """Return whether two candidate groups have overlapping member lines."""
    left_members = [system for index, system in enumerate(systems) if uf.find(index) == left_root]
    right_members = [
        system for index, system in enumerate(systems) if uf.find(index) == right_root
    ]
    return any(
        _has_wavelength_overlap(left, right) for left in left_members for right in right_members
    )


def _overlapping_existing_region_ids(
    group_systems: Sequence[CandidateLineSnapshot],
    existing_regions: tuple[ExistingRegionSnapshot, ...],
) -> tuple[str, ...]:
    """Return existing region IDs overlapping a candidate group, in first-found order."""
    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in group_systems:
        for existing in existing_regions:
            if existing.region_id in seen:
                continue
            if _has_overlap_with_any_range(candidate, existing.line_ranges):
                seen.add(existing.region_id)
                ordered.append(existing.region_id)
    return tuple(ordered)


def _has_overlap_with_any_range(
    candidate: CandidateLineSnapshot, ranges: tuple[tuple[float, float], ...]
) -> bool:
    """Return whether a candidate overlaps any existing line range."""
    return any(
        not (candidate.lambda_max < line_min or line_max < candidate.lambda_min)
        for line_min, line_max in ranges
    )


def _count_species_in_group(
    systems: Iterable[CandidateLineSnapshot], unknown_label: str
) -> dict[str, int]:
    """Count candidate species labels in a group."""
    counts: dict[str, int] = defaultdict(int)
    for system in systems:
        species = system.species or unknown_label
        counts[species] += 1
    return counts
