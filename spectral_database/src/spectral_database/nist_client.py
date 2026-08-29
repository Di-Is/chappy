"""NIST Atomic Spectra Database query client with retry logic.

This module handles fetching spectral line data from NIST using astroquery
with enhanced error handling and HTTP retry mechanisms.
"""

from __future__ import annotations

import contextlib
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import StringIO
from typing import TYPE_CHECKING

import requests
from astropy import units as u
from astropy.io import ascii as astropy_ascii
from astropy.table import Table
from astroquery.nist import Nist

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

# HTTP resilience tuning for direct NIST queries
NIST_HTTP_MAX_RETRIES = 50
NIST_HTTP_BASE_DELAY_S = 0.1
NIST_HTTP_MAX_DELAY_S = 1.0


# Thread-local storage for HTTP sessions reused across parallel workers.
_THREAD_LOCAL = threading.local()


logger = logging.getLogger(__name__)


def safe_meta_set(table: Table, key: str, value: object) -> None:
    """Safely set table metadata, ignoring errors.

    Args:
        table: Astropy Table
        key: Metadata key
        value: Metadata value
    """
    with contextlib.suppress(Exception):
        table.meta[key] = value


def safe_meta_get(table: Table, key: str, default: object = None) -> object:
    """Safely get table metadata with fallback.

    Args:
        table: Astropy Table
        key: Metadata key
        default: Default value if key not found

    Returns:
        Metadata value or default
    """
    with contextlib.suppress(Exception):
        if hasattr(table, "meta"):
            return table.meta.get(key, default)
    return default


def extract_pre_text(html: str) -> str:
    """Extract content from HTML <pre> block.

    Args:
        html: HTML response from NIST

    Returns:
        Content inside <pre> tags

    Raises:
        ValueError: If no <pre> block found
    """
    m = re.search(r"<pre[^>]*>(.*?)</pre>", html, flags=re.DOTALL | re.IGNORECASE)
    if not m:
        msg = "Failed to locate <pre> block in NIST response."
        raise ValueError(msg)
    # Unescape a few common entities used by NIST pages
    text = m.group(1)
    return text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def _strip_nist_table_lines(table_text: str) -> str:
    """Remove purely decorative lines from NIST ASCII tables.

    Args:
        table_text: Raw ASCII table text

    Returns:
        Table text with decorative lines removed
    """
    pattern = re.compile(r"[0-9A-Za-z]")
    lines = [line for line in table_text.splitlines() if pattern.search(line)]
    return "\n".join(lines)


def nist_query_astro_compat(
    spec: str, wmin_ang: float, wmax_ang: float, output_order: str = "wavelength"
) -> Table:
    """Call Nist.query with best-effort compatibility across astroquery versions.

    Note: astroquery's Nist.query doesn't expose uncertainty parameters,
    so we use requests directly to get the full payload including uncertainties.

    Args:
        spec: Species string (e.g., "C IV", "Fe II")
        wmin_ang: Minimum wavelength in Ångströms
        wmax_ang: Maximum wavelength in Ångströms
        output_order: NIST output ordering ("wavelength" or "multiplet")

    Returns:
        Astropy Table with NIST data, or empty Table if query fails
    """
    # Get base payload from astroquery
    u.Quantity([wmin_ang, wmax_ang], unit=u.AA)
    wmin_q = wmin_ang * u.AA
    wmax_q = wmax_ang * u.AA

    base_payload = Nist.query(
        wmin_q,
        wmax_q,
        linename=spec,
        wavelength_type="vacuum",
        output_order=output_order,
        get_query_payload=True,
    )

    # Convert numpy scalars to native types so requests can serialize them reliably.
    payload: dict[str, object] = {}
    for key, value in base_payload.items():
        if hasattr(value, "item") and not isinstance(value, str | bytes):
            with contextlib.suppress(TypeError, ValueError, AttributeError):
                payload[key] = value.item()
                continue
        payload[key] = value

    url = "https://physics.nist.gov/cgi-bin/ASD/lines1.pl"
    base_session = Nist._session

    def _get_session() -> requests.Session:
        session = getattr(_THREAD_LOCAL, "session", None)
        base_session_id = getattr(_THREAD_LOCAL, "base_session_id", None)
        if session is None or base_session_id != id(base_session):
            session = requests.Session()
            session.headers.update(base_session.headers)
            session.cookies.update(base_session.cookies)
            session.auth = base_session.auth
            session.proxies.update(base_session.proxies)
            session.verify = base_session.verify
            session.cert = base_session.cert
            session.trust_env = base_session.trust_env
            _THREAD_LOCAL.session = session
            _THREAD_LOCAL.base_session_id = id(base_session)
        return session

    unc_out_options: tuple[str | None, ...] = ("1", "on", None)
    last_error: Exception | None = None

    def _parse_table(pre_text: str) -> Table:
        stripped = _strip_nist_table_lines(pre_text)
        for data_start in (3, 2, 1, 0):
            with contextlib.suppress(Exception):
                return Table.read(
                    stripped, format="ascii.fixed_width", data_start=data_start, delimiter="|"
                )

        primary_error = ValueError("ascii.fixed_width parse failed")
        logger.debug("Failed to parse NIST table with fixed_width: %s", primary_error)
        try:
            return astropy_ascii.read(
                StringIO(stripped), format="basic", delimiter="|", guess=False, fast_reader=False
            )
        except (OSError, ValueError) as fallback_error:
            logger.warning(
                "Failed to parse NIST table for %s: %s (fallback: %s). First 500 chars: %s",
                spec,
                primary_error,
                fallback_error,
                pre_text[:500],
            )
            raise

    for unc_value in unc_out_options:
        request_payload = dict(payload)
        if unc_value is not None:
            request_payload["unc_out"] = unc_value
        else:
            request_payload.pop("unc_out", None)

        label = f"unc_out={unc_value}" if unc_value is not None else "no_unc_out"

        for attempt in range(NIST_HTTP_MAX_RETRIES):
            try:
                session = _get_session()
                response = session.get(url, params=request_payload, timeout=Nist.TIMEOUT)
                if response.status_code == 503:
                    msg = "503 Service Unavailable"
                    raise requests.exceptions.HTTPError(msg, response=response)
                response.raise_for_status()

                html = response.text
                if "Input Error" in html[:2000]:
                    logger.warning(
                        "NIST rejected query for %s when %s; response starts with: %s",
                        spec,
                        label,
                        html[:200].replace("\n", " "),
                    )
                    # Try next unc_out option without retrying the same invalid payload.
                    break

                try:
                    pre_text = extract_pre_text(html)
                except ValueError as exc:
                    last_error = exc
                    logger.warning(
                        "No <pre> block in NIST response for %s when %s; first 200 chars: %s",
                        spec,
                        label,
                        html[:200].replace("\n", " "),
                    )
                    break

                try:
                    return _parse_table(pre_text)
                except (OSError, ValueError) as exc:
                    last_error = exc
                    break

            except requests.exceptions.RequestException as exc:
                last_error = exc
                delay = min(NIST_HTTP_MAX_DELAY_S, NIST_HTTP_BASE_DELAY_S * (2**attempt))
                logger.warning(
                    "NIST request attempt %d/%d for %s (%s) failed: %s. Retrying in %.1fs",
                    attempt + 1,
                    NIST_HTTP_MAX_RETRIES,
                    spec,
                    label,
                    exc,
                    delay,
                )
                time.sleep(delay)
                continue

            # If we reach here the attempt did not raise but also did not return; break to next option.
            break
        else:
            # Exhausted retries for this unc_out value; try next option.
            continue

        # Move to next unc_out option after break.
        continue

    if last_error is not None:
        logger.warning(
            "NIST query ultimately failed for %s after retries; returning empty table (%s)",
            spec,
            last_error,
        )
    else:
        logger.warning("NIST query for %s returned no data even after fallback payloads", spec)
    return Table()


