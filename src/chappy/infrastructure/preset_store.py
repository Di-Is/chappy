"""Infrastructure-backed preset store persistence and sharing operations."""

from __future__ import annotations

import hashlib
import json
import logging
from contextlib import suppress
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING, Any

from chappy.core.presets import (
    Preset,
    PresetExportError,
    PresetImportEntry,
    PresetImportError,
    PresetImportSummary,
    PresetStore,
    PresetTieGroup,
    TranslateFunc,
)
from chappy.infrastructure.atomic_lines import AtomicLineCsvRepository

if TYPE_CHECKING:
    from collections.abc import Sequence

    from chappy.core.atomic_data import AtomicLineData, LineIdentifier

logger = logging.getLogger(__name__)

DEFAULT_PRESET_PATH = Path.home() / ".chappy" / "presets.json"
PRESET_FILE_SCHEMA_VERSION = "1.2"

_EXPORT_ERROR_MESSAGE = "Failed to export presets"
_IMPORT_NOT_FOUND_MESSAGE = "Import file not found"
_IMPORT_PARSE_MESSAGE = "Import file could not be parsed"
_IMPORT_READ_MESSAGE = "Unable to read import file"
_IMPORT_PAYLOAD_MESSAGE = "Preset payload missing 'presets' array"


def _application_version() -> str:
    try:
        return version("chappy")
    except PackageNotFoundError:  # pragma: no cover - fallback during dev
        return "0.0.0"


APP_VERSION = _application_version()


def _now() -> datetime:
    """Return a timezone-aware timestamp for infrastructure defaults."""
    return datetime.now(UTC)


