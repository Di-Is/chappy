"""Pure line/region storage and logic for absorption identify-mode data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

from chappy.core.constants import LIGHT_SPEED_KMS

from .models import UNASSIGNED_REGION_ID, AbsorptionLine, AbsorptionRegion
from .multiplet_service import expand_multiplet_lines
from .region_operations import (
    collect_lines_for_region,
    is_region_needs_optimization,
    set_region_needs_optimization,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

GROUP_COLOR_PALETTE = [
    "#1abc9c",
    "#3498db",
    "#9b59b6",
    "#f1c40f",
    "#e67e22",
    "#e74c3c",
    "#16a085",
    "#2ecc71",
]

ABSORPTION_LINE_LIMIT = 1000


@dataclass(frozen=True, slots=True)
class AssignLineResult:
    """Outcome of moving a line into a region."""

    target_region_id: str
    vacated_region_id: str | None
    vacated_region_needs_deletion: bool


@dataclass(frozen=True, slots=True)
class RegionCleanupResult:
    """Outcome of finalizing a region after one of its lines was removed."""

    region_id: str
    needs_deletion: bool


@dataclass(frozen=True, slots=True)
class MoveLinesResult:
    """Outcome of validating and expanding a line-move request."""

    destination_region_id: str | None
    moved_lines: tuple[AbsorptionLine, ...]


class AbsorptionRegistry:
    """Owns absorption line/region storage and pure line/region operations."""

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._lines: dict[str, AbsorptionLine] = {}
        self._regions: dict[str, AbsorptionRegion] = {}

    @property
    def lines(self) -> dict[str, AbsorptionLine]:
        """Return the live absorption lines mapping."""
        return self._lines

    @lines.setter
    def lines(self, value: dict[str, AbsorptionLine]) -> None:
        """Replace the absorption lines mapping wholesale."""
        self._lines = value

    @property
    def regions(self) -> dict[str, AbsorptionRegion]:
        """Return the live absorption regions mapping."""
        return self._regions

    @regions.setter
    def regions(self, value: dict[str, AbsorptionRegion]) -> None:
        """Replace the absorption regions mapping wholesale."""
        self._regions = value

    def list_lines(self) -> list[AbsorptionLine]:
        """Return current absorption lines."""
        return list(self._lines.values())

    def list_regions(self) -> list[AbsorptionRegion]:
        """Return absorption regions."""
        return list(self._regions.values())

    def find_line(self, line_id: str) -> AbsorptionLine | None:
        """Return matching absorption line if present."""
        return self._lines.get(line_id)

    def require_line(self, line_id: str) -> AbsorptionLine:
        """Return a required absorption line or raise.

        Args:
            line_id: Absorption line identifier.

        Returns:
            Matching absorption line.

        Raises:
            ValueError: If the line is missing.
        """
        line = self.find_line(line_id)
        if line is None:
            msg = f"Absorption line not found: {line_id}"
            raise ValueError(msg)
        return line

    def find_region(self, region_id: str) -> AbsorptionRegion | None:
        """Return matching absorption region if present."""
        return self._regions.get(region_id)

    def require_region(self, region_id: str) -> AbsorptionRegion:
        """Return a required absorption region or raise.

        Args:
            region_id: Absorption region identifier.

        Returns:
            Matching absorption region.

        Raises:
            ValueError: If the region is missing.
        """
        region = self.find_region(region_id)
        if region is None:
            msg = f"Absorption region not found: {region_id}"
            raise ValueError(msg)
        return region

    def find_lines_for_region(self, region_id: str) -> list[AbsorptionLine] | None:
        """Return region lines when the region exists, otherwise None."""
        if self.find_region(region_id) is None:
            return None
        return collect_lines_for_region(self._regions, self._lines, region_id)

    def region_model_ids(self, region_id: str) -> tuple[str, ...]:
        """Return unique component IDs referenced by a region in stable order."""
        lines = self.find_lines_for_region(region_id)
        if lines is None:
            return ()
        return tuple(dict.fromkeys(model_id for line in lines for model_id in line.model_ids))

    def is_region_needs_optimization(self, region_id: str) -> bool:
        """Return whether any absorption line in the region needs optimization.

        Args:
            region_id: Region identifier.

        Returns:
            True when at least one line in the region has ``needs_optimization`` set.
        """
        return is_region_needs_optimization(self._regions, self._lines, region_id)

    def set_region_needs_optimization(self, region_id: str, *, needs_optimization: bool) -> int:
        """Set the optimization-needed flag for every absorption line in a region.

        Args:
            region_id: Region identifier.
            needs_optimization: Target optimization-needed state.

        Returns:
            Number of lines whose flag was changed.
        """
        return set_region_needs_optimization(
            self._regions, self._lines, region_id, needs_optimization=needs_optimization
        )

    def empty_region_ids(self) -> list[str]:
        """Return non-UNASSIGNED region IDs that have no lines."""
        return [
            region_id
            for region_id, region in self._regions.items()
            if region_id != UNASSIGNED_REGION_ID and not region.line_ids
        ]

    def ensure_unassigned_region(self) -> AbsorptionRegion:
        """Ensure the logical unassigned region exists and return it."""
        region = self._regions.get(UNASSIGNED_REGION_ID)
        if region is None:
            region = AbsorptionRegion(region_id=UNASSIGNED_REGION_ID, display_color="#bdc3c7")
            self._regions[UNASSIGNED_REGION_ID] = region
        return region

    def create_region(
        self, region_id: str | None = None, *, color: str | None = None
    ) -> AbsorptionRegion:
        """Create a new absorption region with optional colour.

        Args:
            region_id: Optional region identifier. If None, a new UUID is generated.
            color: Optional display color. If None, a color is allocated automatically.

        Note:
            Prefer ``create_region_with_lines`` for application code to ensure
            the region invariant (non-UNASSIGNED regions always have lines).
            This method is retained for internal use and migration scenarios.
        """
        if region_id is None:
            region_id = uuid4().hex
        region = AbsorptionRegion(
            region_id=region_id, display_color=color or self._allocate_color()
        )
        self._regions[region_id] = region
        return region

    def add_line(  # noqa: PLR0913 - data model requires explicit fields
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
        """Register an absorption line derived from identify mode.

        Args:
            species: Element/ion species (e.g., "C IV").
            rest_wavelength: Rest-frame wavelength in Angstroms.
            center_z: Central redshift.
            window_kms: Velocity window in km/s.
            multiplet_label: Display label from atomic database (for reproducibility).
            transition_name: Transition name from atomic database.
            oscillator_strength: Oscillator strength (f-value) from atomic database.
            gamma_value: Damping constant from atomic database.
            lambda_range: Optional observed wavelength range.
            region_id: Optional region to assign the line to.
            multiplet_ids: Optional list of related line IDs.
            created_by: Creation source identifier.

        Returns:
            The newly created AbsorptionLine.
        """
        if len(self._lines) >= ABSORPTION_LINE_LIMIT:
            msg = "Absorption line limit reached"
            raise ValueError(msg)

        line = AbsorptionLine(
            line_id=uuid4().hex,
            species=species,
            rest_wavelength=rest_wavelength,
            center_z=center_z,
            window_kms=abs(window_kms),
            multiplet_label=multiplet_label,
            transition_name=transition_name.strip(),
            oscillator_strength=oscillator_strength,
            gamma_value=gamma_value,
            lambda_range=lambda_range,
            region_id=None,
            multiplet_ids=list(multiplet_ids or []),
            needs_optimization=True,
            created_by=created_by,
        )
        self._lines[line.line_id] = line

        default_region = self.ensure_unassigned_region()
        default_region.attach_lines([line.line_id])
        line.region_id = default_region.region_id

        if region_id and region_id != UNASSIGNED_REGION_ID:
            target_region = self.require_region(region_id)
            default_region.remove_lines([line.line_id])
            target_region.attach_lines([line.line_id])
            line.region_id = target_region.region_id
            self.update_region_analysis_range(default_region.region_id)
            self.update_region_analysis_range(target_region.region_id)

        return line

    def assign_line_to_region(self, line_id: str, region_id: str | None) -> AssignLineResult:
        """Move a line into the given region, deferring vacated-region deletion.

        Args:
            line_id: Absorption line identifier to move.
            region_id: Destination region identifier, or None for the unassigned region.

        Returns:
            The destination region id, and the previous region id together with
            whether it is now empty and eligible for deletion (deletion itself
            is left to the caller, since it involves model-side cleanup).
        """
        line = self.require_line(line_id)

        current_region = self._regions.get(line.region_id or UNASSIGNED_REGION_ID)
        if current_region:
            current_region.remove_lines([line_id])
        previous_region = current_region

        target_region: AbsorptionRegion
        if not region_id:
            target_region = self.ensure_unassigned_region()
        else:
            target_region = self.require_region(region_id)
        region_identifier = target_region.region_id

        target_region.attach_lines([line_id])
        line.region_id = region_identifier

        vacated_region_id: str | None = None
        vacated_region_needs_deletion = False
        if previous_region:
            if previous_region.region_id != region_identifier:
                if (
                    not previous_region.line_ids
                    and previous_region.region_id != UNASSIGNED_REGION_ID
                ):
                    vacated_region_id = previous_region.region_id
                    vacated_region_needs_deletion = True
                else:
                    self.update_region_analysis_range(previous_region.region_id)
            else:
                self.update_region_analysis_range(previous_region.region_id)
        self.update_region_analysis_range(region_identifier)

        return AssignLineResult(
            target_region_id=region_identifier,
            vacated_region_id=vacated_region_id,
            vacated_region_needs_deletion=vacated_region_needs_deletion,
        )

    def pop_line(self, line_id: str) -> AbsorptionLine:
        """Remove and return an absorption line, detaching it from its region.

        Args:
            line_id: Absorption line identifier to remove.

        Returns:
            The removed AbsorptionLine.

        Raises:
            ValueError: If the line is missing.
        """
        line = self._lines.pop(line_id, None)
        if line is None:
            msg = f"Absorption line not found: {line_id}"
            raise ValueError(msg)

        region = self._regions.get(line.region_id or UNASSIGNED_REGION_ID)
        if region:
            region.remove_lines([line_id])

        return line

    def clear_multiplet_references(self, line_id: str) -> None:
        """Remove ``line_id`` from every remaining line's multiplet references.

        Args:
            line_id: Absorption line identifier that was just removed from the registry.
        """
        for line in self._lines.values():
            if line_id in line.multiplet_ids:
                line.multiplet_ids.remove(line_id)

    def finalize_region_after_line_removal(self, region_id: str) -> RegionCleanupResult:
        """Update or flag a region after one of its lines was removed.

        Args:
            region_id: Absorption region identifier to finalize.

        Returns:
            ``needs_deletion=False`` with the analysis range refreshed when the
            region still has lines (or is the unassigned region); otherwise
            ``needs_deletion=True`` for the caller to delete it.
        """
        region = self.require_region(region_id)
        if region.line_ids:
            self.update_region_analysis_range(region_id)
            return RegionCleanupResult(region_id, needs_deletion=False)
        if region_id != UNASSIGNED_REGION_ID:
            return RegionCleanupResult(region_id, needs_deletion=True)
        return RegionCleanupResult(region_id, needs_deletion=False)

    def pop_region(self, region_id: str) -> AbsorptionRegion | None:
        """Remove and return a region, mirroring the UNASSIGNED-region guard.

        Args:
            region_id: Absorption region identifier to remove.

        Returns:
            The removed AbsorptionRegion, or None if ``region_id`` is the
            UNASSIGNED region or not present.
        """
        if region_id == UNASSIGNED_REGION_ID:
            return None
        return self._regions.pop(region_id, None)

    def move_lines(
        self, line_ids: Sequence[str], *, target_region_id: str | None
    ) -> MoveLinesResult:
        """Validate, expand, and resolve the destination for a line move.

        Args:
            line_ids: Absorption line identifiers to move.
            target_region_id: Destination region identifier, or None to create
                a new region.

        Returns:
            The destination region id (None if nothing to move) and the
            expanded lines to reassign, in processing order.

        Raises:
            ValueError: If any line id is missing.
        """
        unique_ids: list[str] = []
        seen: set[str] = set()
        for lid in line_ids:
            if lid not in seen:
                unique_ids.append(lid)
                seen.add(lid)
        missing_ids = [line_id for line_id in unique_ids if line_id not in self._lines]
        if missing_ids:
            msg = f"Absorption lines not found: {', '.join(map(str, missing_ids))}"
            raise ValueError(msg)
        if not unique_ids:
            return MoveLinesResult(None, ())

        expanded_ids = expand_multiplet_lines(self._lines, unique_ids)

        destination_region: AbsorptionRegion | None = None
        if target_region_id:
            destination_region = self.require_region(target_region_id)
        if destination_region is None:
            destination_region = self.create_region()

        moved_lines = tuple(self.require_line(lid) for lid in expanded_ids)
        return MoveLinesResult(destination_region.region_id, moved_lines)

    def update_region_analysis_range(self, region_id: str) -> None:
        """Update the analysis range for an absorption region.

        Calculates the union of wavelength ranges from all absorption lines
        in the region.

        Args:
            region_id: ID of the region to update
        """
        region = self.require_region(region_id)

        min_wavelength = float("inf")
        max_wavelength = float("-inf")
        has_lines = False

        for line_id in region.line_ids:
            line = self.require_line(line_id)
            if line.lambda_range:
                has_lines = True
                min_wavelength = min(min_wavelength, line.lambda_range[0])
                max_wavelength = max(max_wavelength, line.lambda_range[1])
            else:
                # Calculate range from center_z and window_kms
                obs_wavelength = line.observed_wavelength()
                if obs_wavelength > 0 and line.window_kms > 0:
                    has_lines = True
                    # Convert velocity window to wavelength range
                    delta_lambda = obs_wavelength * line.window_kms / LIGHT_SPEED_KMS
                    min_wavelength = min(min_wavelength, obs_wavelength - delta_lambda)
                    max_wavelength = max(max_wavelength, obs_wavelength + delta_lambda)

        if has_lines and min_wavelength < max_wavelength:
            region.analysis_range = (min_wavelength, max_wavelength)
        else:
            region.analysis_range = None

    def expand_multiplet_line_ids(self, seed_ids: Sequence[str]) -> list[str]:
        """Expand seed line IDs to include all multiplet companions.

        Args:
            seed_ids: Initial line IDs to expand.

        Returns:
            Sorted list of expanded line IDs including multiplet companions.
        """
        return sorted(expand_multiplet_lines(self._lines, seed_ids))

    def restore_line(
        self, line: AbsorptionLine, *, restore_multiplet_links: bool = True
    ) -> AbsorptionLine | None:
        """Restore an absorption line from a typed core object.

        Args:
            line: Absorption line to restore.
            restore_multiplet_links: If True, restore bidirectional multiplet links.

        Returns:
            Restored AbsorptionLine.
        """
        self._lines[line.line_id] = line

        # Assign to region if specified
        region_id = line.region_id
        if region_id:
            region = self._regions.get(region_id)
            if region and line.line_id not in region.line_ids:
                region.line_ids.append(line.line_id)

        # Restore bidirectional multiplet links
        if restore_multiplet_links:
            for related_id in line.multiplet_ids:
                related = self._lines.get(related_id)
                if related and line.line_id not in related.multiplet_ids:
                    related.multiplet_ids.append(line.line_id)

        return line

    def restore_region(self, region: AbsorptionRegion) -> AbsorptionRegion | None:
        """Restore an absorption region from a typed core object.

        Note: This only restores the region structure, not the lines.
        Lines should be restored separately with restore_line.

        Args:
            region: Absorption region to restore.

        Returns:
            Restored AbsorptionRegion.
        """
        # Don't restore UNASSIGNED region
        if region.region_id == UNASSIGNED_REGION_ID:
            return self._regions.get(UNASSIGNED_REGION_ID)

        self._regions[region.region_id] = region

        return region

    def validate_merge_ids(self, region_ids: Sequence[str]) -> list[str]:
        """Validate and resolve region ids for a merge.

        Args:
            region_ids: Candidate region identifiers to merge, first-listed
                region becomes the merge target.

        Returns:
            Deduplicated, existing, non-UNASSIGNED region ids in original
            order (index 0 is the merge target), or an empty list if fewer
            than two regions remain mergeable.

        Raises:
            ValueError: If a non-UNASSIGNED id in ``region_ids`` doesn't
                match an existing region.
        """
        seen: set[str] = set()
        unique_ids: list[str] = []
        for rid in region_ids:
            if rid not in seen:
                unique_ids.append(rid)
                seen.add(rid)

        missing_ids = [
            rid for rid in unique_ids if rid != UNASSIGNED_REGION_ID and rid not in self._regions
        ]
        if missing_ids:
            msg = f"Absorption regions not found: {', '.join(missing_ids)}"
            raise ValueError(msg)

        valid_ids = [
            rid for rid in unique_ids if rid in self._regions and rid != UNASSIGNED_REGION_ID
        ]
        if len(valid_ids) < 2:
            return []
        return valid_ids

    def _allocate_color(self) -> str:
        used_colors = {region.display_color for region in self._regions.values()}
        for color in GROUP_COLOR_PALETTE:
            if color not in used_colors:
                return color
        return GROUP_COLOR_PALETTE[len(self._regions) % len(GROUP_COLOR_PALETTE)]