def iter_wavelength_chunks(wmin: float, wmax: float, step: float) -> Iterable[tuple[float, float]]:
    """Generate wavelength range chunks for batched queries.

    Args:
        wmin: Minimum wavelength
        wmax: Maximum wavelength
        step: Chunk size (if <=0, yields single range)

    Yields:
        Tuples of (start, end) wavelength ranges
    """
    if step <= 0:
        yield (wmin, wmax)
        return
    start = wmin
    while start < wmax:
        end = min(start + step, wmax)
        yield (start, end)
        start = end


def fetch_tables_resilient(
    species_list: Sequence[str],
    wav_min_ang: float,
    wav_max_ang: float,
    chunk_ang: float = 0.0,
    sleep_s: float = 0.0,
    output_order: str = "wavelength",
    max_workers: int | None = None,
) -> list[Table]:
    """Fetch NIST tables with optional chunking and sleep between requests.

    Args:
        species_list: List of species strings (e.g., ["C IV", "Fe II"])
        wav_min_ang: Minimum wavelength in Ångströms
        wav_max_ang: Maximum wavelength in Ångströms
        chunk_ang: Chunk size for wavelength batching (0 disables)
        sleep_s: Sleep duration between chunks (seconds)
        output_order: NIST output ordering ("wavelength" or "multiplet")
        max_workers: Parallel worker count (<=1 for serial execution)

    Returns:
        List of Astropy Tables with metadata
    """
    tables: list[Table] = []
    tasks: list[tuple[int, str, float, float]] = []

    for spec in species_list:
        for lo, hi in iter_wavelength_chunks(wav_min_ang, wav_max_ang, chunk_ang or 0):
            tasks.append((len(tasks), spec, lo, hi))

    if not tasks:
        logger.warning("No tables returned from astroquery for the given parameters")
        return tables

    def _fetch_single(spec: str, lo: float, hi: float) -> Table | None:
        logger.debug(
            "Fetching %s %.1f–%.1f Å via astroquery (%s order)", spec, lo, hi, output_order
        )
        table = nist_query_astro_compat(spec, lo, hi, output_order=output_order)
        if len(table) == 0:
            return None
        safe_meta_set(table, "species", spec)
        safe_meta_set(table, "wmin", lo)
        safe_meta_set(table, "wmax", hi)
        if sleep_s > 0:
            time.sleep(sleep_s)
        return table

    effective_workers = max_workers if max_workers and max_workers > 1 else 1

    if effective_workers == 1:
        for _, spec, lo, hi in tasks:
            table = _fetch_single(spec, lo, hi)
            if table is not None:
                tables.append(table)
    else:
        ordered: list[tuple[int, Table]] = []
        with ThreadPoolExecutor(max_workers=min(effective_workers, len(tasks))) as executor:
            future_to_order = {
                executor.submit(_fetch_single, spec, lo, hi): order
                for order, spec, lo, hi in tasks
            }
            for future in as_completed(future_to_order):
                order = future_to_order[future]
                table = future.result()
                if table is not None:
                    ordered.append((order, table))
        ordered.sort(key=lambda item: item[0])
        tables.extend(table for _, table in ordered)

    if not tables:
        logger.warning("No tables returned from astroquery for the given parameters")
    return tables
