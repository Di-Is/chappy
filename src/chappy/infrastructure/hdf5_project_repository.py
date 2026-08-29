"""HDF5 v2 project repository implementation."""

from __future__ import annotations

import importlib.metadata as importlib_metadata
import json
import zlib
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import h5py  # type: ignore[import-untyped]
import numpy as np

from chappy.application.project_document import (
    AbsorptionLineDocument,
    AbsorptionRegionDocument,
    AnalysisArtifactDocument,
    ComponentDocument,
    ComponentKind,
    FitSummaryDocument,
    IdentifyStateDocument,
    JsonObject,
    JsonValue,
    MaskDocument,
    ParameterDocument,
    ProjectDocument,
    RegionAnalysisStateDocument,
    SpectrumDocument,
    TieSetDocument,
    TieSharedParameterDocument,
)
from chappy.application.project_schema import PROJECT_SCHEMA_VERSION

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

_STRING_DTYPE = h5py.string_dtype("utf-8")


class HDF5ProjectRepository:
    """Persist project documents using the HDF5 v2 schema."""

    def load(self, path: str) -> ProjectDocument:
        """Load a project document from HDF5.

        Args:
            path: Project file path.

        Returns:
            Loaded project document.
        """
        project_path = Path(path)
        if not project_path.exists():
            msg = f"Project file not found: {path}"
            raise FileNotFoundError(msg)

        with h5py.File(path, "r") as handle:
            schema_version = _read_string(handle, "metadata/schema_version")
            if schema_version != PROJECT_SCHEMA_VERSION:
                msg = f"Unsupported project schema version: {schema_version}"
                raise ValueError(msg)

            info = _read_json_object(handle, "project/info_json")
            spectrum = _read_spectrum(handle)
            return ProjectDocument(
                name=_required_str(info, "name"),
                spectrum_filename=_optional_str(info, "spectrum_filename"),
                created=_parse_datetime(_required_str(info, "created")),
                modified=_parse_datetime(_required_str(info, "modified")),
                metadata=_read_json_object(handle, "project/metadata_json"),
                settings=_read_json_object(handle, "project/settings_json"),
                spectrum=spectrum,
                components=tuple(
                    _component_from_json(entry)
                    for entry in _read_json_object_list(handle, "model/components_json")
                ),
                masks=tuple(
                    _mask_from_json(entry)
                    for entry in _read_json_object_list(handle, "model/masks_json")
                ),
                fit_wavelength_range=_optional_float_pair(info, "fit_wavelength_range"),
                tie_sets=tuple(
                    _tie_set_from_json(entry)
                    for entry in _read_json_object_list(handle, "model/tie_sets_json")
                ),
                absorption_regions=tuple(
                    _region_from_json(entry)
                    for entry in _read_json_object_list(handle, "analysis/regions_json")
                ),
                absorption_lines=tuple(
                    _line_from_json(entry)
                    for entry in _read_json_object_list(handle, "analysis/lines_json")
                ),
                analysis_states=tuple(
                    _analysis_state_from_json(entry)
                    for entry in _read_json_object_list(handle, "analysis/states_json")
                ),
                identify_state=_identify_state_from_json(
                    _read_json_object(handle, "session/identify_json")
                ),
            )

    def save(self, document: ProjectDocument, path: str) -> None:
        """Save a project document to HDF5.

        Args:
            document: Project document.
            path: Destination path.
        """
        state_payloads = _state_payloads(document)
        checksum = _checksum(state_payloads.values(), document.spectrum)

        with h5py.File(path, "w") as handle:
            metadata_group = handle.create_group("metadata")
            metadata_group.create_dataset(
                "schema_version", data=PROJECT_SCHEMA_VERSION, dtype=_STRING_DTYPE
            )
            metadata_group.create_dataset("version", data=_app_version(), dtype=_STRING_DTYPE)
            metadata_group.create_dataset(
                "created", data=_isoformat(document.created), dtype=_STRING_DTYPE
            )
            metadata_group.create_dataset(
                "modified", data=_isoformat(document.modified), dtype=_STRING_DTYPE
            )
            metadata_group.create_dataset("checksum", data=np.uint32(checksum))

            project_group = handle.create_group("project")
            project_group.create_dataset(
                "info_json", data=state_payloads["project/info_json"], dtype=_STRING_DTYPE
            )
            project_group.create_dataset(
                "metadata_json", data=state_payloads["project/metadata_json"], dtype=_STRING_DTYPE
            )
            project_group.create_dataset(
                "settings_json", data=state_payloads["project/settings_json"], dtype=_STRING_DTYPE
            )

            model_group = handle.create_group("model")
            model_group.create_dataset(
                "components_json",
                data=state_payloads["model/components_json"],
                dtype=_STRING_DTYPE,
            )
            model_group.create_dataset(
                "masks_json", data=state_payloads["model/masks_json"], dtype=_STRING_DTYPE
            )
            model_group.create_dataset(
                "tie_sets_json", data=state_payloads["model/tie_sets_json"], dtype=_STRING_DTYPE
            )

            analysis_group = handle.create_group("analysis")
            analysis_group.create_dataset(
                "regions_json", data=state_payloads["analysis/regions_json"], dtype=_STRING_DTYPE
            )
            analysis_group.create_dataset(
                "lines_json", data=state_payloads["analysis/lines_json"], dtype=_STRING_DTYPE
            )
            analysis_group.create_dataset(
                "states_json", data=state_payloads["analysis/states_json"], dtype=_STRING_DTYPE
            )
            session_group = handle.create_group("session")
            session_group.create_dataset(
                "identify_json", data=state_payloads["session/identify_json"], dtype=_STRING_DTYPE
            )

            data_group = handle.create_group("data")
            if document.spectrum is not None:
                spectrum_group = data_group.create_group("spectrum")
                spectrum_group.create_dataset(
                    "wavelength",
                    data=np.asarray(document.spectrum.wavelength, dtype=np.float64),
                    compression="gzip",
                )
                spectrum_group.create_dataset(
                    "flux",
                    data=np.asarray(document.spectrum.flux, dtype=np.float64),
                    compression="gzip",
                )
                if document.spectrum.error is not None:
                    spectrum_group.create_dataset(
                        "error",
                        data=np.asarray(document.spectrum.error, dtype=np.float64),
                        compression="gzip",
                    )
                spectrum_group.create_dataset(
                    "header_json",
                    data=state_payloads["data/spectrum/header_json"],
                    dtype=_STRING_DTYPE,
                )


