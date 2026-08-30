"""Core data structures and in-memory behavior for absorption line presets."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from chappy.core.atomic_data import AtomicLineData, LineIdentifier
from chappy.core.conversion import coerce_float

logger = logging.getLogger(__name__)

PresetSource = Literal["default", "custom"]
TranslateFunc = Callable[[str], str]

METAL_LINES_PRESET_ID = "builtin:metal_doublets"


def preset_tie_group_key(preset_id: str, group_uid: str) -> str:
    """Build the transient key used while materializing a preset tie group."""
    return f"preset:{preset_id}:{group_uid}"


def _now() -> datetime:
    """Return a timezone-aware timestamp for metadata fields."""
    return datetime.now(UTC)


def _coerce_species_candidates(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return [str(item) for item in value if item is not None]
    return []


class TieGroupIssue(StrEnum):
    """Validation failures for a candidate preset tie group."""

    TOO_FEW_LINES = "too_few_lines"
    DUPLICATE_UID = "duplicate_uid"
    LINE_NOT_IN_PRESET = "line_not_in_preset"
    UNKNOWN_LINE = "unknown_line"
    MIXED_SPECIES = "mixed_species"
    ALREADY_GROUPED = "already_grouped"


def evaluate_tie_group_issue(
    uid: str | None,
    line_ids: Sequence[LineIdentifier],
    *,
    preset_line_ids: Iterable[LineIdentifier],
    atomic_data: AtomicLineData,
    other_groups: Sequence[PresetTieGroup],
) -> TieGroupIssue | None:
    """Evaluate a candidate tie group against preset membership and sibling groups.

    Returns the first violated invariant in stable precedence order, or ``None``
    when the candidate is valid. ``uid`` may be ``None`` to skip the duplicate-uid
    check (used when the candidate has no persisted identity yet).
    """
    unique_line_ids = tuple(dict.fromkeys(line_ids))
    if len(unique_line_ids) < 2:
        return TieGroupIssue.TOO_FEW_LINES

    if uid is not None and any(group.uid == uid for group in other_groups):
        return TieGroupIssue.DUPLICATE_UID

    preset_line_id_set = set(preset_line_ids)
    if any(line_id not in preset_line_id_set for line_id in unique_line_ids):
        return TieGroupIssue.LINE_NOT_IN_PRESET

    atomic_lines = [atomic_data.get_line_by_id(line_id) for line_id in unique_line_ids]
    if any(line is None for line in atomic_lines):
        return TieGroupIssue.UNKNOWN_LINE

    species = {line.species for line in atomic_lines if line is not None}
    if len(species) != 1:
        return TieGroupIssue.MIXED_SPECIES

    other_line_ids = {line_id for group in other_groups for line_id in group.line_ids}
    if other_line_ids.intersection(unique_line_ids):
        return TieGroupIssue.ALREADY_GROUPED

    return None


_TIE_GROUP_ISSUE_MESSAGES: dict[TieGroupIssue, str] = {
    TieGroupIssue.TOO_FEW_LINES: "Preset tie groups require at least two lines",
    TieGroupIssue.DUPLICATE_UID: "Duplicate preset tie-group uid",
    TieGroupIssue.LINE_NOT_IN_PRESET: "Tie-group line is not part of the preset",
    TieGroupIssue.UNKNOWN_LINE: "Unknown tie-group line identifier",
    TieGroupIssue.MIXED_SPECIES: "Preset tie-group lines must have the same ion",
    TieGroupIssue.ALREADY_GROUPED: "Line belongs to multiple tie groups",
}


def _tie_group_error(issue: TieGroupIssue, uid: str) -> ValueError:
    return ValueError(f"{_TIE_GROUP_ISSUE_MESSAGES[issue]} (group {uid})")


@dataclass(frozen=True, slots=True)
class PresetTieGroup:
    """Declarative group of preset lines that must be linked together."""

    uid: str
    line_ids: tuple[LineIdentifier, ...]

    def __post_init__(self) -> None:
        """Validate invariants that do not require the atomic database."""
        if not self.uid.strip():
            msg = "Preset tie-group uid cannot be empty"
            raise ValueError(msg)
        if len(self.line_ids) < 2:
            msg = "Preset tie groups require at least two lines"
            raise ValueError(msg)
        if len(set(self.line_ids)) != len(self.line_ids):
            msg = "Preset tie-group line identifiers must be unique"
            raise ValueError(msg)


@dataclass(slots=True)
class Preset:
    """Model representing a named collection of atomic line identifiers."""

    id: str
    name: str
    source: PresetSource
    line_ids: list[LineIdentifier] = field(default_factory=list)
    tie_groups: list[PresetTieGroup] = field(default_factory=list)
    baseline_id: LineIdentifier | None = None
    description: str = ""
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def clone(self) -> Preset:
        """Return a deep copy of the preset for external consumers."""
        return Preset(
            id=self.id,
            name=self.name,
            source=self.source,
            line_ids=list(self.line_ids),
            tie_groups=list(self.tie_groups),
            baseline_id=self.baseline_id,
            description=self.description,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    def validate_tie_groups(self, atomic_data: AtomicLineData) -> None:
        """Validate all tie groups against preset membership and atomic data."""
        preset_line_ids = set(self.line_ids)

        for index, group in enumerate(self.tie_groups):
            other_groups = self.tie_groups[:index] + self.tie_groups[index + 1 :]
            issue = evaluate_tie_group_issue(
                group.uid,
                group.line_ids,
                preset_line_ids=preset_line_ids,
                atomic_data=atomic_data,
                other_groups=other_groups,
            )
            if issue is not None:
                raise _tie_group_error(issue, group.uid)

    @property
    def is_editable(self) -> bool:
        """Return True when user modifications are allowed."""
        return self.source == "custom"

    def ensure_baseline(self, atomic_data: AtomicLineData) -> None:
        """Ensure the preset has a valid baseline identifier."""
        if (
            self.baseline_id
            and self.baseline_id in self.line_ids
            and atomic_data.get_line_by_id(self.baseline_id)
        ):
            return

        self.baseline_id = _select_default_baseline(atomic_data, self.line_ids)


@dataclass(slots=True)
class PresetImportEntry:
    """Typed import candidate prepared by an application or infrastructure adapter."""

    name: str
    line_ids: list[LineIdentifier]
    tie_groups: list[PresetTieGroup] = field(default_factory=list)
    baseline_id: LineIdentifier | None = None
    description: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class PresetImportSummary:
    """Summary of presets imported from an external source."""

    imported: list[Preset]
    renamed: list[tuple[str, str]]
    missing_lines: dict[str, list[LineIdentifier]]
    skipped: int = 0


@dataclass(slots=True)
class _ImportOutcome:
    """Intermediate evaluation result for a single import entry."""

    preset: Preset | None
    missing: list[LineIdentifier]
    rename_pair: tuple[str, str] | None
    unique_name: str
    skip: bool


@dataclass(frozen=True, slots=True)
class _BuiltinLineSpec:
    """Line lookup definition for bundled presets."""

    line_id: LineIdentifier
    name: str


@dataclass(frozen=True, slots=True)
class _BuiltinPresetSpec:
    """Structured definition for a bundled preset."""

    id: str
    name: str
    description: str
    lines: tuple[_BuiltinLineSpec, ...]
    baseline_id: LineIdentifier
    tie_groups: tuple[PresetTieGroup, ...] = ()


class PresetExportError(RuntimeError):
    """Raised when preset export fails."""


class PresetImportError(RuntimeError):
    """Raised when preset import fails."""


class PresetStore:
    """Pure in-memory repository for absorption line presets."""

    MAX_PRESETS = 100
    DEFAULT_MATCH_TOLERANCE = 0.02

    def __init__(self, atomic_data: AtomicLineData, *, translate: TranslateFunc) -> None:
        """Initialize store with atomic data and required translator."""
        self._atomic_data = atomic_data
        self._presets: dict[str, Preset] = {}
        self._default_ids: list[str] = []
        self._custom_ids: list[str] = []
        self._current_id: str | None = None
        self._translate: TranslateFunc = translate

        self._load_default_presets()
        if self._current_id is None and self._default_ids:
            self._current_id = self._default_ids[0]

    def list_presets(self) -> list[Preset]:
        """Return all presets as independent snapshots."""
        ordered_ids = self._default_ids + self._custom_ids
        return [self._presets[preset_id].clone() for preset_id in ordered_ids]

    def get_preset(self, preset_id: str) -> Preset | None:
        """Return snapshot of preset matching identifier."""
        preset = self._presets.get(preset_id)
        return preset.clone() if preset else None

    def preset_revision(self, preset_id: str) -> float | None:
        """Return the preset's updated-at token without cloning the preset."""
        preset = self._presets.get(preset_id)
        return preset.updated_at.timestamp() if preset else None

    @property
    def current_preset_id(self) -> str | None:
        """Return active preset selection identifier."""
        return self._current_id

    def set_current_preset(self, preset_id: str | None) -> None:
        """Mark preset as currently selected."""
        if preset_id is not None and preset_id not in self._presets:
            msg = f"Unknown preset identifier: {preset_id}"
            raise KeyError(msg)
        self._current_id = preset_id

    def set_translator(self, translate: TranslateFunc) -> None:
        """Update translator callable and refresh default preset labels."""
        self._translate = translate
        specs = _builtin_preset_definitions(self._translate)
        for spec in specs:
            self._add_default_preset(spec)
        self._apply_default_translations(specs)

    def replace_custom_presets(
        self, presets: Sequence[Preset], *, current_id: str | None = None
    ) -> None:
        """Replace custom presets with previously persisted snapshots."""
        for preset_id in list(self._custom_ids):
            self._presets.pop(preset_id, None)
        self._custom_ids.clear()

        for preset in presets:
            if preset.source != "custom" or preset.id in self._presets:
                continue
            if len(self._default_ids) + len(self._custom_ids) >= self.MAX_PRESETS:
                logger.warning("Preset capacity reached; skipping '%s'", preset.name)
                break
            snapshot = preset.clone()
            snapshot.line_ids = self._normalize_line_ids(snapshot.line_ids)
            snapshot.tie_groups = self._normalize_tie_groups(
                snapshot.tie_groups, line_ids=snapshot.line_ids
            )
            if snapshot.baseline_id and snapshot.baseline_id not in snapshot.line_ids:
                snapshot.baseline_id = None
            snapshot.ensure_baseline(self._atomic_data)
            self._presets[snapshot.id] = snapshot
            self._custom_ids.append(snapshot.id)

        if current_id is not None and current_id in self._presets:
            self._current_id = current_id
        elif self._current_id not in self._presets:
            self._current_id = self._default_ids[0] if self._default_ids else None

    def import_preset_entries(
        self, entries: Sequence[PresetImportEntry], *, skipped: int = 0
    ) -> PresetImportSummary:
        """Import prepared preset entries into the in-memory store."""
        imported: list[Preset] = []
        renamed: list[tuple[str, str]] = []
        missing_lines: dict[str, list[LineIdentifier]] = {}
        existing_names = {preset.name for preset in self._presets.values()}

        for index, entry in enumerate(entries, start=1):
            outcome = self._evaluate_import_entry(
                entry, index=index, existing_names=existing_names
            )

            if outcome.skip:
                skipped += 1
                if outcome.missing:
                    missing_lines[outcome.unique_name] = outcome.missing
                continue

            self._ensure_capacity()

            existing_names.add(outcome.unique_name)
            preset = outcome.preset
            if preset is None:  # pragma: no cover - defensive fallback
                skipped += 1
                continue

            self._presets[preset.id] = preset
            self._custom_ids.append(preset.id)
            imported.append(preset.clone())

            if outcome.missing:
                missing_lines[outcome.unique_name] = outcome.missing
            if outcome.rename_pair:
                renamed.append(outcome.rename_pair)

        return PresetImportSummary(
            imported=imported, renamed=renamed, missing_lines=missing_lines, skipped=skipped
        )

    def create_custom_preset(
        self,
        name: str,
        *,
        line_ids: Sequence[LineIdentifier] | None = None,
        baseline_id: LineIdentifier | None = None,
        description: str = "",
        tie_groups: Sequence[PresetTieGroup] = (),
    ) -> Preset:
        """Create a new custom preset with optional initial lines and groups."""
        self._ensure_capacity()
        unique_name = self._validate_unique_name(name)
        normalized_lines = self._normalize_line_ids(line_ids or [])
        normalized_baseline = baseline_id if baseline_id in normalized_lines else None

        preset_id = uuid4().hex
        preset = Preset(
            id=preset_id,
            name=unique_name,
            source="custom",
            line_ids=normalized_lines,
            tie_groups=self._normalize_tie_groups(tie_groups, line_ids=normalized_lines),
            baseline_id=normalized_baseline,
            description=description,
        )
        preset.ensure_baseline(self._atomic_data)

        self._presets[preset_id] = preset
        self._custom_ids.append(preset_id)
        self._current_id = preset_id

        logger.debug("Created custom preset '%s' (%s)", unique_name, preset_id)
        return preset.clone()

    def rename_preset(self, preset_id: str, new_name: str) -> Preset:
        """Rename existing custom preset."""
        preset = self._require_editable_preset(preset_id)
        unique_name = self._validate_unique_name(new_name, allow_same_id=preset_id)
        preset.name = unique_name
        preset.updated_at = _now()
        logger.debug("Renamed preset %s -> %s", preset_id, unique_name)
        return preset.clone()

    def duplicate_preset(self, preset_id: str) -> Preset:
        """Duplicate preset, including metadata and declarative tie groups."""
        preset = self._require_preset(preset_id)
        copy_name = self._generate_copy_name(preset.name)
        return self.create_custom_preset(
            copy_name,
            line_ids=preset.line_ids,
            baseline_id=preset.baseline_id,
            description=preset.description,
            tie_groups=preset.tie_groups,
        )

    def delete_preset(self, preset_id: str) -> None:
        """Delete custom preset by identifier."""
        preset = self._require_editable_preset(preset_id)
        self._presets.pop(preset_id, None)
        with suppress(ValueError):
            self._custom_ids.remove(preset_id)
        if self._current_id == preset_id:
            self._current_id = self._custom_ids[-1] if self._custom_ids else None
        logger.debug("Deleted preset '%s' (%s)", preset.name, preset_id)

    def add_lines(
        self, preset_id: str, line_ids: Sequence[LineIdentifier]
    ) -> list[LineIdentifier]:
        """Add line identifiers to custom preset, returning newly added ones."""
        preset = self._require_editable_preset(preset_id)
        added: list[LineIdentifier] = []
        for line_id in self._normalize_line_ids(line_ids):
            if line_id in preset.line_ids:
                continue
            preset.line_ids.append(line_id)
            added.append(line_id)

        if added:
            preset.updated_at = _now()
            preset.ensure_baseline(self._atomic_data)
        return added

    def remove_lines(
        self, preset_id: str, line_ids: Sequence[LineIdentifier]
    ) -> list[LineIdentifier]:
        """Remove provided line identifiers from preset."""
        preset = self._require_editable_preset(preset_id)
        removed: list[LineIdentifier] = []
        for line_id in line_ids:
            if line_id in preset.line_ids:
                preset.line_ids.remove(line_id)
                removed.append(line_id)

        if removed:
            preset.tie_groups = self._remove_lines_from_tie_groups(preset.tie_groups, set(removed))
            preset.updated_at = _now()
            if preset.baseline_id in removed:
                preset.ensure_baseline(self._atomic_data)
        return removed

    def add_tie_group(
        self, preset_id: str, line_ids: Sequence[LineIdentifier], *, uid: str | None = None
    ) -> PresetTieGroup:
        """Add one strictly validated declarative tie group to a preset."""
        preset = self._require_editable_preset(preset_id)
        group = PresetTieGroup(uid=uuid4().hex if uid is None else uid, line_ids=tuple(line_ids))
        issue = evaluate_tie_group_issue(
            group.uid,
            group.line_ids,
            preset_line_ids=preset.line_ids,
            atomic_data=self._atomic_data,
            other_groups=preset.tie_groups,
        )
        if issue is not None:
            raise _tie_group_error(issue, group.uid)
        preset.tie_groups.append(group)
        preset.updated_at = _now()
        return group

    def replace_tie_group_members(
        self, preset_id: str, group_uid: str, line_ids: Sequence[LineIdentifier]
    ) -> PresetTieGroup:
        """Replace members of one tie group after strict validation."""
        preset = self._require_editable_preset(preset_id)
        index = next(
            (index for index, group in enumerate(preset.tie_groups) if group.uid == group_uid),
            None,
        )
        if index is None:
            msg = f"Preset tie group not found: {group_uid}"
            raise KeyError(msg)

        current_group = preset.tie_groups[index]
        replacement_line_ids = tuple(line_ids)
        replacement_uid = (
            group_uid if replacement_line_ids == current_group.line_ids else uuid4().hex
        )
        replacement = PresetTieGroup(uid=replacement_uid, line_ids=replacement_line_ids)
        other_groups = [group for i, group in enumerate(preset.tie_groups) if i != index]
        issue = evaluate_tie_group_issue(
            replacement.uid,
            replacement.line_ids,
            preset_line_ids=preset.line_ids,
            atomic_data=self._atomic_data,
            other_groups=other_groups,
        )
        if issue is not None:
            raise _tie_group_error(issue, replacement.uid)
        preset.tie_groups[index] = replacement
        preset.updated_at = _now()
        return replacement

    def remove_tie_group(self, preset_id: str, group_uid: str) -> None:
        """Remove one declarative tie group from a preset."""
        preset = self._require_editable_preset(preset_id)
        for index, group in enumerate(preset.tie_groups):
            if group.uid == group_uid:
                del preset.tie_groups[index]
                preset.updated_at = _now()
                return
        msg = f"Preset tie group not found: {group_uid}"
        raise KeyError(msg)

    def add_lines_with_tie_groups(
        self,
        preset_id: str,
        line_ids: Sequence[LineIdentifier],
        tie_groups: Sequence[Sequence[LineIdentifier]],
    ) -> list[LineIdentifier]:
        """Add lines unconditionally, then apply proposed tie groups on a best effort basis.

        Line addition never fails because of a tie-group proposal. Each proposal is
        applied independently: it extends the one existing group it overlaps, creates
        a new group when it overlaps none, or is skipped (with a warning) when it
        overlaps more than one existing group or would violate a tie-group invariant.
        """
        preset = self._require_editable_preset(preset_id)
        normalized_lines = self._normalize_line_ids(line_ids)
        added = [line_id for line_id in normalized_lines if line_id not in preset.line_ids]
        preset.line_ids.extend(added)

        changed_any_group = False
        for proposal in tie_groups:
            if self._apply_tie_group_proposal(preset, proposal):
                changed_any_group = True

        if added or changed_any_group:
            preset.updated_at = _now()
            preset.ensure_baseline(self._atomic_data)
        return added

    def _apply_tie_group_proposal(
        self, preset: Preset, proposal: Sequence[LineIdentifier]
    ) -> bool:
        """Extend, create, or skip one proposed tie group; return whether it changed."""
        proposal_ids = tuple(dict.fromkeys(proposal))
        intersecting = [
            index
            for index, group in enumerate(preset.tie_groups)
            if any(line_id in group.line_ids for line_id in proposal_ids)
        ]

        if len(intersecting) > 1:
            logger.warning(
                "Skipping tie-group proposal %s: overlaps %d existing groups",
                proposal_ids,
                len(intersecting),
            )
            return False

        if intersecting:
            index = intersecting[0]
            existing = preset.tie_groups[index]
            merged_ids = tuple(dict.fromkeys((*existing.line_ids, *proposal_ids)))
            if merged_ids == existing.line_ids:
                return False
            # Membership changed: re-issue the uid so stale transient keys stop matching.
            merged_uid = uuid4().hex
            other_groups = [group for i, group in enumerate(preset.tie_groups) if i != index]
            issue = evaluate_tie_group_issue(
                merged_uid,
                merged_ids,
                preset_line_ids=preset.line_ids,
                atomic_data=self._atomic_data,
                other_groups=other_groups,
            )
            if issue is not None:
                logger.warning("Skipping tie-group proposal %s: %s", proposal_ids, issue.value)
                return False
            preset.tie_groups[index] = PresetTieGroup(uid=merged_uid, line_ids=merged_ids)
            return True

        candidate_uid = uuid4().hex
        issue = evaluate_tie_group_issue(
            candidate_uid,
            proposal_ids,
            preset_line_ids=preset.line_ids,
            atomic_data=self._atomic_data,
            other_groups=preset.tie_groups,
        )
        if issue is not None:
            logger.warning("Skipping tie-group proposal %s: %s", proposal_ids, issue.value)
            return False
        preset.tie_groups.append(PresetTieGroup(uid=candidate_uid, line_ids=proposal_ids))
        return True

    def set_baseline(self, preset_id: str, line_id: LineIdentifier | None) -> None:
        """Update baseline identifier for preset.

        Baseline is session usage state rather than a structural preset edit: it is
        allowed on built-in presets too, since built-in presets are never persisted.
        """
        preset = self._require_preset(preset_id)
        if line_id is None:
            preset.baseline_id = None
        else:
            if line_id not in preset.line_ids:
                msg = f"Baseline line {line_id} is not part of preset {preset_id}"
                raise ValueError(msg)
            if not self._atomic_data.get_line_by_id(line_id):
                msg = f"Unknown line identifier: {line_id}"
                raise ValueError(msg)
            preset.baseline_id = line_id
        preset.updated_at = _now()

    def _load_default_presets(self) -> None:
        """Populate store with built-in presets."""
        specs = _builtin_preset_definitions(self._translate)
        for spec in specs:
            self._add_default_preset(spec)

        if self._default_ids:
            self._current_id = self._default_ids[0]

        self._apply_default_translations(specs)

    def _apply_default_translations(self, specs: Sequence[_BuiltinPresetSpec]) -> None:
        """Ensure in-memory defaults use the active translator."""
        for spec in specs:
            preset = self._presets.get(spec.id)
            if not preset or preset.source != "default":
                continue

            if preset.name != spec.name:
                preset.name = spec.name
            if preset.description != spec.description:
                preset.description = spec.description

    def _resolve_line_spec(  # noqa: PLR0911
        self, spec: _BuiltinLineSpec | dict[str, object] | str | None
    ) -> LineIdentifier | None:
        """Resolve flexible line spec into a concrete identifier."""
        if not spec:
            return None
        if isinstance(spec, _BuiltinLineSpec):
            return spec.line_id if self._atomic_data.get_line_by_id(spec.line_id) else None
        if isinstance(spec, str):
            return spec if self._atomic_data.get_line_by_id(spec) else None

        line_id_value = spec.get("line_id")
        if isinstance(line_id_value, str):
            if self._atomic_data.get_line_by_id(line_id_value):
                return line_id_value
            logger.warning("Preset line_id not found: %s", line_id_value)
            return None

        species = spec.get("species")
        wavelength = spec.get("wavelength")
        tolerance = coerce_float(spec.get("tolerance"), default=self.DEFAULT_MATCH_TOLERANCE)
        wavelength_value = coerce_float(wavelength, default=None)

        if species is None or wavelength_value is None:
            logger.debug("Incomplete line spec: %s", spec)
            return None

        species_candidates = _coerce_species_candidates(species)
        if not species_candidates:
            logger.debug("Unsupported species value in line spec: %s", species)
            return None

        normalized_candidates = [
            candidate.replace(" ", "").upper() for candidate in species_candidates
        ]

        matched_line = None
        best_delta = float("inf")

        for line in self._atomic_data.lines:
            normalized_species = line.species.replace(" ", "").upper()
            if normalized_species not in normalized_candidates:
                continue
            delta = abs(line.wavelength_angstrom - wavelength_value)
            if delta <= tolerance and delta < best_delta:
                matched_line = line
                best_delta = delta

        if matched_line:
            return matched_line.line_id

        display_name = spec.get("name")
        if display_name:
            logger.warning(
                "Preset line '%s' unresolved with provided species/wavelength", display_name
            )
        else:
            logger.warning("Preset line unresolved: %s", spec)
        return None

    def _normalize_line_ids(self, line_ids: Sequence[LineIdentifier]) -> list[LineIdentifier]:
        seen: set[LineIdentifier] = set()
        normalized: list[LineIdentifier] = []
        for line_id in line_ids:
            if not line_id:
                continue
            if not self._atomic_data.get_line_by_id(line_id):
                logger.debug("Skipping unknown line identifier: %s", line_id)
                continue
            if line_id in seen:
                continue
            seen.add(line_id)
            normalized.append(line_id)
        return normalized

    def _normalize_tie_groups(
        self, tie_groups: Sequence[PresetTieGroup], *, line_ids: Sequence[LineIdentifier]
    ) -> list[PresetTieGroup]:
        """Normalize externally loaded tie groups without rejecting the preset."""
        known_line_ids = set(line_ids)
        assigned_line_ids: set[LineIdentifier] = set()
        normalized: list[PresetTieGroup] = []

        for group in tie_groups:
            members = tuple(
                line_id
                for line_id in group.line_ids
                if line_id in known_line_ids and line_id not in assigned_line_ids
            )
            issue = evaluate_tie_group_issue(
                group.uid,
                members,
                preset_line_ids=known_line_ids,
                atomic_data=self._atomic_data,
                other_groups=normalized,
            )
            if issue is not None:
                logger.warning("Dropping preset tie group %s: %s", group.uid, issue.value)
                continue
            if members != group.line_ids:
                logger.warning(
                    "Trimming preset tie group %s: kept %d of %d members",
                    group.uid,
                    len(members),
                    len(group.line_ids),
                )

            normalized.append(PresetTieGroup(uid=group.uid, line_ids=members))
            assigned_line_ids.update(members)

        return normalized

    @staticmethod
    def _remove_lines_from_tie_groups(
        tie_groups: Sequence[PresetTieGroup], removed_ids: set[LineIdentifier]
    ) -> list[PresetTieGroup]:
        """Remove deleted line references and discard undersized groups."""
        result: list[PresetTieGroup] = []
        for group in tie_groups:
            members = tuple(line_id for line_id in group.line_ids if line_id not in removed_ids)
            if len(members) >= 2:
                result.append(PresetTieGroup(uid=group.uid, line_ids=members))
        return result

    def _validate_unique_name(self, name: str, *, allow_same_id: str | None = None) -> str:
        normalized = name.strip()
        if not normalized:
            message = "Preset name cannot be empty"
            raise ValueError(message)

        for preset_id, preset in self._presets.items():
            if preset.name == normalized and preset_id != allow_same_id:
                message = f"Preset name '{normalized}' already exists"
                raise ValueError(message)
        return normalized

    def _generate_copy_name(self, base_name: str) -> str:
        suffix_template = "{base} copy"
        candidate = suffix_template.format(base=base_name)
        index = 2
        existing_names = {preset.name for preset in self._presets.values()}
        while candidate in existing_names:
            candidate = f"{suffix_template.format(base=base_name)} {index}"
            index += 1
        return candidate

    def _require_preset(self, preset_id: str) -> Preset:
        preset = self._presets.get(preset_id)
        if not preset:
            msg = f"Preset not found: {preset_id}"
            raise KeyError(msg)
        return preset

    def _require_editable_preset(self, preset_id: str) -> Preset:
        preset = self._require_preset(preset_id)
        if preset.source != "custom":
            msg = "Default presets cannot be modified"
            raise PermissionError(msg)
        return preset

    def _ensure_capacity(self) -> None:
        total = len(self._default_ids) + len(self._custom_ids)
        if total >= self.MAX_PRESETS:
            msg = "Preset capacity exceeded"
            raise OverflowError(msg)

    def _add_default_preset(self, spec: _BuiltinPresetSpec) -> None:
        """Register a built-in preset definition if not already present."""
        if spec.id in self._presets or not spec.name:
            return

        line_ids: list[LineIdentifier] = []
        for line_spec in spec.lines:
            line_id = self._resolve_line_spec(line_spec)
            if line_id:
                line_ids.append(line_id)
            else:
                logger.warning("Preset '%s': unresolved line spec %s", spec.name, line_spec)

        baseline_id = self._resolve_line_spec(spec.baseline_id)

        resolved_groups = self._normalize_tie_groups(spec.tie_groups, line_ids=line_ids)
        preset = Preset(
            id=spec.id,
            name=spec.name,
            source="default",
            line_ids=line_ids,
            tie_groups=resolved_groups,
            baseline_id=baseline_id,
            description=spec.description,
        )
        preset.ensure_baseline(self._atomic_data)
        preset.validate_tie_groups(self._atomic_data)

        self._presets[spec.id] = preset
        self._default_ids.append(spec.id)

    def _evaluate_import_entry(
        self, entry: PresetImportEntry, *, index: int, existing_names: set[str]
    ) -> _ImportOutcome:
        raw_name = entry.name.strip()
        base_name = raw_name or f"Imported preset {index}"
        unique_name, renamed_flag = self._generate_unique_import_name(base_name, existing_names)

        requested_line_ids = list(entry.line_ids)
        normalized_ids = self._normalize_line_ids(requested_line_ids)
        missing = [line_id for line_id in requested_line_ids if line_id not in normalized_ids]

        if not normalized_ids:
            return _ImportOutcome(None, missing, None, unique_name, True)

        baseline_id = entry.baseline_id
        if baseline_id and baseline_id not in normalized_ids:
            missing.append(baseline_id)
            baseline_id = None

        created_at = entry.created_at or _now()
        updated_at = entry.updated_at or created_at

        preset = Preset(
            id=uuid4().hex,
            name=unique_name,
            source="custom",
            line_ids=normalized_ids,
            tie_groups=self._normalize_tie_groups(entry.tie_groups, line_ids=normalized_ids),
            baseline_id=baseline_id,
            description=entry.description,
            created_at=created_at,
            updated_at=updated_at,
        )
        preset.ensure_baseline(self._atomic_data)

        rename_pair = None
        if renamed_flag or (raw_name and unique_name != raw_name):
            rename_pair = (raw_name or unique_name, unique_name)

        return _ImportOutcome(preset, missing, rename_pair, unique_name, False)

    def _generate_unique_import_name(
        self, base_name: str, existing_names: set[str]
    ) -> tuple[str, bool]:
        normalized = base_name.strip()
        if not normalized:
            normalized = "Imported preset"
        normalized = normalized[:30].strip()
        if not normalized:
            normalized = "Imported preset"

        candidate = normalized
        changed = candidate != base_name.strip()
        counter = 2
        while candidate in existing_names:
            suffix = f" ({counter})"
            counter += 1
            available = max(1, 30 - len(suffix))
            candidate = f"{normalized[:available].rstrip()}{suffix}"
            changed = True

        return candidate, changed


