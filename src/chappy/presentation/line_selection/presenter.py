"""Qt-independent line selection presentation helpers."""

from __future__ import annotations

import html
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from chappy.core.atomic_data import AtomicLine

type SortKey = tuple[object, object, object]


class SelectionView(Protocol):
    """Read-only view of the working line selection.

    Implemented structurally by the application ``LineSelectionSession`` so the
    presentation layer can query aggregated state without importing the
    application layer.
    """

    @property
    def selected_ids(self) -> frozenset[str]:
        """User-selected line identifiers."""
        ...

    @property
    def existing_ids(self) -> frozenset[str]:
        """Locked, already-selected line identifiers."""
        ...

    def is_aggregated_selected(self, line: AtomicLine) -> bool:
        """Return whether the line or any multiplet companion is selected."""
        ...


@dataclass(slots=True)
class MultipletSummary:
    """Aggregated display and sorting state for one multiplet."""

    label: str
    representative_id: str
    representative_rank: tuple[float, float, float, str]
    wavelength_min: float
    f_value_max: float
    gamma_min: float


@dataclass(frozen=True, slots=True)
class LinePreviewLabels:
    """Translated labels used to render line preview HTML."""

    element: str
    ion_stage: str
    species: str
    multiplet: str
    component: str
    rest_wavelength: str
    ritz_wavelength: str
    ritz_uncertainty: str
    observed_wavelength: str
    observed_uncertainty: str
    source: str
    oscillator_f: str
    gamma: str
    lower_level_ev: str
    upper_level_ev: str
    delta_e_ev: str
    lower_level: str
    upper_level: str
    accuracy: str
    transition_ref: str
    wavelength_ref: str
    notes: str
    basic_information: str
    wavelength_strength: str
    energy_levels: str
    references: str
    source_ritz: str
    source_observed: str
    source_aggregated: str
    source_custom: str


@dataclass(frozen=True, slots=True)
class LineRowLabels:
    """Translated labels used to build result-table rows."""

    multiplet_header: str
    multiplet_tooltip: str


class RowHighlightRole(StrEnum):
    """Semantic background role for a result-table row."""

    NONE = "none"
    EXISTING = "existing"
    HIGHLIGHT = "highlight"
    GROUP_HEADER = "group_header"


@dataclass(frozen=True, slots=True)
class LineRowPayload:
    """Qt-independent display data for one result-table row."""

    line_id: str
    display_name: str
    wavelength_text: str
    f_value_text: str
    gamma_text: str
    wavelength_value: float
    f_value: float
    gamma_value: float
    is_existing: bool
    is_multiplet_member: bool
    is_selectable: bool
    has_multiplet: bool
    aggregated_selected: bool
    accessible_text: str
    name_tooltip: str
    name_sort_key: SortKey
    wavelength_sort_key: SortKey
    f_value_sort_key: SortKey
    gamma_sort_key: SortKey
    selection_sort_key: SortKey