def _state_payloads(document: ProjectDocument) -> dict[str, str]:
    info: JsonObject = {
        "name": document.name,
        "spectrum_filename": document.spectrum_filename,
        "created": _isoformat(document.created),
        "modified": _isoformat(document.modified),
        "fit_wavelength_range": _float_pair_to_json(document.fit_wavelength_range),
    }
    return {
        "project/info_json": _json_dumps(info),
        "project/metadata_json": _json_dumps(document.metadata),
        "project/settings_json": _json_dumps(document.settings),
        "model/components_json": _json_dumps(
            [_component_to_json(component) for component in document.components]
        ),
        "model/masks_json": _json_dumps([_mask_to_json(mask) for mask in document.masks]),
        "model/tie_sets_json": _json_dumps(
            [_tie_set_to_json(tie_set) for tie_set in document.tie_sets]
        ),
        "analysis/regions_json": _json_dumps(
            [_region_to_json(region) for region in document.absorption_regions]
        ),
        "analysis/lines_json": _json_dumps(
            [_line_to_json(line) for line in document.absorption_lines]
        ),
        "analysis/states_json": _json_dumps(
            [_analysis_state_to_json(state) for state in document.analysis_states]
        ),
        "session/identify_json": _json_dumps(_identify_state_to_json(document.identify_state)),
        "data/spectrum/header_json": _json_dumps(
            document.spectrum.header if document.spectrum is not None else {}
        ),
    }


