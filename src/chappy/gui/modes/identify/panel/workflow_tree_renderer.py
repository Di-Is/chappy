"""Tree item rendering helpers for the identify workflow sections."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

from chappy.gui.modes.identify.panel.panel_models import (
    CandidateLineRow,
    ConfirmedGroupItemPayload,
    ConfirmedLineRow,
    ConfirmedRegionRow,
    ConfirmedSystemItemPayload,
    RegionPreviewRow,
    TemporarySystemItemPayload,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True, slots=True)
class IdentifyWorkflowTreeText:
    """Translated text used while rendering workflow tree items."""

    unknown: str
    grouped_template: str = ""
    new_region_template: str = ""
    append_region_template: str = ""
    overlap_warning: str = ""


class IdentifyWorkflowTreeRenderer:
    """Populate identify workflow tree widgets with typed item payloads."""

    def __init__(self) -> None:
        """Initialize the renderer."""

    def render_temporary_systems(
        self,
        tree: QTreeWidget,
        systems: Sequence[CandidateLineRow],
        previews: Sequence[RegionPreviewRow],
        *,
        selected_primary_ids: set[str],
        text: IdentifyWorkflowTreeText,
    ) -> None:
        """Populate the temporary tree grouped by registration previews.

        Group heading rows are non-selectable; child rows carry the temporary
        system payloads and restore the previous selection by primary ID.
        """
        tree.clear()

        row_lookup: dict[str, CandidateLineRow] = {}
        for row in systems:
            for system_id in row.system_ids:
                row_lookup[system_id] = row

        display_index = 0
        rendered_row_ids: set[int] = set()
        for preview in previews:
            member_rows = self._unique_member_rows(preview.member_system_ids, row_lookup)
            if not member_rows:
                continue
            heading = QTreeWidgetItem(tree)
            heading.setText(0, self._group_heading_text(preview, member_rows, text=text))
            heading.setFlags(Qt.ItemFlag.ItemIsEnabled)
            if preview.warning:
                heading.setToolTip(0, text.overlap_warning)

            for member_row in self._sorted_rows(member_rows):
                rendered_row_ids.add(id(member_row))
                display_index += 1
                self._add_temporary_item(
                    heading,
                    member_row,
                    display_index=display_index,
                    selected_primary_ids=selected_primary_ids,
                    text=text,
                )
            heading.setExpanded(True)

        for row in self._sorted_rows(systems):
            if id(row) in rendered_row_ids:
                continue
            display_index += 1
            self._add_temporary_item(
                tree,
                row,
                display_index=display_index,
                selected_primary_ids=selected_primary_ids,
                text=text,
            )

    def render_confirmed_groups(
        self,
        tree: QTreeWidget,
        groups: Sequence[ConfirmedRegionRow],
        *,
        text: IdentifyWorkflowTreeText,
    ) -> None:
        """Populate the group tree with confirmed groups."""
        tree.clear()
        for group in groups:
            self.create_group_item(
                tree=tree,
                group_id=group.group_id,
                label=group.label,
                systems=group.systems,
                is_expanded=group.is_expanded,
                text=text,
            )

    def create_group_item(
        self,
        *,
        tree: QTreeWidget,
        group_id: str,
        label: str,
        systems: Sequence[ConfirmedLineRow],
        is_expanded: bool,
        text: IdentifyWorkflowTreeText,
    ) -> QTreeWidgetItem:
        """Create a confirmed group item and its system children."""
        group_item = QTreeWidgetItem(tree)
        group_item.setText(0, label)
        group_item.setData(0, Qt.ItemDataRole.UserRole, ConfirmedGroupItemPayload(group_id))

        for system in systems:
            self.add_confirmed_system_item(group_item, system, text=text)

        group_item.setExpanded(is_expanded)
        return group_item

    def add_confirmed_system_item(
        self, parent: QTreeWidgetItem, system: ConfirmedLineRow, *, text: IdentifyWorkflowTreeText
    ) -> QTreeWidgetItem:
        """Add a confirmed system item as a child of the given parent."""
        base_label = self._system_display_name(system, text=text)
        system_label = f"{system.display_id}. {base_label}" if system.display_id else base_label
        system_text = f"{system_label} [z={system.redshift:.4f}]"

        system_item = QTreeWidgetItem(parent)
        system_item.setText(0, system_text)
        system_item.setData(
            0, Qt.ItemDataRole.UserRole, ConfirmedSystemItemPayload(system.system_id)
        )
        return system_item

    def format_candidate_line(self, system: CandidateLineRow, *, display_index: int) -> str:
        """Format a candidate line for list display."""
        base_label = self.temporary_display_name(system)
        prefix = f"{display_index}. "
        z_part = f"[z={system.redshift:.4f}]" if system.redshift is not None else ""
        range_part = f"@ {system.lambda_start:.1f}-{system.lambda_end:.1f}"
        return f"{prefix}{base_label} {z_part} {range_part}".strip()

    def temporary_display_name(self, system: CandidateLineRow) -> str:
        """Return the preferred display label for a temporary system."""
        if system.multiplet_label:
            return system.multiplet_label
        return system.transition_name

    def _add_temporary_item(
        self,
        parent: QTreeWidget | QTreeWidgetItem,
        system: CandidateLineRow,
        *,
        display_index: int,
        selected_primary_ids: set[str],
        text: IdentifyWorkflowTreeText,
    ) -> None:
        primary_id = system.system_ids[0]
        tree_item = QTreeWidgetItem(
            [self.format_candidate_line(system, display_index=display_index)]
        )
        tree_item.setData(
            0,
            Qt.ItemDataRole.UserRole,
            TemporarySystemItemPayload(primary_system_id=primary_id, system_ids=system.system_ids),
        )

        member_count = len(system.system_ids)
        if member_count > 1:
            tree_item.setToolTip(0, text.grouped_template.format(count=member_count))

        if isinstance(parent, QTreeWidget):
            parent.addTopLevelItem(tree_item)
        else:
            parent.addChild(tree_item)
        if primary_id in selected_primary_ids:
            tree_item.setSelected(True)

    def _group_heading_text(
        self,
        preview: RegionPreviewRow,
        member_rows: Sequence[CandidateLineRow],
        *,
        text: IdentifyWorkflowTreeText,
    ) -> str:
        count = len(member_rows)
        if preview.is_existing_group:
            heading = text.append_region_template.format(region=preview.label, count=count)
        else:
            species = member_rows[0].species or text.unknown
            heading = text.new_region_template.format(
                species=species,
                start=min(row.lambda_start for row in member_rows),
                end=max(row.lambda_end for row in member_rows),
                count=count,
            )
        if preview.warning:
            heading = f"{heading} ⚠"
        return heading

    @staticmethod
    def _unique_member_rows(
        member_system_ids: Sequence[str], row_lookup: dict[str, CandidateLineRow]
    ) -> list[CandidateLineRow]:
        rows: list[CandidateLineRow] = []
        seen: set[int] = set()
        for member_id in member_system_ids:
            row = row_lookup.get(member_id)
            if row is None or id(row) in seen:
                continue
            seen.add(id(row))
            rows.append(row)
        return rows

    @staticmethod
    def _sorted_rows(rows: Sequence[CandidateLineRow]) -> list[CandidateLineRow]:
        return sorted(
            rows, key=lambda row: row.redshift if row.redshift is not None else float("inf")
        )

    def _system_display_name(
        self, system: ConfirmedLineRow, *, text: IdentifyWorkflowTreeText
    ) -> str:
        label = (system.transition_name or "").strip()
        if not label:
            label = (system.species or "").strip()
        if label:
            return label
        return text.unknown