class LineSelectionPresenter:
    """Build presentation state for the line selection dialog."""

    @staticmethod
    def representative_rank(line: AtomicLine) -> tuple[float, float, float, str]:
        """Generate sort key for multiplet representative selection.

        Args:
            line: Atomic line to rank.

        Returns:
            Sort key ordered by descending f-value, component index, wavelength, and ID.
        """
        component = (
            float(line.component_index) if line.component_index is not None else float("inf")
        )
        f_value = -line.oscillator_strength if line.oscillator_strength else float("inf")
        return (f_value, component, float(line.wavelength_angstrom), line.line_id)

    def compute_multiplet_summaries(
        self, lines: Iterable[AtomicLine]
    ) -> dict[str, MultipletSummary]:
        """Compute multiplet display summaries.

        Args:
            lines: Atomic lines to inspect.

        Returns:
            Multiplet summaries keyed by multiplet ID.
        """
        summaries: dict[str, MultipletSummary] = {}
        for line in lines:
            if not line.multiplet_id:
                continue
            summary = summaries.get(line.multiplet_id)
            rank = self.representative_rank(line)
            if summary is None:
                summaries[line.multiplet_id] = MultipletSummary(
                    label=line.multiplet_label or line.multiplet_id,
                    representative_id=line.line_id,
                    representative_rank=rank,
                    wavelength_min=line.wavelength_angstrom,
                    f_value_max=line.oscillator_strength,
                    gamma_min=line.gamma_value,
                )
                continue

            summary.wavelength_min = min(summary.wavelength_min, line.wavelength_angstrom)
            summary.f_value_max = max(summary.f_value_max, line.oscillator_strength)
            summary.gamma_min = min(summary.gamma_min, line.gamma_value)
            if rank < summary.representative_rank:
                summary.representative_rank = rank
                summary.representative_id = line.line_id

        return summaries

    def build_row_payloads(
        self, lines: Sequence[AtomicLine], *, selection: SelectionView, labels: LineRowLabels
    ) -> list[LineRowPayload]:
        """Build display payloads for the result table.

        Args:
            lines: Filtered atomic lines in their natural (pre-sort) order.
            selection: Working selection used for aggregated checkbox state.
            labels: Translated labels for multiplet text and tooltips.

        Returns:
            One payload per line, in input order.
        """
        summaries = self.compute_multiplet_summaries(lines)
        representatives = {
            multiplet_id: summary.representative_id for multiplet_id, summary in summaries.items()
        }
        existing_ids = selection.existing_ids
        return [
            self._build_row_payload(
                line, summaries, representatives, existing_ids, selection, labels
            )
            for line in lines
        ]

    def build_highlight_states(
        self, ordered_lines: Sequence[AtomicLine], *, selection: SelectionView
    ) -> list[RowHighlightRole]:
        """Compute the highlight role for each row in display order.

        Args:
            ordered_lines: Lines in the order they are displayed (post-sort).
            selection: Working selection used to resolve highlighted multiplets.

        Returns:
            One highlight role per line, in display order.
        """
        selected_multiplets = {
            line.multiplet_id
            for line in ordered_lines
            if line.multiplet_id and selection.is_aggregated_selected(line)
        }
        existing_ids = selection.existing_ids
        roles: list[RowHighlightRole] = []
        last_multiplet_id: str | None = None
        for line in ordered_lines:
            first_in_group = False
            if line.multiplet_id:
                if line.multiplet_id != last_multiplet_id:
                    first_in_group = True
                    last_multiplet_id = line.multiplet_id
            else:
                last_multiplet_id = None

            if line.line_id in existing_ids:
                roles.append(RowHighlightRole.EXISTING)
            elif line.multiplet_id and line.multiplet_id in selected_multiplets:
                roles.append(RowHighlightRole.HIGHLIGHT)
            elif first_in_group:
                roles.append(RowHighlightRole.GROUP_HEADER)
            else:
                roles.append(RowHighlightRole.NONE)
        return roles

    def _build_row_payload(
        self,
        line: AtomicLine,
        summaries: dict[str, MultipletSummary],
        representatives: dict[str, str],
        existing_ids: frozenset[str],
        selection: SelectionView,
        labels: LineRowLabels,
    ) -> LineRowPayload:
        """Build a single result-table row payload."""
        is_existing = line.line_id in existing_ids
        is_representative = (not line.multiplet_id) or representatives.get(
            line.multiplet_id, line.line_id
        ) == line.line_id
        is_multiplet_member = bool(line.multiplet_id and not is_representative)
        is_selectable = not is_existing

        display_name = (
            f"  └ {line.transition_name}" if is_multiplet_member else line.transition_name
        )

        name_tooltip = labels.multiplet_tooltip if line.multiplet_id else ""

        summary = summaries.get(line.multiplet_id or "")
        label_aggregate = summary.label if summary else None
        accessible_text = f"{labels.multiplet_header} {label_aggregate}" if label_aggregate else ""
        return LineRowPayload(
            line_id=line.line_id,
            display_name=display_name,
            wavelength_text=f"{line.wavelength_angstrom:.3f}",
            f_value_text=f"{line.oscillator_strength:.5f}",
            gamma_text=f"{line.gamma_value:.2e}",
            wavelength_value=line.wavelength_angstrom,
            f_value=line.oscillator_strength,
            gamma_value=line.gamma_value,
            is_existing=is_existing,
            is_multiplet_member=is_multiplet_member,
            is_selectable=is_selectable,
            has_multiplet=bool(line.multiplet_id),
            aggregated_selected=selection.is_aggregated_selected(line),
            accessible_text=accessible_text,
            name_tooltip=name_tooltip,
            name_sort_key=self._make_sort_key(label_aggregate, line.transition_name, line.line_id),
            wavelength_sort_key=self._wavelength_sort_key(line, summary),
            f_value_sort_key=self._make_sort_key(
                summary.f_value_max if summary else None, line.oscillator_strength, line.line_id
            ),
            gamma_sort_key=self._make_sort_key(
                summary.gamma_min if summary else None, line.gamma_value, line.line_id
            ),
            selection_sort_key=self._selection_sort_key(line, summaries),
        )

    def _make_sort_key(self, aggregated: object, actual: object, line_id: str) -> SortKey:
        """Build a (aggregated, actual, id) sort key, normalizing values."""
        resolved = actual if aggregated is None else aggregated
        return (self._normalize_sort_value(resolved), self._normalize_sort_value(actual), line_id)

    def _wavelength_sort_key(self, line: AtomicLine, summary: MultipletSummary | None) -> SortKey:
        """Build the wavelength-column key, keeping each multiplet's representative first."""
        group_position = summary.wavelength_min if summary else line.wavelength_angstrom
        member_rank = 0 if summary is None or line.line_id == summary.representative_id else 1
        return (
            float(group_position),
            (member_rank, float(line.wavelength_angstrom)),
            line.line_id,
        )

    def _selection_sort_key(
        self, line: AtomicLine, summaries: dict[str, MultipletSummary]
    ) -> SortKey:
        """Build the checkbox-column sort key grouping multiplets together."""
        component_rank = self.representative_rank(line)
        if line.multiplet_id and line.multiplet_id in summaries:
            group_rank = summaries[line.multiplet_id].representative_rank
        else:
            group_rank = component_rank
        return (group_rank, component_rank, line.line_id)

    @staticmethod
    def _normalize_sort_value(value: object) -> object:
        """Coerce a value to a consistent, comparable representation."""
        if isinstance(value, int | float):
            return float(value)
        if value is None:
            return ""
        return str(value)