def _component_to_json(document: ComponentDocument) -> JsonObject:
    return {
        "component_id": document.component_id,
        "kind": document.kind,
        "name": document.name,
        "enabled": document.enabled,
        "parameters": [_parameter_to_json(parameter) for parameter in document.parameters],
        "wavelength": document.wavelength,
        "oscillator_strength": document.oscillator_strength,
        "gamma": document.gamma,
        "group_id": document.group_id,
        "continuum_points": [[wavelength, flux] for wavelength, flux in document.continuum_points],
        "is_shared_with_absorption": document.is_shared_with_absorption,
    }


def _component_from_json(payload: JsonObject) -> ComponentDocument:
    parameters = tuple(
        _parameter_from_json(entry)
        for entry in _object_list(_required_list(payload, "parameters"), "parameters")
    )
    kind = _required_str(payload, "kind")
    if kind == "absorber":
        component_kind: ComponentKind = "absorber"
    elif kind == "continuum":
        component_kind = "continuum"
    else:
        msg = f"Unsupported component kind: {kind}"
        raise ValueError(msg)
    return ComponentDocument(
        component_id=_required_str(payload, "component_id"),
        kind=component_kind,
        name=_required_str(payload, "name"),
        enabled=_required_bool(payload, "enabled"),
        parameters=parameters,
        wavelength=_optional_float(payload, "wavelength"),
        oscillator_strength=_optional_float(payload, "oscillator_strength"),
        gamma=_optional_float(payload, "gamma"),
        group_id=_optional_str(payload, "group_id"),
        continuum_points=tuple(
            _float_pair_from_value(value) for value in _required_list(payload, "continuum_points")
        ),
        is_shared_with_absorption=_required_bool(payload, "is_shared_with_absorption"),
    )


def _parameter_to_json(document: ParameterDocument) -> JsonObject:
    return {
        "name": document.name,
        "value": document.value,
        "min_val": document.min_val,
        "max_val": document.max_val,
        "fixed": document.fixed,
        "error": document.error,
        "unit": document.unit,
    }


def _parameter_from_json(payload: JsonObject) -> ParameterDocument:
    return ParameterDocument(
        name=_required_str(payload, "name"),
        value=_required_float(payload, "value"),
        min_val=_required_float(payload, "min_val"),
        max_val=_required_float(payload, "max_val"),
        fixed=_required_bool(payload, "fixed"),
        error=_required_float(payload, "error"),
        unit=_optional_str(payload, "unit"),
    )


def _mask_to_json(document: MaskDocument) -> JsonObject:
    return {
        "identifier": document.identifier,
        "label": document.label,
        "mode": document.mode,
        "start_wavelength": document.start_wavelength,
        "end_wavelength": document.end_wavelength,
        "center": document.center,
        "half_width": document.half_width,
        "note": document.note,
        "color": document.color,
        "enabled": document.enabled,
        "group_id": document.group_id,
    }


def _mask_from_json(payload: JsonObject) -> MaskDocument:
    return MaskDocument(
        identifier=_required_str(payload, "identifier"),
        label=_required_str(payload, "label"),
        mode=_required_str(payload, "mode"),
        start_wavelength=_optional_float(payload, "start_wavelength"),
        end_wavelength=_optional_float(payload, "end_wavelength"),
        center=_optional_float(payload, "center"),
        half_width=_optional_float(payload, "half_width"),
        note=_required_str(payload, "note"),
        color=_optional_str(payload, "color"),
        enabled=_required_bool(payload, "enabled"),
        group_id=_optional_str(payload, "group_id"),
    )


def _tie_set_to_json(document: TieSetDocument) -> JsonObject:
    return {
        "uid": document.uid,
        "tie_id": document.tie_id,
        "name": document.name,
        "origin": document.origin,
        "mask": list(document.mask),
        "component_ids": list(document.component_ids),
        "member_uids": list(document.member_uids),
        "shared_parameters": [
            _shared_parameter_to_json(parameter) for parameter in document.shared_parameters
        ],
    }


