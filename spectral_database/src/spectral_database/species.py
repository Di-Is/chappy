"""Species management and preset handling.

This module provides utilities for managing spectral species specifications,
including preset lists and normalization of species strings.
"""

from __future__ import annotations

import csv
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

try:  # pragma: no cover - Python < 3.11 fallback
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

if TYPE_CHECKING:
    from collections.abc import Sequence

from spectral_database.data_models import (
    LineFilterThresholds,
    SpeciesFilterProfile,
    SpeciesFilterSet,
    SpeciesPreset,
)

_PRESET_DIR = Path(__file__).parent / "resources"
_PRESET_DIR_TOML = _PRESET_DIR / "presets"


logger = logging.getLogger(__name__)


def roman_to_int(roman: str) -> int:
    """Convert Roman numeral to integer.

    Args:
        roman: Roman numeral string (e.g., "II", "IV")

    Returns:
        Integer value
    """
    mapping = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    roman = roman.upper()
    total = 0
    prev = 0
    for ch in reversed(roman):
        val = mapping.get(ch, 0)
        if val < prev:
            total -= val
        else:
            total += val
            prev = val
    return total


def int_to_roman(num: int) -> str:
    """Convert integer to Roman numeral.

    Args:
        num: Integer value

    Returns:
        Roman numeral string
    """
    vals = [
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    ]
    out = []
    for v, sym in vals:
        while num >= v:
            out.append(sym)
            num -= v
    return "".join(out)


