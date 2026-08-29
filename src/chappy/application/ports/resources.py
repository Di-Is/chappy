"""Application resource and catalog port definitions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    from chappy.core.atomic_data import AtomicLine, LineIdentifier, SearchFilters
    from chappy.core.presets import Preset, PresetImportSummary, PresetTieGroup


class ResourcePathResolver(Protocol):
    """Port for resolving application resource paths."""

    def resolve_data_path(self, relative_path: str | Path) -> Path:
        """Resolve a path under the configured application data root.

        Args:
            relative_path: Relative path requested by an application workflow.

        Returns:
            Absolute path to the resolved resource.
        """
        ...


class AtomicLineRepository(Protocol):
    """Port for querying atomic transition lines."""

    @property
    def lines(self) -> Sequence[AtomicLine]:
        """Return the available atomic lines."""
        ...

    def get_lines_by_multiplet(self, multiplet_id: str) -> list[AtomicLine]:
        """Return lines belonging to a multiplet.

        Args:
            multiplet_id: Multiplet identifier.

        Returns:
            Matching atomic lines.
        """
        ...

    def has_multiplet_siblings(self, line: AtomicLine) -> bool:
        """Return whether a line has siblings in its multiplet.

        Args:
            line: Atomic line to inspect.

        Returns:
            True when another line shares the line's multiplet identifier.
        """
        ...

    def get_line_by_id(self, line_id: LineIdentifier) -> AtomicLine | None:
        """Return one atomic line by persistent identifier.

        Args:
            line_id: Persistent line identifier.

        Returns:
            Atomic line when present, otherwise None.
        """
        ...

    def get_line_by_species_wavelength(
        self, species: str, wavelength: float, *, tolerance: float = 0.01
    ) -> AtomicLine | None:
        """Return one line by species and rest wavelength.

        Args:
            species: Species label.
            wavelength: Rest wavelength in angstroms.
            tolerance: Absolute wavelength tolerance in angstroms.

        Returns:
            Atomic line when present, otherwise None.
        """
        ...

    def search_lines(self, filters: SearchFilters | None = None) -> list[AtomicLine]:
        """Search atomic lines.

        Args:
            filters: Optional search filters.

        Returns:
            Matching atomic lines.
        """
        ...

    def get_available_elements(self) -> list[str]:
        """Return available element symbols."""
        ...

    def get_available_charge_states(self, element: str | None = None) -> list[int]:
        """Return available charge states.

        Args:
            element: Optional element filter.

        Returns:
            Charge states present in the repository.
        """
        ...


class PresetStorePort(Protocol):
    """Port for preset store operations."""

    @property
    def current_preset_id(self) -> str | None:
        """Return the active preset identifier."""
        ...

    def list_presets(self) -> list[Preset]:
        """Return preset snapshots."""
        ...

    def get_preset(self, preset_id: str) -> Preset | None:
        """Return one preset snapshot.

        Args:
            preset_id: Preset identifier.

        Returns:
            Preset when present, otherwise None.
        """
        ...

    def preset_revision(self, preset_id: str) -> float | None:
        """Return the preset's updated-at token without cloning the preset.

        Args:
            preset_id: Preset identifier.

        Returns:
            Monotonic-per-edit token when present, otherwise None.
        """
        ...

    def set_current_preset(self, preset_id: str | None) -> None:
        """Set the active preset.

        Args:
            preset_id: Preset identifier, or None to clear selection.
        """
        ...

    def set_translator(self, translate: Callable[[str], str]) -> None:
        """Set the active preset label translator.

        Args:
            translate: Translation callable for source text.
        """
        ...

    def export_presets(
        self,
        destination: str | Path,
        preset_ids: Sequence[str] | None = None,
        *,
        include_names: bool = True,
    ) -> Path:
        """Export presets.

        Args:
            destination: Destination file path.
            preset_ids: Optional subset of preset identifiers.
            include_names: Whether to include preset names.
            Exported path.
        """
        ...

    def import_presets(self, source: str | Path) -> PresetImportSummary:
        """Import presets from a file.

        Args:
            source: Source file path.

        Returns:
            Import summary.
        """
        ...

    def create_custom_preset(
        self,
        name: str,
        *,
        line_ids: Sequence[LineIdentifier] | None = None,
        baseline_id: LineIdentifier | None = None,
        description: str = "",
    ) -> Preset:
        """Create a custom preset.

        Args:
            name: Preset name.
            line_ids: Optional line identifiers.
            baseline_id: Optional baseline line identifier.
            description: Optional description.

        Returns:
            Created preset.
        """
        ...

    def rename_preset(self, preset_id: str, new_name: str) -> Preset:
        """Rename a preset.

        Args:
            preset_id: Preset identifier.
            new_name: New display name.

        Returns:
            Renamed preset.
        """
        ...

    def duplicate_preset(self, preset_id: str) -> Preset:
        """Duplicate a preset.

        Args:
            preset_id: Preset identifier.

        Returns:
            Created duplicate.
        """
        ...

    def delete_preset(self, preset_id: str) -> None:
        """Delete a preset.

        Args:
            preset_id: Preset identifier.
        """
        ...

    def add_tie_group(self, preset_id: str, line_ids: Sequence[LineIdentifier]) -> PresetTieGroup:
        """Add a declarative tie group to a preset."""
        ...

    def replace_tie_group_members(
        self, preset_id: str, group_uid: str, line_ids: Sequence[LineIdentifier]
    ) -> PresetTieGroup:
        """Replace members of a declarative tie group."""
        ...

    def remove_tie_group(self, preset_id: str, group_uid: str) -> None:
        """Remove a declarative tie group."""
        ...

    def add_lines(
        self, preset_id: str, line_ids: Sequence[LineIdentifier]
    ) -> list[LineIdentifier]:
        """Add lines to a preset.

        Args:
            preset_id: Preset identifier.
            line_ids: Line identifiers to add.

        Returns:
            Added line identifiers.
        """
        ...

    def add_lines_with_tie_groups(
        self,
        preset_id: str,
        line_ids: Sequence[LineIdentifier],
        tie_groups: Sequence[Sequence[LineIdentifier]],
    ) -> list[LineIdentifier]:
        """Add lines and tie-group declarations atomically."""
        ...

    def remove_lines(
        self, preset_id: str, line_ids: Sequence[LineIdentifier]
    ) -> list[LineIdentifier]:
        """Remove lines from a preset.

        Args:
            preset_id: Preset identifier.
            line_ids: Line identifiers to remove.

        Returns:
            Removed line identifiers.
        """
        ...

    def set_baseline(self, preset_id: str, line_id: LineIdentifier | None) -> None:
        """Set a preset baseline.

        Args:
            preset_id: Preset identifier.
            line_id: Baseline line identifier, or None to clear it.
        """
        ...