def _tie_set_from_json(payload: JsonObject) -> TieSetDocument:
    return TieSetDocument(
        uid=_required_str(payload, "uid"),
        tie_id=_required_str(payload, "tie_id"),
        name=_required_str(payload, "name"),
        origin=_required_str(payload, "origin"),
        mask=tuple(_string_list(payload, "mask")),
        component_ids=tuple(_string_list(payload, "component_ids")),
        member_uids=tuple(_string_list(payload, "member_uids")),
        shared_parameters=tuple(
            _shared_parameter_from_json(entry)
            for entry in _object_list(
                _required_list(payload, "shared_parameters"), "shared_parameters"
            )
        ),
    )


def _shared_parameter_to_json(document: TieSharedParameterDocument) -> JsonObject:
    return {"name": document.name, "value": document.value, "fixed": document.fixed}


def _shared_parameter_from_json(payload: JsonObject) -> TieSharedParameterDocument:
    return TieSharedParameterDocument(
        name=_required_str(payload, "name"),
        value=_required_float(payload, "value"),
        fixed=_required_bool(payload, "fixed"),
    )


def _region_to_json(document: AbsorptionRegionDocument) -> JsonObject:
    return {
        "region_id": document.region_id,
        "line_ids": list(document.line_ids),
        "display_color": document.display_color,
        "analysis_range": _float_pair_to_json(document.analysis_range),
        "created_at": _isoformat(document.created_at),
    }


def _region_from_json(payload: JsonObject) -> AbsorptionRegionDocument:
    return AbsorptionRegionDocument(
        region_id=_required_str(payload, "region_id"),
        line_ids=tuple(_string_list(payload, "line_ids")),
        display_color=_required_str(payload, "display_color"),
        analysis_range=_optional_float_pair(payload, "analysis_range"),
        created_at=_parse_datetime(_required_str(payload, "created_at")),
    )


def _line_to_json(document: AbsorptionLineDocument) -> JsonObject:
    return {
        "line_id": document.line_id,
        "species": document.species,
        "rest_wavelength": document.rest_wavelength,
        "center_z": document.center_z,
        "window_kms": document.window_kms,
        "multiplet_label": document.multiplet_label,
        "transition_name": document.transition_name,
        "oscillator_strength": document.oscillator_strength,
        "gamma_value": document.gamma_value,
        "lambda_range": _float_pair_to_json(document.lambda_range),
        "region_id": document.region_id,
        "multiplet_ids": list(document.multiplet_ids),
        "model_ids": list(document.model_ids),
        "needs_optimization": document.needs_optimization,
        "created_by": document.created_by,
        "created_at": _isoformat(document.created_at),
    }


def _line_from_json(payload: JsonObject) -> AbsorptionLineDocument:
    return AbsorptionLineDocument(
        line_id=_required_str(payload, "line_id"),
        species=_required_str(payload, "species"),
        rest_wavelength=_required_float(payload, "rest_wavelength"),
        center_z=_required_float(payload, "center_z"),
        window_kms=_required_float(payload, "window_kms"),
        multiplet_label=_required_str(payload, "multiplet_label"),
        transition_name=_required_str(payload, "transition_name"),
        oscillator_strength=_required_float(payload, "oscillator_strength"),
        gamma_value=_required_float(payload, "gamma_value"),
        lambda_range=_optional_float_pair(payload, "lambda_range"),
        region_id=_optional_str(payload, "region_id"),
        multiplet_ids=tuple(_string_list(payload, "multiplet_ids")),
        model_ids=tuple(_string_list(payload, "model_ids")),
        needs_optimization=_required_bool(payload, "needs_optimization"),
        created_by=_required_str(payload, "created_by"),
        created_at=_parse_datetime(_required_str(payload, "created_at")),
    )


def _analysis_state_to_json(document: RegionAnalysisStateDocument) -> JsonObject:
    artifact = document.artifact
    artifact_payload: JsonObject | None = None
    if artifact is not None:
        summary = artifact.fit_summary
        artifact_payload = {
            "region_id": artifact.region_id,
            "source_revision": artifact.source_revision,
            "fit_summary": {
                "chi_squared": summary.chi_squared,
                "reduced_chi_squared": summary.reduced_chi_squared,
                "degrees_of_freedom": summary.degrees_of_freedom,
                "n_parameters": summary.n_parameters,
                "n_function_evaluations": summary.n_function_evaluations,
                "outcome": summary.outcome,
            },
        }
    return {
        "region_id": document.region_id,
        "current_revision": document.current_revision,
        "artifact": artifact_payload,
    }


