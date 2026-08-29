"""Architecture sentinels for user-facing absorber topology mutations."""

from __future__ import annotations

from pathlib import Path


_GUI_ROOTS = (
    "src/chappy/gui/modes/analysis/region_detail",
    "src/chappy/gui/modes/identify",
    "src/chappy/gui/modes/analysis/overview",
    "src/chappy/gui/shell",
    "src/chappy/gui/spectrum",
)
_FORBIDDEN_FRAGMENTS = (
    ".model.remove_component(",
    ".remove_absorber_component(",
    ".remove_absorber_component_by_id(",
    ".add_tie_set(",
    ".remove_tie_set(",
    ".attach_tie_set(",
    ".detach_tie_set(",
    ".model_ids.append(",
    ".model_ids.extend(",
    ".model_ids.insert(",
    ".model_ids.remove(",
    ".model_ids.clear(",
    ".components[:] =",
    ".tie_set =",
    ".parent_tie =",
)


def _production_sources() -> tuple[Path, ...]:
    """Return Python sources for user-facing absorber mutation entrypoints."""
    root = Path(__file__).parents[2]
    return tuple(
        source
        for relative_root in _GUI_ROOTS
        for source in sorted((root / relative_root).rglob("*.py"))
    )


def test_gui_absorber_topology_mutations_are_application_orchestrated() -> None:
    """GUI entrypoints must not directly mutate absorber links or parameter ties."""
    root = Path(__file__).parents[2]
    violations: list[str] = []
    direct_model_additions: list[str] = []
    for source in _production_sources():
        relative = source.relative_to(root)
        for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if any(fragment in stripped for fragment in _FORBIDDEN_FRAGMENTS):
                violations.append(f"{relative}:{line_number}: {stripped}")
            if ".model.add_component(" in stripped:
                direct_model_additions.append(f"{relative}: {stripped}")

    assert violations == []
    assert direct_model_additions == []