def normalize_species_for_query(raw: str) -> str | None:
    """Normalize species string for NIST query.

    Converts variations like "FeII", "Fe2", "Fe_II" to standard "Fe II" format.

    Args:
        raw: Raw species string

    Returns:
        Normalized species string (e.g., "Fe II"), or None if invalid
    """
    s = raw.strip()
    if not s:
        return None
    s = s.replace("*", "")
    s = s.replace("_", " ")
    s = s.replace("-", " ")
    s = re.sub(r"\d+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return None
    token = s.replace(" ", "")
    if not token:
        return None
    element = token[0].upper()
    idx = 1
    if idx < len(token) and token[idx].islower():
        element += token[idx].lower()
        idx += 1
    remainder = token[idx:]
    element = element[0].upper() + (element[1:].lower() if len(element) > 1 else "")
    if remainder:
        roman = remainder.upper()
        if not re.fullmatch(r"[IVXLCDM]+", roman):
            logger.debug("Skipping invalid ion stage '%s' from species '%s'", remainder, raw)
            return None
        return f"{element} {roman}"
    return f"{element} I"


def load_species_presets() -> dict[str, SpeciesPreset]:
    """Load species presets from TOML files.

    Returns:
        Dictionary mapping normalized preset names to :class:`SpeciesPreset` objects.
    """
    if not _PRESET_DIR_TOML.exists():
        logger.warning("Preset directory %s not found; no presets available", _PRESET_DIR_TOML)
        return {}

    presets: dict[str, SpeciesPreset] = {}
    for path in sorted(_PRESET_DIR_TOML.glob("*.toml")):
        try:
            with path.open("rb") as handle:
                raw = tomllib.load(handle)
        except (
            OSError,
            tomllib.TOMLDecodeError,
        ) as exc:  # pragma: no cover - load errors are logged
            logger.warning("Failed to load preset %s: %s", path.name, exc)
            continue

        name = str(raw.get("name") or path.stem)
        normalized_key = name.lower()
        species_values = _parse_species_list(raw.get("species"), path.name)
        filter_set = _parse_filter_section(raw.get("filters"), path.name)

        presets[normalized_key] = SpeciesPreset(
            name=name, species=species_values, filters=filter_set
        )

    return presets


def _parse_species_list(data: object, source: str) -> list[str]:
    if not isinstance(data, list):
        logger.debug("Preset %s has no species list", source)
        return []
    species: list[str] = []
    for raw in data:
        normalized = normalize_species_for_query(str(raw)) if raw is not None else None
        if normalized is None:
            logger.debug("Ignoring invalid species '%s' in %s", raw, source)
            continue
        species.append(normalized)
    return _dedupe_preserve_order(species)


def _parse_filter_section(data: object, source: str) -> SpeciesFilterSet:
    if not isinstance(data, dict):
        return SpeciesFilterSet()

    filter_set = SpeciesFilterSet()

    default_section = data.get("default")
    if isinstance(default_section, dict):
        filter_set.defaults.append(_build_threshold(default_section, source))

    defaults_section = data.get("defaults")
    if isinstance(defaults_section, list):
        for item in defaults_section:
            if isinstance(item, dict):
                filter_set.defaults.append(_build_threshold(item, source))

    profiles = data.get("profiles")
    if isinstance(profiles, list):
        for raw_profile in profiles:
            if not isinstance(raw_profile, dict):
                continue
            profile = _build_profile(raw_profile, source)
            if profile is not None:
                filter_set.profiles.append(profile)

    return filter_set


def _build_threshold(data: dict[str, object], source: str) -> LineFilterThresholds:
    min_f = _optional_float(data.get("min_f"))
    max_ei_ev = _optional_float(data.get("max_ei_ev"))
    if min_f is None and max_ei_ev is None:
        logger.debug("Threshold in %s skipped: no values", source)
    return LineFilterThresholds(min_f=min_f, max_ei_ev=max_ei_ev)


def _build_profile(data: dict[str, object], source: str) -> SpeciesFilterProfile | None:
    species_entries = data.get("species")
    element_entries = data.get("elements")

    normalized_species: set[str] = set()
    if isinstance(species_entries, list):
        for raw in species_entries:
            normalized = normalize_species_for_query(str(raw)) if raw is not None else None
            if normalized is None:
                logger.debug("Ignoring invalid profile species '%s' in %s", raw, source)
                continue
            normalized_species.add(normalized.lower())

    normalized_elements: set[str] = set()
    if isinstance(element_entries, list):
        for raw in element_entries:
            if raw is None:
                continue
            text = str(raw).strip()
            if not text:
                continue
            normalized_elements.add(text.lower())

    if not normalized_species and not normalized_elements:
        logger.debug("Ignoring profile without targets in %s", source)
        return None

    return SpeciesFilterProfile(
        name=str(data.get("name") or "") or None,
        species=normalized_species,
        elements=normalized_elements,
        min_f=_optional_float(data.get("min_f")),
        max_ei_ev=_optional_float(data.get("max_ei_ev")),
    )


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_filter_set_for_presets(
    preset_names: Sequence[str] | None, presets: dict[str, SpeciesPreset]
) -> SpeciesFilterSet:
    """Combine filter definitions for the selected presets.

    Args:
        preset_names: Iterable of preset names requested by the user.
        presets: Mapping returned by :func:`load_species_presets`.

    Returns:
        Aggregated :class:`SpeciesFilterSet` with defaults and profiles merged
        in the order the presets were provided.
    """
    combined = SpeciesFilterSet()
    if not preset_names:
        return combined

    for name in preset_names:
        key = name.lower()
        preset = presets.get(key)
        if preset is None:
            logger.warning("Unknown species preset for filters: %s", name)
            continue
        combined = combined.merged_with(preset.filters)

    return combined


def load_species_from_file(path: Path | str, column: str = "species") -> list[str]:
    """Load species list from CSV/text file.

    Args:
        path: Path to file
        column: Column name to read (default: "species")

    Returns:
        List of normalized species strings
    """
    input_path = Path(path)
    try:
        with input_path.open(encoding="utf-8") as handle:
            sample = handle.read(4096)
            handle.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
            except csv.Error:
                dialect = csv.excel
            reader = csv.reader(handle, dialect)
            species: list[str] = []
            header_checked = False
            col_idx: int | None = None
            for row in reader:
                if not row:
                    continue
                if not header_checked:
                    header_checked = True
                    for idx, value in enumerate(row):
                        if value.strip().lower() == column.lower():
                            col_idx = idx
                            break
                    if col_idx is not None:
                        # Skip header row
                        continue
                    col_idx = 0
                if col_idx is None or col_idx >= len(row):
                    continue
                raw_value = row[col_idx].strip()
                if not raw_value or raw_value.startswith("#"):
                    continue
                normalized = normalize_species_for_query(raw_value)
                if normalized is None:
                    logger.debug("Ignoring species entry '%s' from %s", raw_value, input_path)
                    continue
                species.append(normalized)
            return species
    except FileNotFoundError:
        logger.exception("Species file not found: %s", path)
    except OSError:
        logger.exception("Failed to read species file %s", path)
    return []


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    """Remove duplicates while preserving order.

    Args:
        items: List of strings

    Returns:
        List with duplicates removed (first occurrence kept)
    """
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def build_species_list(
    elements: Sequence[str],
    charges: Sequence[int],
    species: Sequence[str],
    presets: Sequence[str] | None = None,
    file_species: Sequence[str] | None = None,
    species_presets_dict: dict[str, SpeciesPreset] | None = None,
) -> list[str]:
    """Build final species list from various input sources.

    Args:
        elements: Element symbols (e.g., ["Fe", "Mg"])
        charges: Charge states (0=I, 1=II, ...)
        species: Direct species strings (e.g., ["Fe II", "Mg I"])
        presets: Preset names (e.g., ["qso_absorbers"])
        file_species: Species loaded from file
        species_presets_dict: Preset dictionary (loaded if None)

    Returns:
        Deduplicated list of species strings
    """
    if species_presets_dict is None:
        species_presets_dict = load_species_presets()

    preset_species: list[str] = []
    if presets:
        for name in presets:
            preset = species_presets_dict.get(name.lower())
            if preset is None:
                logger.warning("Unknown species preset: %s", name)
                continue
            preset_species.extend(preset.species)
    combined: list[str] = []
    if species:
        combined.extend(species)
    if preset_species:
        combined.extend(preset_species)
    if file_species:
        combined.extend(file_species)
    if combined:
        return _dedupe_preserve_order(combined)
    if not elements:
        # No explicit species; default to a modest, safe baseline to avoid huge queries
        return ["H I", "He I"]
    result: list[str] = []
    if not charges:
        # All ion stages for each element (NIST interprets element alone as all stages)
        return list(elements)
    for e in elements:
        for z in charges:
            roman = int_to_roman(z + 1)
            result.append(f"{e} {roman}")
    return result
