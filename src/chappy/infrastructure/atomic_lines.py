"""Infrastructure repository for loading atomic line CSV catalogs."""

from __future__ import annotations

import csv
import logging
import os
from pathlib import Path

from chappy.core.atomic_data import (
    AtomicLine,
    AtomicLineData,
    charge_to_stage,
    normalize_element_symbol,
    stage_to_charge,
)
from chappy.infrastructure.resources import resolve_data_path

logger = logging.getLogger(__name__)

CSV_PATH_ENV_VAR = "CHAPPY_SPECTRAL_LINES_CSV"
CONFIG_DIR_ENV_VAR = "CHAPPY_CONFIG_DIR"
USER_CSV_FILENAME = "spectral_lines.csv"
_BUNDLED_CSV_PARTS = ("spectral_database", "db_file", "spectral_lines.csv")


class SpectralLineCsvError(ValueError):
    """Raised when a spectral line CSV cannot be used as an atomic line catalog."""


def user_csv_directory() -> Path:
    """Return the directory where users may drop a replacement catalog CSV."""
    override = os.environ.get(CONFIG_DIR_ENV_VAR)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".chappy"


def user_csv_path() -> Path:
    """Return the fixed path users may place a replacement catalog CSV at."""
    return user_csv_directory() / USER_CSV_FILENAME