def _analysis_state_from_json(payload: JsonObject) -> RegionAnalysisStateDocument:
    artifact_value = payload.get("artifact")
    artifact: AnalysisArtifactDocument | None = None
    if artifact_value is not None:
        if not isinstance(artifact_value, dict):
            msg = "Expected object or null for 'artifact'"
            raise TypeError(msg)
        summary_value = artifact_value.get("fit_summary")
        if not isinstance(summary_value, dict):
            msg = "Expected object for 'fit_summary'"
            raise TypeError(msg)
        fit_summary = FitSummaryDocument(
            chi_squared=_optional_float(summary_value, "chi_squared"),
            reduced_chi_squared=_optional_float(summary_value, "reduced_chi_squared"),
            degrees_of_freedom=_optional_float(summary_value, "degrees_of_freedom"),
            n_parameters=_optional_int(summary_value, "n_parameters"),
            n_function_evaluations=_optional_int(summary_value, "n_function_evaluations"),
            outcome=_optional_str(summary_value, "outcome"),
        )
        if all(
            value is None
            for value in (
                fit_summary.chi_squared,
                fit_summary.reduced_chi_squared,
                fit_summary.degrees_of_freedom,
                fit_summary.n_parameters,
                fit_summary.n_function_evaluations,
            )
        ):
            msg = "Expected at least one value in 'fit_summary'"
            raise ValueError(msg)
        artifact = AnalysisArtifactDocument(
            region_id=_required_str(artifact_value, "region_id"),
            source_revision=_required_int(artifact_value, "source_revision"),
            fit_summary=fit_summary,
        )
    return RegionAnalysisStateDocument(
        region_id=_required_str(payload, "region_id"),
        current_revision=_required_int(payload, "current_revision"),
        artifact=artifact,
    )


def _identify_state_to_json(document: IdentifyStateDocument) -> JsonObject:
    return {
        "work_phase": document.work_phase,
        "reference_z": document.reference_z,
        "last_added_wavelength": document.last_added_wavelength,
        "last_click_wavelength": document.last_click_wavelength,
    }


def _identify_state_from_json(payload: JsonObject) -> IdentifyStateDocument:
    return IdentifyStateDocument(
        work_phase=_required_str(payload, "work_phase"),
        reference_z=_required_float(payload, "reference_z"),
        last_added_wavelength=_optional_float(payload, "last_added_wavelength"),
        last_click_wavelength=_optional_float(payload, "last_click_wavelength"),
    )


def _read_spectrum(handle: h5py.File) -> SpectrumDocument | None:
    if "data/spectrum" not in handle:
        return None
    group = handle["data/spectrum"]
    return SpectrumDocument(
        wavelength=np.asarray(group["wavelength"][()], dtype=np.float64),
        flux=np.asarray(group["flux"][()], dtype=np.float64),
        error=np.asarray(group["error"][()], dtype=np.float64) if "error" in group else None,
        header=_read_json_object(handle, "data/spectrum/header_json"),
    )


def _read_json_object(handle: h5py.File, path: str) -> JsonObject:
    value = _json_value_from_object(json.loads(_read_string(handle, path)), path)
    if not isinstance(value, dict):
        msg = f"Expected JSON object at {path}"
        raise TypeError(msg)
    return value


def _read_json_object_list(handle: h5py.File, path: str) -> list[JsonObject]:
    value = _json_value_from_object(json.loads(_read_string(handle, path)), path)
    if not isinstance(value, list):
        msg = f"Expected JSON list at {path}"
        raise TypeError(msg)
    return _object_list(value, path)


