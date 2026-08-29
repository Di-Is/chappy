"""Preset workflow controller for identify mode."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from chappy.core.presets import preset_tie_group_key
from chappy.gui.modes.identify.panel import panel_models

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from chappy.core.atomic_data import AtomicLine, AtomicLineData
    from chappy.core.presets import Preset
    from chappy.gui.modes.identify.adapters import IdentifyPresetAdapter
    from chappy.gui.modes.identify.presets.preset_store import IdentifyPresetStore


class IdentifyPresetPanelPort(Protocol):
    """Panel operations required by identify preset workflow."""

    def set_presets(self, presets: list[tuple[str, str]], current: str | None = None) -> None:
        """Display preset options and active preset."""
        ...

    def set_line_items(self, items: list[panel_models.LineListItem]) -> None:
        """Display atomic line entries for the active preset."""
        ...


@dataclass(frozen=True, slots=True)
class IdentifyPresetMessages:
    """Translated messages emitted by preset workflow."""

    baseline_updated: str
    selection_missing: str


@dataclass(frozen=True, slots=True)
class IdentifyPresetCallbacks:
    """Callbacks required by the preset workflow owner."""

    status_callback: Callable[[str], None]
    hide_velocity_plot_callback: Callable[[], None]
    reapply_cursor_preview_callback: Callable[[], None]
    refresh_velocity_overlay_callback: Callable[[], None]
    messages_provider: Callable[[], IdentifyPresetMessages]
    velocity_active_provider: Callable[[], bool]


class IdentifyPresetController:
    """Synchronize identify preset store state with the side panel."""

    def __init__(
        self,
        *,
        store: IdentifyPresetStore,
        atomic_data: AtomicLineData,
        callbacks: IdentifyPresetCallbacks,
        adapter: IdentifyPresetAdapter,
    ) -> None:
        """Initialize the preset controller."""
        self._store = store
        self._atomic_data = atomic_data
        self._callbacks = callbacks
        self._adapter = adapter
        self._panel: IdentifyPresetPanelPort | None = None
        self._current_preset_id: str | None = store.current_preset_id
        self._derived_cache_token: tuple[str, float | None] | None = None
        self._line_cache: list[AtomicLine] = []
        self._tie_group_keys_cache: dict[str, str] = {}
        self._baseline_refresh_guard = 0

    @property
    def current_preset_id(self) -> str | None:
        """Return the current preset id tracked by the controller."""
        return self._current_preset_id

    def set_panel(self, panel: IdentifyPresetPanelPort | None) -> None:
        """Update the panel sink for preset display data."""
        self._panel = panel

    def set_atomic_data(self, atomic_data: AtomicLineData) -> None:
        """Update the atomic data source and clear cached line rows."""
        if atomic_data is self._atomic_data:
            return
        self._atomic_data = atomic_data
        self._clear_line_cache()

    def refresh_presets(self) -> None:
        """Refresh preset options and line rows in the panel."""
        if self._panel is None:
            return

        self._clear_line_cache()
        result = self._adapter.build_result(
            self._store.list_presets(), self._store.current_preset_id, self._atomic_data
        )
        if not result.options:
            self._panel.set_presets([], None)
            self._panel.set_line_items([])
            return

        if self._store.current_preset_id != result.current_id:
            self._store.set_current_preset(result.current_id)
        self._current_preset_id = result.current_id
        self._panel.set_presets(list(result.options), result.current_id)

        line_items = [
            panel_models.LineListItem(
                identifier=atomic_line.line_id,
                reference=atomic_line.species,
                name=atomic_line.transition_name or atomic_line.species,
                wavelength=atomic_line.wavelength_angstrom,
                oscillator_strength=atomic_line.oscillator_strength,
                is_reference=atomic_line.line_id == result.baseline_id,
                multiplet_id=atomic_line.multiplet_id or "",
            )
            for atomic_line in result.line_items
        ]
        line_items.sort(key=lambda item: item.wavelength)
        self._panel.set_line_items(line_items)
        self._callbacks.reapply_cursor_preview_callback()

    def handle_store_selection_changed(self, preset_id: str | None) -> None:
        """Handle selection change emitted by the preset store."""
        previous_id = self._current_preset_id
        try:
            self._store.set_current_preset(preset_id)
        except KeyError:
            self._callbacks.status_callback(self._callbacks.messages_provider().selection_missing)
            return

        self._current_preset_id = preset_id
        if (
            self._callbacks.velocity_active_provider()
            and previous_id is not None
            and preset_id is not None
            and preset_id != previous_id
        ):
            self._callbacks.hide_velocity_plot_callback()

        self.refresh_presets()

    def handle_panel_preset_changed(self, preset_id: str) -> None:
        """Handle preset selection requested by the panel."""
        if not preset_id or preset_id == self._store.current_preset_id:
            return
        try:
            self._store.set_current_preset(preset_id)
        except KeyError:
            self._callbacks.status_callback(self._callbacks.messages_provider().selection_missing)
            self.refresh_presets()

    def handle_preset_updated(self, preset_id: str) -> None:
        """Refresh preset display after the active preset changes."""
        if preset_id != self._store.current_preset_id:
            return
        if self._baseline_refresh_guard > 0:
            self._callbacks.refresh_velocity_overlay_callback()
            return
        self.refresh_presets()
        self._callbacks.refresh_velocity_overlay_callback()

    def handle_reference_line_changed(self, line_id: str) -> None:
        """Persist baseline line change requested by the panel."""
        preset_id = self._store.current_preset_id
        if not preset_id:
            return
        self._baseline_refresh_guard += 1
        try:
            self._store.set_baseline(preset_id, line_id)
        finally:
            self._baseline_refresh_guard -= 1
        self._callbacks.status_callback(self._callbacks.messages_provider().baseline_updated)
        self._callbacks.reapply_cursor_preview_callback()
        self._callbacks.refresh_velocity_overlay_callback()

    def current_preset(self) -> Preset | None:
        """Return the current preset snapshot from the store."""
        preset_id = self._store.current_preset_id
        if not preset_id:
            return None
        return self._store.get_preset(preset_id)

    def current_tie_group_keys(self) -> Mapping[str, str]:
        """Return line identifiers mapped to transient declarative group keys."""
        self._refresh_derived_cache()
        return self._tie_group_keys_cache

    def collect_current_lines(self) -> list[AtomicLine]:
        """Return atomic lines for the current preset, using a local cache."""
        self._refresh_derived_cache()
        return list(self._line_cache)

    def _refresh_derived_cache(self) -> None:
        """Rebuild cached preset-derived state when the preset revision changes."""
        preset_id = self._store.current_preset_id
        if not preset_id:
            self._clear_line_cache()
            return

        token = (preset_id, self._store.preset_revision(preset_id))
        if token == self._derived_cache_token:
            return

        preset = self._store.get_preset(preset_id)
        if preset is None:
            self._clear_line_cache()
            return

        self._line_cache = [
            atomic_line
            for line_id in preset.line_ids
            if (atomic_line := self._atomic_data.get_line_by_id(line_id)) is not None
        ]
        self._tie_group_keys_cache = {
            line_id: preset_tie_group_key(preset.id, group.uid)
            for group in preset.tie_groups
            for line_id in group.line_ids
        }
        self._derived_cache_token = token

    def _clear_line_cache(self) -> None:
        self._derived_cache_token = None
        self._line_cache = []
        self._tie_group_keys_cache = {}