class AtomicLineCsvRepository:
    """Load atomic line data from an explicit, user-supplied, or bundled CSV."""

    def load(self, csv_path: str | Path | None = None) -> AtomicLineData:
        """Load atomic line data from CSV into an in-memory query repository."""
        path = self.resolve_csv_path(csv_path)
        logger.info("Loading atomic data from: %s", path)
        lines = self._load_lines(path)
        if not lines:
            msg = f"No usable atomic lines found in spectral line CSV: {path}"
            raise SpectralLineCsvError(msg)
        return AtomicLineData(lines)

    def resolve_csv_path(self, csv_path: str | Path | None = None) -> Path:
        """Resolve the CSV path using explicit, env override, user file, then bundled."""
        if csv_path is not None:
            return self._require_existing(Path(csv_path).expanduser())

        env_override = os.environ.get(CSV_PATH_ENV_VAR)
        if env_override:
            return self._require_existing(Path(env_override).expanduser())

        user_path = user_csv_path()
        if user_path.exists():
            return user_path

        bundled_path = resolve_data_path(*_BUNDLED_CSV_PARTS)
        if bundled_path is not None:
            return bundled_path

        msg = "Could not find spectral_lines.csv in bundled resources"
        raise FileNotFoundError(msg)

    def _require_existing(self, path: Path) -> Path:
        """Return the path when it exists, otherwise raise."""
        if path.exists():
            return path
        msg = f"CSV file not found: {path}"
        raise FileNotFoundError(msg)

    def _load_lines(self, path: Path) -> list[AtomicLine]:
        """Read and parse valid atomic lines from CSV."""
        try:
            with path.open(encoding="utf-8") as file:
                data_rows = [
                    raw for raw in file if raw.strip() and not raw.lstrip().startswith("#")
                ]
        except OSError as exc:
            msg = f"Error reading CSV file: {exc}"
            raise SpectralLineCsvError(msg) from exc

        if not data_rows:
            return []

        reader = csv.DictReader(data_rows)
        lines: list[AtomicLine] = []
        for row_num, row in enumerate(reader, 1):
            try:
                line = self._parse_csv_row(row)
            except (ValueError, KeyError) as exc:
                logger.debug("Skipping invalid row %s: %s", row_num, exc)
                continue
            if line is not None and line.is_valid:
                lines.append(line)

        logger.info("Loaded %d valid atomic lines", len(lines))
        return lines

    def _parse_csv_row(self, row: dict[str, str]) -> AtomicLine | None:
        """Parse a CSV row into an AtomicLine object."""
        try:

            def _field(key: str) -> str:
                return row.get(key, "").strip()

            def _float_field(key: str) -> float | None:
                value = _field(key)
                if not value:
                    return None
                try:
                    return float(value)
                except ValueError:
                    return None

            def _int_field(key: str) -> int | None:
                value = _field(key)
                if not value:
                    return None
                try:
                    return int(value)
                except ValueError:
                    return None

            line_identifier = _field("line_id")
            if not line_identifier:
                logger.debug("Missing line_id in atomic line data for row: %s", row)
                return None
            species = _field("species")
            name = _field("name")
            element_symbol_raw = _field("element_symbol")
            charge_raw = _field("charge_state")
            multiplet_label = _field("mutiplet_name") or _field("multiplet_name")
            multiplet_id = _field("multiplet_id") or multiplet_label
            comments = _field("comment") or _field("comments")
            wavelength_str = _field("wavelength") or _field("wavelength_angstrom")
            osc_str = _field("f_value") or _field("oscillator_strength")
            gamma_str = _field("gamma") or _field("gamma_value")
            wavelength_source = _field("wavelength_source")
            wavelength_ritz = _float_field("wavelength_ritz")
            wavelength_ritz_unc = _float_field("wavelength_ritz_unc")
            wavelength_observed = _float_field("wavelength_observed")
            wavelength_observed_unc = _float_field("wavelength_observed_unc")
            energy_lower = _float_field("Ei_eV")
            energy_upper = _float_field("Ek_eV")
            lower_conf = _field("lower_conf")
            lower_term = _field("lower_term")
            lower_j = _field("lower_J")
            upper_conf = _field("upper_conf")
            upper_term = _field("upper_term")
            upper_j = _field("upper_J")
            upper_term_ls = _field("upper_term_LS")
            accuracy_code = _field("accuracy")
            component_index = _int_field("component_index")
            tp_ref = _field("tp_ref")
            line_ref = _field("line_ref")

            if not wavelength_str:
                return None

            wavelength = float(wavelength_str)
            oscillator_strength = float(osc_str) if osc_str else 0.0
            gamma_value = float(gamma_str) if gamma_str else 0.0
            charge_state: int | None = None
            if charge_raw:
                try:
                    charge_state = int(charge_raw)
                except ValueError:
                    charge_state = stage_to_charge(charge_raw)

            element_symbol = normalize_element_symbol(element_symbol_raw)

            if not species:
                stage = charge_to_stage(charge_state)
                if element_symbol and stage:
                    species = f"{element_symbol} {stage}"
                elif element_symbol:
                    species = element_symbol
                elif name:
                    parts = name.split()
                    species = " ".join(parts[:2]) if len(parts) >= 2 else name
                    if parts:
                        element_symbol = normalize_element_symbol(parts[0])

            species = species.strip()
            if not species:
                return None

            if not element_symbol and species:
                element_symbol = normalize_element_symbol(species.split()[0])

            transition_name = name or species

            return AtomicLine(
                line_identifier=line_identifier,
                species=species,
                wavelength_angstrom=wavelength,
                oscillator_strength=oscillator_strength,
                gamma_value=gamma_value,
                multiplet_id=multiplet_id,
                comments=comments,
                element_symbol=element_symbol,
                charge_state=charge_state,
                transition_name=transition_name,
                wavelength_source=wavelength_source,
                wavelength_ritz=wavelength_ritz,
                wavelength_ritz_uncertainty=wavelength_ritz_unc,
                wavelength_observed=wavelength_observed,
                wavelength_observed_uncertainty=wavelength_observed_unc,
                energy_lower_ev=energy_lower,
                energy_upper_ev=energy_upper,
                lower_configuration=lower_conf,
                lower_term=lower_term,
                lower_j=lower_j,
                upper_configuration=upper_conf,
                upper_term=upper_term,
                upper_j=upper_j,
                upper_term_ls=upper_term_ls,
                accuracy_code=accuracy_code,
                multiplet_label=multiplet_label,
                component_index=component_index,
                transition_probability_ref=tp_ref,
                wavelength_ref=line_ref,
            )
        except (ValueError, TypeError) as exc:
            logger.debug("Failed to parse row %s: %s", row, exc)
            return None


class _AtomicDataHolder:
    """Holder for infrastructure-owned atomic line data singleton."""

    def __init__(self) -> None:
        self._data: AtomicLineData | None = None

    def get(self) -> AtomicLineData:
        """Return the infrastructure-owned atomic line data singleton."""
        if self._data is None:
            self._data = AtomicLineCsvRepository().load()
        return self._data


_holder = _AtomicDataHolder()


def load_atomic_data(csv_path: str | Path | None = None) -> AtomicLineData:
    """Load atomic line data from an explicit or resolved CSV path."""
    return AtomicLineCsvRepository().load(csv_path)


def get_atomic_data() -> AtomicLineData:
    """Return the infrastructure-owned process-wide atomic line data."""
    return _holder.get()


__all__ = [
    "CSV_PATH_ENV_VAR",
    "AtomicLineCsvRepository",
    "SpectralLineCsvError",
    "get_atomic_data",
    "load_atomic_data",
    "user_csv_directory",
    "user_csv_path",
]