def _format_timestamp(value: datetime) -> str:
    """Format timestamps for preset JSON payloads."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_timestamp(raw: object) -> datetime | None:
    """Parse optional persisted timestamps."""
    if not isinstance(raw, str) or not raw:
        return None
    text = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
    try:
        result = datetime.fromisoformat(text)
    except ValueError:
        logger.debug("Skipping invalid timestamp '%s'", raw)
        return None
    if result.tzinfo is None:
        return result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


class PersistentPresetStore:
    """Preset store adapter with JSON persistence and import/export support."""

    def __init__(
        self,
        atomic_data: AtomicLineData,
        *,
        storage_path: str | Path | None = None,
        translate: TranslateFunc,
    ) -> None:
        """Initialize persistent store and recover existing user presets."""
        self._atomic_data = atomic_data
        self._storage_path = (
            Path(storage_path).expanduser() if storage_path is not None else DEFAULT_PRESET_PATH
        )
        self._store = PresetStore(atomic_data, translate=translate)
        self._load_from_disk()

    @property
    def current_preset_id(self) -> str | None:
        """Return active preset selection identifier."""
        return self._store.current_preset_id

    def list_presets(self) -> list[Preset]:
        """Return all presets as independent snapshots."""
        return self._store.list_presets()

    def get_preset(self, preset_id: str) -> Preset | None:
        """Return snapshot of preset matching identifier."""
        return self._store.get_preset(preset_id)

    def preset_revision(self, preset_id: str) -> float | None:
        """Return the preset's updated-at token without cloning the preset."""
        return self._store.preset_revision(preset_id)

    def set_current_preset(self, preset_id: str | None) -> None:
        """Mark preset as currently selected and persist the selection."""
        self._store.set_current_preset(preset_id)
        self._persist()

    def set_translator(self, translate: TranslateFunc) -> None:
        """Update translator callable and refresh default preset labels."""
        self._store.set_translator(translate)

    def export_presets(
        self,
        destination: str | Path,
        preset_ids: Sequence[str] | None = None,
        *,
        include_names: bool = True,
    ) -> Path:
        """Export presets to a JSON file compatible with the shared schema."""
        path = Path(destination).expanduser()
        if path.suffix.lower() != ".json":
            path = path.with_suffix(".json")

        if preset_ids is None:
            ordered_ids = [preset.id for preset in self._store.list_presets()]
        else:
            ordered_ids = []
            for preset_id in preset_ids:
                if self._store.get_preset(preset_id) is None:
                    msg = f"Preset not found: {preset_id}"
                    raise KeyError(msg)
                ordered_ids.append(preset_id)

        payload = self._build_export_payload(ordered_ids, include_names=include_names)

        tmp_path = path.with_suffix(path.suffix + ".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tmp_path.open("w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
            tmp_path.replace(path)
        except OSError as exc:  # pragma: no cover - filesystem dependent
            with suppress(FileNotFoundError):
                tmp_path.unlink()
            logger.exception("Failed to export presets to '%s'", path)
            raise PresetExportError(_EXPORT_ERROR_MESSAGE) from exc

        return path

    def import_presets(self, source: str | Path) -> PresetImportSummary:
        """Import presets from a JSON file and merge them into the store."""
        path = Path(source).expanduser()
        raw_entries = self._read_import_entries(path)
        entries, skipped = self._decode_import_entries(raw_entries)
        summary = self._store.import_preset_entries(entries, skipped=skipped)
        if summary.imported:
            self._persist()
        return summary

    def create_custom_preset(
        self,
        name: str,
        *,
        line_ids: Sequence[LineIdentifier] | None = None,
        baseline_id: LineIdentifier | None = None,
        description: str = "",
    ) -> Preset:
        """Create a new custom preset and persist it."""
        preset = self._store.create_custom_preset(
            name, line_ids=line_ids, baseline_id=baseline_id, description=description
        )
        self._persist()
        return preset

    def rename_preset(self, preset_id: str, new_name: str) -> Preset:
        """Rename existing custom preset and persist it."""
        preset = self._store.rename_preset(preset_id, new_name)
        self._persist()
        return preset

    def duplicate_preset(self, preset_id: str) -> Preset:
        """Duplicate a preset and persist the copy."""
        preset = self._store.duplicate_preset(preset_id)
        self._persist()
        return preset

    def delete_preset(self, preset_id: str) -> None:
        """Delete custom preset by identifier and persist the change."""
        self._store.delete_preset(preset_id)
        self._persist()

    def add_tie_group(self, preset_id: str, line_ids: Sequence[LineIdentifier]) -> PresetTieGroup:
        """Add a declarative tie group and persist the updated preset."""
        group = self._store.add_tie_group(preset_id, line_ids)
        self._persist()
        return group

    def replace_tie_group_members(
        self, preset_id: str, group_uid: str, line_ids: Sequence[LineIdentifier]
    ) -> PresetTieGroup:
        """Replace a declarative tie group's members and persist it."""
        group = self._store.replace_tie_group_members(preset_id, group_uid, line_ids)
        self._persist()
        return group

    def remove_tie_group(self, preset_id: str, group_uid: str) -> None:
        """Remove a declarative tie group and persist the updated preset."""
        self._store.remove_tie_group(preset_id, group_uid)
        self._persist()

    def add_lines(
        self, preset_id: str, line_ids: Sequence[LineIdentifier]
    ) -> list[LineIdentifier]:
        """Add line identifiers to custom preset and persist changes."""
        added = self._store.add_lines(preset_id, line_ids)
        if added:
            self._persist()
        return added

    def add_lines_with_tie_groups(
        self,
        preset_id: str,
        line_ids: Sequence[LineIdentifier],
        tie_groups: Sequence[Sequence[LineIdentifier]],
    ) -> list[LineIdentifier]:
        """Add lines and tie-group declarations in one persisted mutation."""
        added = self._store.add_lines_with_tie_groups(preset_id, line_ids, tie_groups)
        self._persist()
        return added

    def remove_lines(
        self, preset_id: str, line_ids: Sequence[LineIdentifier]
    ) -> list[LineIdentifier]:
        """Remove provided line identifiers and persist changes."""
        removed = self._store.remove_lines(preset_id, line_ids)
        if removed:
            self._persist()
        return removed

    def set_baseline(self, preset_id: str, line_id: LineIdentifier | None) -> None:
        """Update baseline identifier and persist it."""
        self._store.set_baseline(preset_id, line_id)
        self._persist()

    def _load_from_disk(self) -> None:
        """Load persisted custom presets from disk."""
        path = self._storage_path
        try:
            with path.open(encoding="utf-8") as stream:
                payload = json.load(stream)
        except FileNotFoundError:
            return
        except json.JSONDecodeError as exc:
            logger.warning("Preset file '%s' is malformed: %s", path, exc)
            return
        except OSError as exc:  # pragma: no cover - unexpected IO failure
            logger.warning("Unable to read presets from '%s': %s", path, exc)
            return

        if not isinstance(payload, dict):
            logger.warning("Preset payload root is not an object")
            return

        presets_data = payload.get("presets", [])
        if not isinstance(presets_data, list):
            logger.warning("Preset payload missing 'presets' array")
            presets_data = []

        presets = [
            preset
            for entry in presets_data
            if (preset := self._deserialize_custom_preset(entry)) is not None
        ]
        selected_id = payload.get("selected_preset_id")
        current_id = selected_id if isinstance(selected_id, str) else None
        self._store.replace_custom_presets(presets, current_id=current_id)

    def _deserialize_custom_preset(self, entry: object) -> Preset | None:
        """Convert a persisted JSON entry into a preset snapshot."""
        if not isinstance(entry, dict):
            logger.debug("Ignoring preset entry %s", entry)
            return None

        try:
            preset_id = str(entry["id"])
            name = str(entry["name"])
        except (KeyError, TypeError, ValueError):
            logger.warning("Preset entry missing required identifiers: %s", entry)
            return None

        description = str(entry.get("description", ""))
        line_ids = self._collect_line_ids(entry.get("lines")) or []
        self._warn_unknown_line_ids(name, line_ids)
        baseline_value = self._decode_baseline(entry.get("baseline_id"))

        created_at = _parse_timestamp(entry.get("created_at")) or _now()
        updated_at = _parse_timestamp(entry.get("updated_at")) or created_at

        return Preset(
            id=preset_id,
            name=name,
            source="custom",
            line_ids=line_ids,
            tie_groups=self._collect_tie_groups(entry.get("groups")),
            baseline_id=baseline_value,
            description=description,
            created_at=created_at,
            updated_at=updated_at,
        )

    def _serialize_custom_preset(
        self, preset: Preset, *, include_names: bool = True
    ) -> dict[str, Any]:
        """Convert preset into JSON-friendly dictionary."""
        lines: list[dict[str, Any]] = []
        for line_id in preset.line_ids:
            text_id = str(line_id)
            entry: dict[str, Any] = {"line_id": text_id}
            if include_names:
                line = self._atomic_data.get_line_by_id(text_id)
                if line:
                    entry["name"] = line.transition_name
            lines.append(entry)

        payload: dict[str, Any] = {
            "id": str(preset.id),
            "name": str(preset.name),
            "source": preset.source,
            "created_at": _format_timestamp(preset.created_at),
            "updated_at": _format_timestamp(preset.updated_at),
            "lines": lines,
            "groups": [
                {"uid": group.uid, "line_ids": list(group.line_ids)} for group in preset.tie_groups
            ],
        }
        if preset.description:
            payload["description"] = str(preset.description)
        if preset.baseline_id:
            payload["baseline_id"] = str(preset.baseline_id)
        return payload

    def _build_persist_payload(self, *, include_names: bool) -> dict[str, Any]:
        presets_payload = [
            self._serialize_custom_preset(preset, include_names=include_names)
            for preset in self._store.list_presets()
            if preset.source == "custom"
        ]

        payload: dict[str, Any] = {
            "schema_version": PRESET_FILE_SCHEMA_VERSION,
            "app_version": APP_VERSION,
            "presets": presets_payload,
        }

        if self._store.current_preset_id:
            payload["selected_preset_id"] = self._store.current_preset_id

        return payload

    def _build_export_payload(
        self, preset_ids: Sequence[str], *, include_names: bool
    ) -> dict[str, Any]:
        presets_payload: list[dict[str, Any]] = []
        for preset_id in preset_ids:
            preset = self._store.get_preset(preset_id)
            if preset is not None:
                presets_payload.append(
                    self._serialize_custom_preset(preset, include_names=include_names)
                )

        payload: dict[str, Any] = {
            "schema_version": PRESET_FILE_SCHEMA_VERSION,
            "app_version": APP_VERSION,
            "presets": presets_payload,
        }

        database_metadata = self._resolve_database_metadata()
        if database_metadata:
            payload["database"] = database_metadata

        return payload

    def _persist(self) -> None:
        """Persist current custom presets to the user preset file."""
        path = self._storage_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:  # pragma: no cover - extremely rare
            logger.warning("Cannot create preset directory '%s': %s", path.parent, exc)
            return

        tmp_path = path.with_suffix(path.suffix + ".tmp")

        def _write_payload(payload: dict[str, Any]) -> None:
            with tmp_path.open("w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
            tmp_path.replace(path)

        try:
            payload = self._build_persist_payload(include_names=True)
            _write_payload(payload)
        except RecursionError:
            logger.exception(
                "Detected recursive preset payload while saving; writing without line names."
            )
            safe_payload = self._build_persist_payload(include_names=False)
            try:
                _write_payload(safe_payload)
            except OSError as exc:
                logger.warning("Failed to persist presets to '%s': %s", path, exc)
                with suppress(FileNotFoundError):
                    tmp_path.unlink()
        except OSError as exc:
            logger.warning("Failed to persist presets to '%s': %s", path, exc)
            with suppress(FileNotFoundError):
                tmp_path.unlink()

    def _read_import_entries(self, path: Path) -> list[object]:
        """Read raw preset entries from an import JSON file."""
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            logger.exception("Preset import file not found: %s", path)
            raise PresetImportError(_IMPORT_NOT_FOUND_MESSAGE) from exc
        except json.JSONDecodeError as exc:
            logger.exception("Preset import file parsing failed")
            raise PresetImportError(_IMPORT_PARSE_MESSAGE) from exc
        except OSError as exc:  # pragma: no cover - unexpected IO failure
            logger.exception("Unable to read preset import file: %s", path)
            raise PresetImportError(_IMPORT_READ_MESSAGE) from exc

        if not isinstance(payload, dict):
            raise PresetImportError(_IMPORT_PAYLOAD_MESSAGE)
        entries = payload.get("presets")
        if not isinstance(entries, list):
            raise PresetImportError(_IMPORT_PAYLOAD_MESSAGE)
        return entries

    def _decode_import_entries(
        self, raw_entries: Sequence[object]
    ) -> tuple[list[PresetImportEntry], int]:
        """Convert raw JSON objects into typed import entries."""
        entries: list[PresetImportEntry] = []
        skipped = 0
        for raw_entry in raw_entries:
            entry = self._decode_import_entry(raw_entry)
            if entry is None:
                skipped += 1
            else:
                entries.append(entry)
        return entries, skipped

    def _decode_import_entry(self, raw_entry: object) -> PresetImportEntry | None:
        """Decode one import entry."""
        if not isinstance(raw_entry, dict):
            return None

        line_ids = self._collect_line_ids(raw_entry.get("lines"))
        if line_ids is None:
            return None

        raw_name = raw_entry.get("name", "")
        name = str(raw_name).strip()
        self._warn_unknown_line_ids(name, line_ids)
        return PresetImportEntry(
            name=name,
            line_ids=line_ids,
            tie_groups=self._collect_tie_groups(raw_entry.get("groups")),
            baseline_id=self._decode_baseline(raw_entry.get("baseline_id")),
            description=str(raw_entry.get("description", "")),
            created_at=_parse_timestamp(raw_entry.get("created_at")),
            updated_at=_parse_timestamp(raw_entry.get("updated_at")),
        )

    def _collect_line_ids(self, raw_lines: object) -> list[LineIdentifier] | None:
        """Collect line identifiers from a persisted or imported line array."""
        if not isinstance(raw_lines, list):
            return None

        collected: list[LineIdentifier] = []
        for item in raw_lines:
            line_id: LineIdentifier | None = None
            if isinstance(item, dict):
                candidate = item.get("line_id")
                line_id = str(candidate) if candidate is not None else None
            elif isinstance(item, str | int):
                line_id = str(item)
            if line_id:
                collected.append(line_id)
        return collected

    def _collect_tie_groups(self, raw_groups: object) -> list[PresetTieGroup]:
        """Decode syntactically valid tie groups from JSON input."""
        if raw_groups is None:
            return []
        if not isinstance(raw_groups, list):
            logger.warning("Ignoring preset groups value that is not an array")
            return []

        groups: list[PresetTieGroup] = []
        for raw_group in raw_groups:
            if not isinstance(raw_group, dict):
                logger.warning("Ignoring malformed preset tie group: %s", raw_group)
                continue
            raw_uid = raw_group.get("uid")
            raw_line_ids = raw_group.get("line_ids")
            if not isinstance(raw_uid, str) or not isinstance(raw_line_ids, list):
                logger.warning("Ignoring malformed preset tie group: %s", raw_group)
                continue
            line_ids = tuple(
                str(line_id)
                for line_id in raw_line_ids
                if isinstance(line_id, str | int) and str(line_id)
            )
            try:
                groups.append(PresetTieGroup(uid=raw_uid, line_ids=line_ids))
            except ValueError:
                logger.warning("Ignoring invalid preset tie group: %s", raw_group)
        return groups

    def _warn_unknown_line_ids(self, preset_name: str, line_ids: Sequence[LineIdentifier]) -> None:
        """Report unknown line identifiers at the persistence boundary."""
        missing = [
            line_id for line_id in line_ids if self._atomic_data.get_line_by_id(line_id) is None
        ]
        if missing:
            logger.warning(
                "Preset '%s': skipping unknown line identifiers: %s",
                preset_name,
                ", ".join(dict.fromkeys(missing)),
            )

    def _decode_baseline(self, raw_baseline: object) -> LineIdentifier | None:
        """Decode baseline identifiers from supported JSON forms."""
        if isinstance(raw_baseline, str | int):
            return str(raw_baseline)
        if isinstance(raw_baseline, dict):
            candidate = raw_baseline.get("line_id")
            if candidate is not None:
                return str(candidate)
        return None

    def _resolve_database_metadata(self) -> dict[str, Any] | None:
        """Resolve spectral line CSV provenance for export payloads."""
        try:
            path = AtomicLineCsvRepository().resolve_csv_path()
        except (FileNotFoundError, OSError):  # pragma: no cover - filesystem dependent
            return None

        header = self._read_csv_header_fields(path)
        metadata: dict[str, Any] = {"format": "csv"}
        name = header.get("name")
        if name:
            metadata["name"] = name
        metadata["version"] = header.get("version", "")

        digest = self._compute_file_digest(path)
        if digest:
            metadata["digest"] = f"sha256:{digest}"
        metadata["path"] = str(path)
        return metadata

    def _read_csv_header_fields(self, path: Path) -> dict[str, str]:
        """Return ``# key: value`` fields from the leading comment block of a CSV."""
        fields: dict[str, str] = {}
        try:
            with path.open(encoding="utf-8") as stream:
                for raw in stream:
                    stripped = raw.strip()
                    if not stripped:
                        continue
                    if not stripped.startswith("#"):
                        break
                    key, separator, value = stripped.lstrip("#").strip().partition(":")
                    if separator:
                        fields[key.strip().lower()] = value.strip()
        except OSError:  # pragma: no cover - filesystem dependent
            return {}
        return fields

    def _compute_file_digest(self, path: Path) -> str | None:
        """Return a SHA-256 digest for a file when it is readable."""
        try:
            hasher = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(65536), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except OSError:  # pragma: no cover - filesystem dependent
            return None


__all__ = ["DEFAULT_PRESET_PATH", "PRESET_FILE_SCHEMA_VERSION", "PersistentPresetStore"]
