"""Tests for resource application ports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from chappy.application.ports import AtomicLineRepository, PresetStorePort, ResourcePathResolver
from chappy.core.atomic_data import AtomicLine, LineIdentifier, SearchFilters
from chappy.core.presets import Preset, PresetImportSummary, PresetTieGroup


def _line(identifier: str = "line-a") -> AtomicLine:
    """Create an atomic line for port contract tests."""
    return AtomicLine(
        line_identifier=identifier,
        species="H I",
        wavelength_angstrom=1215.67,
        oscillator_strength=0.4164,
        gamma_value=6.265e8,
    )


@dataclass(slots=True)
class _ResourceResolverStub:
    """Stub resource resolver."""

    root: Path

    def resolve_data_path(self, relative_path: str | Path) -> Path:
        """Resolve a data path under the stub root."""
        return self.root / relative_path


@dataclass(slots=True)
class _AtomicRepositoryStub:
    """Stub atomic line repository."""

    lines: list[AtomicLine]

    def get_lines_by_multiplet(self, multiplet_id: str) -> list[AtomicLine]:
        """Return matching multiplet lines."""
        return [line for line in self.lines if line.multiplet_id == multiplet_id]

    def has_multiplet_siblings(self, line: AtomicLine) -> bool:
        """Return whether the line has multiplet siblings."""
        return bool(line.multiplet_id and self.get_lines_by_multiplet(line.multiplet_id))

    def get_line_by_id(self, line_id: LineIdentifier) -> AtomicLine | None:
        """Return one line by identifier."""
        return next((line for line in self.lines if line.line_id == line_id), None)

    def get_line_by_species_wavelength(
        self, species: str, wavelength: float, *, tolerance: float = 0.01
    ) -> AtomicLine | None:
        """Return one line by species and wavelength."""
        return next(
            (
                line
                for line in self.lines
                if line.species == species
                and abs(line.wavelength_angstrom - wavelength) <= tolerance
            ),
            None,
        )

    def search_lines(self, filters: SearchFilters | None = None) -> list[AtomicLine]:
        """Return all lines for the contract stub."""
        return list(self.lines)

    def get_available_elements(self) -> list[str]:
        """Return available elements."""
        return sorted({line.element for line in self.lines})

    def get_available_charge_states(self, element: str | None = None) -> list[int]:
        """Return available charge states."""
        return sorted(
            {
                line.charge_state
                for line in self.lines
                if line.charge_state is not None and (element is None or line.element == element)
            }
        )


@dataclass(slots=True)
class _PresetStoreStub:
    """Stub preset store."""

    current_preset_id: str | None
    presets: list[Preset]

    def list_presets(self) -> list[Preset]:
        """Return presets."""
        return list(self.presets)

    def get_preset(self, preset_id: str) -> Preset | None:
        """Return one preset."""
        return next((preset for preset in self.presets if preset.id == preset_id), None)

    def preset_revision(self, preset_id: str) -> float | None:
        """Return the preset's updated-at token."""
        preset = self.get_preset(preset_id)
        return preset.updated_at.timestamp() if preset else None

    def set_current_preset(self, preset_id: str | None) -> None:
        """Set current preset."""
        self.current_preset_id = preset_id

    def set_translator(self, translate: object) -> None:
        """Set translator."""
        del translate

    def export_presets(
        self,
        destination: str | Path,
        preset_ids: list[str] | None = None,
        *,
        include_names: bool = True,
    ) -> None:
        """Export presets."""

    def import_presets(self, source: str | Path) -> PresetImportSummary:
        """Import presets."""
        return PresetImportSummary(imported=[], renamed=[], missing_lines={})

    def create_custom_preset(
        self,
        name: str,
        *,
        line_ids: list[LineIdentifier] | None = None,
        baseline_id: LineIdentifier | None = None,
        description: str = "",
    ) -> Preset:
        """Create a custom preset."""
        preset = Preset(
            id="custom",
            name=name,
            source="custom",
            line_ids=list(line_ids or ()),
            baseline_id=baseline_id,
            description=description,
        )
        self.presets.append(preset)
        return preset

    def rename_preset(self, preset_id: str, new_name: str) -> Preset:
        """Rename a preset."""
        preset = self.get_preset(preset_id)
        if preset is None:
            raise KeyError(preset_id)
        preset.name = new_name
        return preset

    def duplicate_preset(self, preset_id: str) -> Preset:
        """Duplicate a preset."""
        preset = self.get_preset(preset_id)
        if preset is None:
            raise KeyError(preset_id)
        duplicate = Preset(id=f"{preset.id}-copy", name=preset.name, source="custom")
        self.presets.append(duplicate)
        return duplicate

    def delete_preset(self, preset_id: str) -> None:
        """Delete a preset."""
        self.presets = [preset for preset in self.presets if preset.id != preset_id]

    def add_tie_group(self, preset_id: str, line_ids: list[LineIdentifier]) -> PresetTieGroup:
        """Add a tie group."""
        preset = self.get_preset(preset_id)
        if preset is None:
            raise KeyError(preset_id)
        group = PresetTieGroup(uid="stub-group", line_ids=tuple(line_ids))
        preset.tie_groups.append(group)
        return group

    def replace_tie_group_members(
        self, preset_id: str, group_uid: str, line_ids: list[LineIdentifier]
    ) -> PresetTieGroup:
        """Replace tie-group members."""
        preset = self.get_preset(preset_id)
        if preset is None:
            raise KeyError(preset_id)
        group = PresetTieGroup(uid=group_uid, line_ids=tuple(line_ids))
        preset.tie_groups = [item for item in preset.tie_groups if item.uid != group_uid]
        preset.tie_groups.append(group)
        return group

    def remove_tie_group(self, preset_id: str, group_uid: str) -> None:
        """Remove a tie group."""
        preset = self.get_preset(preset_id)
        if preset is None:
            raise KeyError(preset_id)
        preset.tie_groups = [item for item in preset.tie_groups if item.uid != group_uid]

    def add_lines(self, preset_id: str, line_ids: list[LineIdentifier]) -> list[LineIdentifier]:
        """Add lines."""
        preset = self.get_preset(preset_id)
        if preset is None:
            raise KeyError(preset_id)
        preset.line_ids.extend(line_ids)
        return list(line_ids)

    def add_lines_with_tie_groups(
        self,
        preset_id: str,
        line_ids: list[LineIdentifier],
        tie_groups: list[list[LineIdentifier]],
    ) -> list[LineIdentifier]:
        """Add lines and tie groups."""
        added = self.add_lines(preset_id, line_ids)
        for members in tie_groups:
            self.add_tie_group(preset_id, members)
        return added

    def remove_lines(self, preset_id: str, line_ids: list[LineIdentifier]) -> list[LineIdentifier]:
        """Remove lines."""
        preset = self.get_preset(preset_id)
        if preset is None:
            raise KeyError(preset_id)
        removed = [line_id for line_id in line_ids if line_id in preset.line_ids]
        preset.line_ids = [line_id for line_id in preset.line_ids if line_id not in removed]
        return removed

    def set_baseline(self, preset_id: str, line_id: LineIdentifier | None) -> None:
        """Set baseline."""
        preset = self.get_preset(preset_id)
        if preset is None:
            raise KeyError(preset_id)
        preset.baseline_id = line_id


def test_resource_resolver_port_accepts_stub(tmp_path: Path) -> None:
    """Resource resolver stubs satisfy the application port."""
    resolver: ResourcePathResolver = _ResourceResolverStub(tmp_path)

    assert resolver.resolve_data_path("data/catalog.csv") == tmp_path / "data/catalog.csv"


def test_atomic_line_repository_port_accepts_stub() -> None:
    """Atomic repository stubs satisfy the application port."""
    line = _line()
    repository: AtomicLineRepository = _AtomicRepositoryStub([line])

    assert repository.get_line_by_id(line.line_id) == line
    assert repository.search_lines() == [line]


def test_preset_store_port_accepts_stub() -> None:
    """Preset store stubs satisfy the application port."""
    preset = Preset(id="default", name="Default", source="default")
    store: PresetStorePort = _PresetStoreStub("default", [preset])

    assert store.current_preset_id == "default"
    assert store.get_preset("default") == preset