class LinePreviewPresenter:
    """Render atomic line preview HTML without Qt dependencies."""

    def render_section(self, title: str, rows: list[tuple[str, str]]) -> str:
        """Render one preview section.

        Args:
            title: Section title.
            rows: Label/value rows. Empty values are omitted.

        Returns:
            HTML fragment for the section.
        """
        display_rows = [(label, value) for label, value in rows if value]
        if not display_rows:
            return ""
        body = "".join(
            f"<tr><th scope='row'>{html.escape(label)}</th><td>{value}</td></tr>"
            for label, value in display_rows
        )
        return (
            f"<div class='line-preview-section'>"
            f"<h4>{html.escape(title)}</h4>"
            f"<table class='line-preview-table'>{body}</table>"
            f"</div>"
        )

    @staticmethod
    def _format_float(
        value: float | None, *, precision: int = 4, fmt: str = "f", unit: str = ""
    ) -> str:
        """Format a floating point value for a preview row."""
        if value is None:
            return ""
        formatted = f"{value:.2e}" if fmt == "e" else f"{value:.{precision}{fmt}}"
        return f"{formatted} {unit}".strip()

    @staticmethod
    def _format_level_details(
        configuration: str, term: str, j_value: str, *, extra: str | None = None
    ) -> str:
        """Format atomic level configuration/term/J details."""
        parts = [part for part in (configuration, term, extra) if part]
        if j_value:
            parts.append(f"J={j_value}")
        return " • ".join(parts)

    @staticmethod
    def _wavelength_source_label(source: str, labels: LinePreviewLabels) -> str:
        """Map a raw wavelength source string to a translated label."""
        if not source:
            return ""
        normalized = source.strip().lower()
        mapping = {
            "ritz": labels.source_ritz,
            "observed": labels.source_observed,
            "aggregated": labels.source_aggregated,
            "custom": labels.source_custom,
        }
        return mapping.get(normalized, source)

    def render_preview_html(self, line: AtomicLine, *, labels: LinePreviewLabels) -> str:
        """Render a complete atomic line preview.

        Args:
            line: Atomic line to render.
            labels: Translated preview labels.

        Returns:
            HTML for the preview panel.
        """
        format_float = self._format_float
        heading = html.escape(line.transition_name)

        basic_rows: list[tuple[str, str]] = []
        element_value = line.element_symbol or line.element
        if element_value:
            basic_rows.append((labels.element, html.escape(element_value)))
        stage = line.ionization_stage
        if stage:
            basic_rows.append((labels.ion_stage, html.escape(stage)))
        species_label = line.species.strip()
        if species_label and species_label != element_value:
            basic_rows.append((labels.species, html.escape(species_label)))
        if line.multiplet_label:
            basic_rows.append((labels.multiplet, html.escape(line.multiplet_label)))
        if line.component_index is not None:
            basic_rows.append((labels.component, html.escape(str(line.component_index))))

        strength_rows: list[tuple[str, str]] = [
            (
                labels.rest_wavelength,
                html.escape(format_float(line.wavelength_angstrom, precision=4, unit="Å")),
            )
        ]
        if line.wavelength_ritz is not None:
            strength_rows.append(
                (
                    labels.ritz_wavelength,
                    html.escape(format_float(line.wavelength_ritz, precision=4, unit="Å")),
                )
            )
        if line.wavelength_observed is not None:
            strength_rows.append(
                (
                    labels.observed_wavelength,
                    html.escape(format_float(line.wavelength_observed, precision=4, unit="Å")),
                )
            )
        strength_rows.extend(
            [
                (
                    labels.oscillator_f,
                    html.escape(format_float(line.oscillator_strength, precision=6, unit="")),
                ),
                (labels.gamma, html.escape(format_float(line.gamma_value, fmt="e"))),
            ]
        )
        source_label = self._wavelength_source_label(line.wavelength_source, labels)
        if source_label:
            strength_rows.append((labels.source, html.escape(source_label)))

        levels_rows: list[tuple[str, str]] = []
        if line.energy_lower_ev is not None:
            levels_rows.append(
                (
                    labels.lower_level_ev,
                    html.escape(format_float(line.energy_lower_ev, precision=4)),
                )
            )
        if line.energy_upper_ev is not None:
            levels_rows.append(
                (
                    labels.upper_level_ev,
                    html.escape(format_float(line.energy_upper_ev, precision=4)),
                )
            )
        energy_gap = line.energy_gap_ev
        if energy_gap is not None:
            levels_rows.append(
                (labels.delta_e_ev, html.escape(format_float(energy_gap, precision=4)))
            )

        lower_details = self._format_level_details(
            line.lower_configuration, line.lower_term, line.lower_j
        )
        if lower_details:
            levels_rows.append((labels.lower_level, html.escape(lower_details)))
        upper_details = self._format_level_details(
            line.upper_configuration, line.upper_term, line.upper_j, extra=line.upper_term_ls
        )
        if upper_details:
            levels_rows.append((labels.upper_level, html.escape(upper_details)))

        reference_rows: list[tuple[str, str]] = []
        if line.wavelength_ritz_uncertainty is not None:
            reference_rows.append(
                (
                    labels.ritz_uncertainty,
                    html.escape(
                        format_float(line.wavelength_ritz_uncertainty, precision=4, unit="Å")
                    ),
                )
            )
        if line.wavelength_observed_uncertainty is not None:
            reference_rows.append(
                (
                    labels.observed_uncertainty,
                    html.escape(
                        format_float(line.wavelength_observed_uncertainty, precision=4, unit="Å")
                    ),
                )
            )
        if line.accuracy_code:
            reference_rows.append((labels.accuracy, html.escape(line.accuracy_code)))
        if line.transition_probability_ref:
            reference_rows.append(
                (labels.transition_ref, html.escape(line.transition_probability_ref))
            )
        if line.wavelength_ref:
            reference_rows.append((labels.wavelength_ref, html.escape(line.wavelength_ref)))

        sections = [
            f"<h3>{heading}</h3>",
            self.render_section(labels.wavelength_strength, strength_rows),
            self.render_section(labels.basic_information, basic_rows),
            self.render_section(labels.energy_levels, levels_rows),
            self.render_section(labels.references, reference_rows),
        ]

        comment_text = line.comments.strip()
        if comment_text:
            comment_html = html.escape(comment_text).replace("\n", "<br>")
            sections.append(
                f"<div class='line-preview-section'><h4>{html.escape(labels.notes)}</h4>"
                f"<p>{comment_html}</p></div>"
            )

        return "".join(section for section in sections if section)
