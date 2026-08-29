"""Pure presentation helpers for velocity grid state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from chappy.presentation.velocity.selection_model import resolve_velocity_slice_selection

if TYPE_CHECKING:
    from chappy.presentation.velocity.grid_presenter import VelocityGridPage
    from chappy.presentation.velocity.view_model import VelocitySliceInfo


class SlotLabelBuilder(Protocol):
    """Callable boundary for slot-label creation."""

    def __call__(self, slot_number: int) -> str:
        """Return the label for an empty slot."""
        ...


@dataclass(frozen=True, slots=True)
class VelocityPaginationState:
    """Read-only pagination state for the velocity grid."""

    current_page: int
    one_based_page: int
    total_pages: int
    can_go_previous: bool
    can_go_next: bool
    page_size: int
    visible_count: int


@dataclass(frozen=True, slots=True)
class VelocityVisibleSliceState:
    """Read-only visible subplot state for one grid slot."""

    slot_number: int
    absolute_index: int | None
    title: str
    primary: bool
    selected: bool
    selection_enabled: bool


def build_velocity_pagination_state(page: VelocityGridPage) -> VelocityPaginationState:
    """Convert grid page data into a read-only pagination snapshot."""
    return VelocityPaginationState(
        current_page=page.current_page,
        one_based_page=page.one_based_page,
        total_pages=page.total_pages,
        can_go_previous=page.current_page > 0,
        can_go_next=page.total_pages > 0 and page.current_page < (page.total_pages - 1),
        page_size=page.page_size,
        visible_count=page.visible_count,
    )


def build_visible_slice_states(
    *,
    slices: tuple[VelocitySliceInfo, ...],
    page: VelocityGridPage,
    slot_label_builder: SlotLabelBuilder,
) -> tuple[VelocityVisibleSliceState, ...]:
    """Return read-only slot states for the current page."""
    states: list[VelocityVisibleSliceState] = []
    for local_index in range(page.page_size):
        slot_number = page.slot_number(local_index)
        absolute_index = page.absolute_index(local_index)
        if absolute_index >= len(slices):
            states.append(
                VelocityVisibleSliceState(
                    slot_number=slot_number,
                    absolute_index=None,
                    title=slot_label_builder(slot_number),
                    primary=False,
                    selected=False,
                    selection_enabled=False,
                )
            )
            continue

        slice_info = slices[absolute_index]
        states.append(
            VelocityVisibleSliceState(
                slot_number=slot_number,
                absolute_index=absolute_index,
                title=slice_info.label,
                primary=slice_info.is_primary,
                selected=resolve_velocity_slice_selection(slice_info),
                selection_enabled=True,
            )
        )
    return tuple(states)


def compute_auto_flux_range(
    observed_ranges: tuple[tuple[float, float] | None, ...],
) -> tuple[float, float] | None:
    """Return the unified auto Y range for visible observed data."""
    y_min_all = float("inf")
    y_max_all = float("-inf")
    for observed_range in observed_ranges:
        if observed_range is None:
            continue
        y_min_all = min(y_min_all, observed_range[0])
        y_max_all = max(y_max_all, observed_range[1])

    if y_min_all == float("inf"):
        return None

    return min(y_min_all - 0.05, -0.05), max(y_max_all + 0.05, 1.05)