def _select_default_baseline(
    atomic_data: AtomicLineData, line_ids: Sequence[LineIdentifier]
) -> LineIdentifier | None:
    """Pick a baseline line with strongest oscillator strength."""
    best_id: LineIdentifier | None = None
    best_osc = float("-inf")

    for line_id in line_ids:
        line = atomic_data.get_line_by_id(line_id)
        if not line:
            continue
        if line.oscillator_strength > best_osc:
            best_id = line_id
            best_osc = line.oscillator_strength

    return best_id


def _builtin_preset_definitions(translate: TranslateFunc) -> list[_BuiltinPresetSpec]:
    """Return structured definitions for bundled presets."""
    lyman_line_ids = (
        "8cd0394ff25e72e7",
        "cd0f85d159976946",
        "2feafb6deab92064",
        "35815e9743604328",
        "9f1f1a3dae473067",
    )
    return [
        _BuiltinPresetSpec(
            id="builtin:lyman",
            name=translate("Lyman Series"),
            description=translate("Principal H I Lyman transitions for quick selection."),
            lines=(
                _BuiltinLineSpec(lyman_line_ids[0], "Lyα"),
                _BuiltinLineSpec(lyman_line_ids[1], "Lyβ"),
                _BuiltinLineSpec(lyman_line_ids[2], "Lyγ"),
                _BuiltinLineSpec(lyman_line_ids[3], "Lyδ"),
                _BuiltinLineSpec(lyman_line_ids[4], "Lyε"),
            ),
            baseline_id=lyman_line_ids[0],
            tie_groups=(
                PresetTieGroup(uid="c1f2f0c8a7c94f1b9e0a5d7b3c6e8124", line_ids=lyman_line_ids),
            ),
        ),
        _BuiltinPresetSpec(
            id=METAL_LINES_PRESET_ID,
            name=translate("Metal Lines"),
            description=translate("Metal doublets."),
            lines=(
                _BuiltinLineSpec("d85a4a9d4dfb3235", "Mg II 2796.352"),
                _BuiltinLineSpec("380d715c908636f5", "Mg II 2803.531"),
                _BuiltinLineSpec("703f975612c284c7", "C IV 1548.204"),
                _BuiltinLineSpec("2f22adc74ae6712b", "C IV 1550.784"),
                _BuiltinLineSpec("9fe527b438587d9e", "Si IV 1393.755"),
                _BuiltinLineSpec("6ef4702248c8800f", "Si IV 1402.770"),
                _BuiltinLineSpec("e2fa193c1127a703", "N V 1238.804"),
                _BuiltinLineSpec("3c56a1c41c3932c5", "N V 1242.795"),
            ),
            baseline_id="d85a4a9d4dfb3235",
            tie_groups=(
                PresetTieGroup(
                    uid="2a9d7f63e4b14a5c8f0e1d2c3b4a5967",
                    line_ids=("d85a4a9d4dfb3235", "380d715c908636f5"),
                ),
                PresetTieGroup(
                    uid="4b7c9d1e2f3a4856a7b8c9d0e1f2a3b4",
                    line_ids=("703f975612c284c7", "2f22adc74ae6712b"),
                ),
                PresetTieGroup(
                    uid="6d8e0f1a2b3c4d5e6f708192a3b4c5d6",
                    line_ids=("9fe527b438587d9e", "6ef4702248c8800f"),
                ),
                PresetTieGroup(
                    uid="8f1a2b3c4d5e6f708192a3b4c5d6e7f8",
                    line_ids=("e2fa193c1127a703", "3c56a1c41c3932c5"),
                ),
            ),
        ),
    ]


__all__ = [
    "METAL_LINES_PRESET_ID",
    "LineIdentifier",
    "Preset",
    "PresetExportError",
    "PresetImportEntry",
    "PresetImportError",
    "PresetImportSummary",
    "PresetSource",
    "PresetStore",
    "PresetTieGroup",
    "TieGroupIssue",
    "TranslateFunc",
    "evaluate_tie_group_issue",
    "preset_tie_group_key",
]
