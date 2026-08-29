"""Tests for the Qt-independent line selection session."""

from __future__ import annotations

from dataclasses import dataclass, field

from chappy.application.line_selection import LineSelectionSession
from chappy.core.atomic_data import AtomicLine


def _line(line_id: str, *, multiplet_id: str = "", wavelength: float = 1500.0) -> AtomicLine:
    """Create an atomic line for session tests."""
    return AtomicLine(
        line_identifier=line_id,
        species="Mg II",
        wavelength_angstrom=wavelength,
        oscillator_strength=0.5,
        gamma_value=1.0e8,
        multiplet_id=multiplet_id,
        transition_name=f"Line {line_id}",
    )


@dataclass
class _FakeCatalog:
    """Minimal in-memory multiplet catalog."""

    lines: list[AtomicLine] = field(default_factory=list)

    def get_lines_by_multiplet(self, multiplet_id: str) -> list[AtomicLine]:
        """Return lines for a multiplet identifier."""
        if not multiplet_id:
            return []
        return [line for line in self.lines if line.multiplet_id == multiplet_id]

    def get_line_by_id(self, line_id: str) -> AtomicLine | None:
        """Return a line by identifier."""
        return next((line for line in self.lines if line.line_id == line_id), None)


def test_toggle_single_line_selects_and_deselects() -> None:
    """Toggling a non-multiplet line flips its selection."""
    catalog = _FakeCatalog([_line("a")])
    session = LineSelectionSession(catalog)

    change = session.toggle("a")
    assert session.selected_ids == frozenset({"a"})
    assert change.changed_line_ids == frozenset({"a"})

    session.toggle("a")
    assert session.selected_ids == frozenset()


def test_toggle_multiplet_member_selects_whole_group() -> None:
    """Toggling any member selects every member of the multiplet."""
    catalog = _FakeCatalog([_line("blue", multiplet_id="m"), _line("red", multiplet_id="m")])
    session = LineSelectionSession(catalog)

    change = session.toggle("red")

    assert session.selected_ids == frozenset({"blue", "red"})
    assert change.changed_line_ids == frozenset({"blue", "red"})
    assert session.is_aggregated_selected(catalog.get_line_by_id("blue"))  # type: ignore[arg-type]


def test_toggle_multiplet_again_deselects_whole_group() -> None:
    """A second toggle clears every selectable member."""
    catalog = _FakeCatalog([_line("blue", multiplet_id="m"), _line("red", multiplet_id="m")])
    session = LineSelectionSession(catalog)

    session.toggle("blue")
    session.toggle("red")

    assert session.selected_ids == frozenset()


def test_existing_line_cannot_be_toggled() -> None:
    """Locked existing lines are never mutated by toggle."""
    catalog = _FakeCatalog([_line("a")])
    session = LineSelectionSession(catalog, existing_ids={"a"})

    change = session.toggle("a")

    assert session.selected_ids == frozenset()
    assert change.changed_line_ids == frozenset()


def test_multiplet_with_existing_member_cannot_be_deselected() -> None:
    """Deselecting a multiplet that contains a locked line re-selects the rest."""
    catalog = _FakeCatalog([_line("blue", multiplet_id="m"), _line("red", multiplet_id="m")])
    session = LineSelectionSession(catalog, existing_ids={"blue"})

    # The group already counts as selected because "blue" exists; toggling
    # attempts to deselect but must keep selectable members selected.
    session.toggle("red")

    assert session.selected_ids == frozenset({"red"})
    assert session.is_aggregated_selected(catalog.get_line_by_id("red"))  # type: ignore[arg-type]


def test_remove_clears_multiplet_companions() -> None:
    """Removing one selected member clears the selected companions too."""
    catalog = _FakeCatalog([_line("blue", multiplet_id="m"), _line("red", multiplet_id="m")])
    session = LineSelectionSession(catalog)
    session.toggle("blue")

    change = session.remove("red")

    assert session.selected_ids == frozenset()
    assert change.changed_line_ids == frozenset({"blue", "red"})


def test_remove_unselected_line_is_noop() -> None:
    """Removing a line that is not selected does nothing."""
    catalog = _FakeCatalog([_line("a")])
    session = LineSelectionSession(catalog)

    change = session.remove("a")

    assert change.changed_line_ids == frozenset()
    assert session.selected_ids == frozenset()


def test_initial_ids_exclude_existing_ids() -> None:
    """Initial selection never overlaps locked existing identifiers."""
    catalog = _FakeCatalog([_line("a"), _line("b")])
    session = LineSelectionSession(catalog, existing_ids={"a"}, initial_ids={"a", "b"})

    assert session.selected_ids == frozenset({"b"})
    assert session.existing_ids == frozenset({"a"})


def test_clear_empties_selection() -> None:
    """Clearing removes all user-selected lines."""
    catalog = _FakeCatalog([_line("a"), _line("b")])
    session = LineSelectionSession(catalog, initial_ids={"a", "b"})

    change = session.clear()

    assert session.selected_ids == frozenset()
    assert change.changed_line_ids == frozenset({"a", "b"})


def test_build_result_contains_explicit_multiplet_group_proposal() -> None:
    """Multiplet-wide selection returns a persistent group proposal."""
    catalog = _FakeCatalog(
        [_line("blue", multiplet_id="m", wavelength=1500.0), _line("red", multiplet_id="m")]
    )
    session = LineSelectionSession(catalog)

    session.toggle("red")
    result = session.build_result()

    assert result.selected_ids == ("blue", "red")
    assert result.proposed_tie_groups[0].line_ids == ("blue", "red")


def test_build_result_includes_existing_member_in_group_without_returning_it_as_new() -> None:
    """Existing preset members participate in the proposal but not new IDs."""
    catalog = _FakeCatalog(
        [_line("blue", multiplet_id="m", wavelength=1500.0), _line("red", multiplet_id="m")]
    )
    session = LineSelectionSession(catalog, existing_ids={"blue"})

    session.toggle("red")
    result = session.build_result()

    assert result.selected_ids == ("red",)
    assert result.proposed_tie_groups[0].line_ids == ("blue", "red")


def test_remove_drops_explicit_multiplet_when_no_selected_members_remain() -> None:
    """Removing the last selected member clears the phantom multiplet proposal."""
    catalog = _FakeCatalog(
        [
            _line("a", multiplet_id="m", wavelength=1500.0),
            _line("b", multiplet_id="m", wavelength=1501.0),
            _line("c", multiplet_id="m", wavelength=1502.0),
            _line("x", wavelength=1600.0),
        ]
    )
    session = LineSelectionSession(catalog, existing_ids={"a", "b"})

    session.toggle("c")
    session.remove("c")
    session.toggle("x")

    result = session.build_result()

    assert all(set(group.line_ids) != {"a", "b"} for group in result.proposed_tie_groups)


def test_build_result_drops_proposal_after_multiplet_is_deselected() -> None:
    """A canceled multiplet selection does not leave a stale proposal."""
    catalog = _FakeCatalog(
        [_line("blue", multiplet_id="m", wavelength=1500.0), _line("red", multiplet_id="m")]
    )
    session = LineSelectionSession(catalog)

    session.toggle("blue")
    session.toggle("red")

    assert session.build_result().proposed_tie_groups == ()