def _read_string(handle: h5py.File, path: str) -> str:
    if path not in handle:
        msg = f"Missing required dataset: {path}"
        raise ValueError(msg)
    raw = handle[path][()]
    if isinstance(raw, bytes):
        return raw.decode("utf-8")
    if isinstance(raw, str):
        return raw
    return str(raw)


def _json_dumps(value: JsonValue) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_value_from_object(value: object, path: str) -> JsonValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list):
        return [_json_value_from_object(item, path) for item in value]
    if isinstance(value, dict):
        result: JsonObject = {}
        for key, item in value.items():
            if not isinstance(key, str):
                msg = f"Expected string JSON key at {path}"
                raise TypeError(msg)
            result[key] = _json_value_from_object(item, path)
        return result
    msg = f"Unsupported JSON value at {path}: {type(value).__name__}"
    raise ValueError(msg)


def _checksum(payloads: Iterable[str], spectrum: SpectrumDocument | None) -> int:
    checksum = 0
    for payload in payloads:
        checksum = zlib.crc32(payload.encode("utf-8"), checksum)
    if spectrum is not None:
        arrays = [spectrum.wavelength, spectrum.flux]
        if spectrum.error is not None:
            arrays.append(spectrum.error)
        for array in arrays:
            checksum = zlib.crc32(np.asarray(array, dtype=np.float64).tobytes(), checksum)
    return checksum


def _app_version() -> str:
    try:
        return importlib_metadata.version("chappy")
    except importlib_metadata.PackageNotFoundError:
        return "0.0.0"


def _isoformat(dt: datetime) -> str:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC).isoformat()
    return dt.astimezone(UTC).isoformat()


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _float_pair_to_json(value: tuple[float, float] | None) -> list[JsonValue] | None:
    if value is None:
        return None
    return [float(value[0]), float(value[1])]


def _optional_float_pair(payload: Mapping[str, JsonValue], key: str) -> tuple[float, float] | None:
    value = payload.get(key)
    if value is None:
        return None
    return _float_pair_from_value(value)


def _float_pair_from_value(value: JsonValue) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        msg = f"Expected two-item float pair, got {value!r}"
        raise ValueError(msg)
    return (_float_from_value(value[0]), _float_from_value(value[1]))


def _required_list(payload: Mapping[str, JsonValue], key: str) -> list[JsonValue]:
    value = payload.get(key)
    if not isinstance(value, list):
        msg = f"Expected list for '{key}'"
        raise TypeError(msg)
    return value


def _object_list(values: list[JsonValue], key: str) -> list[JsonObject]:
    result: list[JsonObject] = []
    for value in values:
        if not isinstance(value, dict):
            msg = f"Expected object entries for '{key}'"
            raise TypeError(msg)
        result.append(value)
    return result


def _string_list(payload: Mapping[str, JsonValue], key: str) -> list[str]:
    values = _required_list(payload, key)
    result: list[str] = []
    for value in values:
        if not isinstance(value, str):
            msg = f"Expected string list for '{key}'"
            raise TypeError(msg)
        result.append(value)
    return result


def _required_str(payload: Mapping[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        msg = f"Expected string for '{key}'"
        raise TypeError(msg)
    return value


def _optional_str(payload: Mapping[str, JsonValue], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        msg = f"Expected optional string for '{key}'"
        raise TypeError(msg)
    return value


def _required_bool(payload: Mapping[str, JsonValue], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        msg = f"Expected bool for '{key}'"
        raise TypeError(msg)
    return value


def _optional_int(payload: Mapping[str, JsonValue], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"Expected optional int for '{key}'"
        raise TypeError(msg)
    return value


def _required_int(payload: Mapping[str, JsonValue], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"Expected int for '{key}'"
        raise TypeError(msg)
    return value


def _required_float(payload: Mapping[str, JsonValue], key: str) -> float:
    return _float_from_value(payload.get(key))


def _optional_float(payload: Mapping[str, JsonValue], key: str) -> float | None:
    value = payload.get(key)
    if value is None:
        return None
    return _float_from_value(value)


def _float_from_value(value: JsonValue) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        msg = f"Expected float-compatible value, got {value!r}"
        raise TypeError(msg)
    return float(value)
