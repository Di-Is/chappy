"""Tests for Qt-independent line selection presenters."""

from __future__ import annotations

from dataclasses import dataclass, field

from chappy.core.atomic_data import AtomicLine
from chappy.presentation.line_selection.presenter import (
    LinePreviewLabels,
    LinePreviewPresenter,
    LineRowLabels,
    LineSelectionPresenter,
    RowHighlightRole,
)


@dataclass
class _FakeSelectionView:
    """Structural SelectionView used to exercise the presenter."""

    selected: set[str] = field(default_factory=set)
    existing: set[str] = field(default_factory=set)
    selected_multiplets: set[str] = field(default_factory=set)

    @property
    def selected_ids(self) -> frozenset[str]:
        """User-selected identifiers."""
        return frozenset(self.selected)

    @property
    def existing_ids(self) -> frozenset[str]:
        """Locked identifiers."""
        return frozenset(self.existing)

    def is_aggregated_selected(self, line: AtomicLine) -> bool:
        """Return aggregated selection per multiplet or single line."""
        if line.multiplet_id:
            return line.multiplet_id in self.selected_multiplets
        return line.line_id in (self.selected | self.existing)


def _row_labels() -> LineRowLabels:
    """Return deterministic row labels."""
    return LineRowLabels(multiplet_header="Multiplet", multiplet_tooltip="whole multiplet")


def _line(
    line_id: str,
    *,
    wavelength: float,
    oscillator_strength: float,
    component_index: int | None = None,
    comments: str = "",
) -> AtomicLine:
    """Create an atomic line for presenter tests."""
    return AtomicLine(
        line_identifier=line_id,
        species="H I",
        wavelength_angstrom=wavelength,
        oscillator_strength=oscillator_strength,
        gamma_value=1.0e8,
        element_symbol="H",
        charge_state=0,
        transition_name=f"Line {line_id}",
        multiplet_id="m1",
        multiplet_label="H I",
        component_index=component_index,
        comments=comments,
    )


def _labels() -> LinePreviewLabels:
    """Return deterministic preview labels."""
    return LinePreviewLabels(
        element="Element",
        ion_stage="Ion stage",
        species="Species",
        multiplet="Multiplet",
        component="Component",
        rest_wavelength="Rest wavelength",
        ritz_wavelength="Ritz wavelength",
        ritz_uncertainty="Ritz uncertainty",
        observed_wavelength="Observed wavelength",
        observed_uncertainty="Observed uncertainty",
        source="Source",
        oscillator_f="Oscillator f",
        gamma="Gamma",
        lower_level_ev="Lower level eV",
        upper_level_ev="Upper level eV",
        delta_e_ev="Delta E eV",
        lower_level="Lower level",
        upper_level="Upper level",
        accuracy="Accuracy",
        transition_ref="Transition ref",
        wavelength_ref="Wavelength ref",
        notes="Notes",
        basic_information="Basic information",
        wavelength_strength="Wavelength and strength",
        energy_levels="Energy levels",
        references="References",
        source_ritz="Ritz",
        source_observed="Observed",
        source_aggregated="Aggregated",
        source_custom="Custom",
    )


def test_compute_multiplet_summaries_chooses_highest_f_value_after_component() -> None:
    """Representative selection is testable without constructing the dialog."""
    presenter = LineSelectionPresenter()
    weak = _line("weak", wavelength=1216.0, oscillator_strength=0.1)
    strong = _line("strong", wavelength=1215.0, oscillator_strength=0.5)

    summaries = presenter.compute_multiplet_summaries([weak, strong])

    assert summaries["m1"].representative_id == "strong"
    assert summaries["m1"].f_value_min == 0.1


def test_line_preview_presenter_escapes_user_visible_values() -> None:
    """Preview HTML escapes transition names and comments."""
    presenter = LinePreviewPresenter()
    line = _line(
        "escaped", wavelength=1215.67, oscillator_strength=0.416, comments="<unsafe>\nnext"
    )

    html = presenter.render_preview_html(line, labels=_labels())

    assert "&lt;unsafe&gt;<br>next" in html
    assert "<h3>Line escaped</h3>" in html
    assert "1215.6700" in html


def test_render_preview_html_orders_wavelength_before_basic_information() -> None:
    """Wavelength/strength rows come right after the title, references last."""
    presenter = LinePreviewPresenter()
    line = _line("order", wavelength=1215.67, oscillator_strength=0.416, comments="note")

    html = presenter.render_preview_html(line, labels=_labels())

    assert (
        html.index("Wavelength and strength")
        < html.index("Basic information")
        < html.index("Notes")
    )


def test_build_row_payloads_marks_representative_and_member() -> None:
    """Members stay marked with the └ prefix but are selectable like the head."""
    presenter = LineSelectionPresenter()
    rep = _line("rep", wavelength=1215.0, oscillator_strength=0.5, component_index=0)
    member = _line("member", wavelength=1216.0, oscillator_strength=0.1, component_index=1)
    view = _FakeSelectionView()

    payloads = presenter.build_row_payloads([rep, member], selection=view, labels=_row_labels())
    by_id = {payload.line_id: payload for payload in payloads}

    assert by_id["rep"].is_selectable
    assert not by_id["rep"].is_multiplet_member
    assert by_id["member"].is_multiplet_member
    assert by_id["member"].is_selectable
    assert by_id["member"].display_name.startswith("  └ ")
    assert by_id["rep"].accessible_text == "Multiplet H I"
    assert by_id["member"].name_tooltip == "whole multiplet"


def test_build_row_payloads_reports_aggregated_selection() -> None:
    """Aggregated selection comes from the selection view."""
    presenter = LineSelectionPresenter()
    rep = _line("rep", wavelength=1215.0, oscillator_strength=0.5, component_index=0)
    member = _line("member", wavelength=1216.0, oscillator_strength=0.1, component_index=1)
    view = _FakeSelectionView(selected_multiplets={"m1"})

    payloads = presenter.build_row_payloads([rep, member], selection=view, labels=_row_labels())

    assert all(payload.aggregated_selected for payload in payloads)


def test_build_highlight_states_assigns_roles() -> None:
    """Existing, highlighted, and group-header roles are assigned in order."""
    presenter = LineSelectionPresenter()
    rep = _line("rep", wavelength=1215.0, oscillator_strength=0.5, component_index=0)
    member = _line("member", wavelength=1216.0, oscillator_strength=0.1, component_index=1)
    view = _FakeSelectionView(existing={"rep"}, selected_multiplets={"m1"})

    roles = presenter.build_highlight_states([rep, member], selection=view)

    assert roles[0] is RowHighlightRole.EXISTING
    assert roles[1] is RowHighlightRole.HIGHLIGHT


def test_build_highlight_states_group_header_when_unselected() -> None:
    """The first row of an unselected multiplet becomes a group header."""
    presenter = LineSelectionPresenter()
    rep = _line("rep", wavelength=1215.0, oscillator_strength=0.5, component_index=0)
    member = _line("member", wavelength=1216.0, oscillator_strength=0.1, component_index=1)
    view = _FakeSelectionView()

    roles = presenter.build_highlight_states([rep, member], selection=view)

    assert roles[0] is RowHighlightRole.GROUP_HEADER
    assert roles[1] is RowHighlightRole.NONE
