"""Utility functions to build minimal FITS files for tests without astropy."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Iterable

import numpy as np

BLOCK_SIZE = 2880
CARD_SIZE = 80


def _format_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "T" if value else "F"
    if isinstance(value, int):
        return f"{value:d}"
    if isinstance(value, float):
        return f"{value: .10E}".replace("E", "E").strip()
    return str(value)


def _format_card(keyword: str, value: object | None = None) -> bytes:
    if len(keyword) > 8:
        raise ValueError(f"Keyword '{keyword}' exceeds 8 characters")
    if value is None:
        text = keyword.ljust(CARD_SIZE)
        return text.encode("ascii")
    if isinstance(value, str) and not value.startswith("'"):
        value_str = f"'{value}'"
    elif isinstance(value, str):
        value_str = value
    else:
        value_str = _format_scalar(value)
    if not isinstance(value, str):
        value_str = value_str.rjust(20)
    card = f"{keyword:<8}= {value_str}".ljust(CARD_SIZE)
    return card.encode("ascii")


def _write_header(stream, cards: Iterable[tuple[str, object | None]]) -> None:
    buffer = bytearray()
    for keyword, value in cards:
        buffer.extend(_format_card(keyword, value))
    buffer.extend(_format_card("END", None))
    padding = (-len(buffer)) % BLOCK_SIZE
    if padding:
        buffer.extend(b" " * padding)
    stream.write(buffer)


def _write_image_data(stream, data: np.ndarray) -> None:
    arr = np.asarray(data, dtype=np.float64)
    be = arr.astype(">f8")
    raw = be.tobytes()
    stream.write(raw)
    padding = (BLOCK_SIZE - (len(raw) % BLOCK_SIZE)) % BLOCK_SIZE
    if padding:
        stream.write(b"\0" * padding)


def write_primary_image(
    path: Path,
    data: np.ndarray,
    *,
    crval1: float = 0.0,
    cdelt1: float = 1.0,
    crpix1: float = 1.0,
    dc_flag: bool = False,
    extra_cards: Iterable[tuple[str, object]] | None = None,
) -> None:
    arr = np.asarray(data, dtype=np.float64)
    if arr.ndim != 1:
        raise ValueError("Only 1D data supported for test helper")
    cards: list[tuple[str, object | None]] = [
        ("SIMPLE", True),
        ("BITPIX", -64),
        ("NAXIS", 1),
        ("NAXIS1", arr.shape[0]),
        ("EXTEND", True),
        ("CRVAL1", crval1),
        ("CDELT1", cdelt1),
        ("CRPIX1", crpix1),
        ("DC-FLAG", 1 if dc_flag else 0),
    ]
    if dc_flag:
        cards.append(("CTYPE1", "LOGLIN"))
    if extra_cards:
        cards.extend((key, value) for key, value in extra_cards)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        _write_header(stream, cards)
        _write_image_data(stream, arr)


def write_empty_primary(path: Path) -> None:
    cards = [("SIMPLE", True), ("BITPIX", 8), ("NAXIS", 0), ("EXTEND", True)]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        _write_header(stream, cards)


def write_binary_table(
    path: Path,
    columns: dict[str, np.ndarray],
    *,
    extname: str | None = None,
    primary_header_cards: Iterable[tuple[str, object]] | None = None,
) -> None:
    if not columns:
        raise ValueError("columns must not be empty")
    nrows = len(next(iter(columns.values())))
    for col in columns.values():
        if len(col) != nrows:
            raise ValueError("All columns must share the same length")
    dtype_fields = []
    for name in columns:
        dtype_fields.append((name, ">f8"))
    table_dtype = np.dtype(dtype_fields)
    table = np.zeros(nrows, dtype=table_dtype)
    for name, values in columns.items():
        table[name] = np.asarray(values, dtype=np.float64)
    primary_cards = [("SIMPLE", True), ("BITPIX", 8), ("NAXIS", 0), ("EXTEND", True)]
    if primary_header_cards:
        primary_cards.extend(primary_header_cards)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        _write_header(stream, primary_cards)
        row_width = table_dtype.itemsize
        cards: list[tuple[str, object | None]] = [
            ("XTENSION", "BINTABLE"),
            ("BITPIX", 8),
            ("NAXIS", 2),
            ("NAXIS1", row_width),
            ("NAXIS2", nrows),
            ("PCOUNT", 0),
            ("GCOUNT", 1),
            ("TFIELDS", len(dtype_fields)),
        ]
        if extname:
            cards.append(("EXTNAME", extname))
        for idx, name in enumerate(columns, start=1):
            cards.append((f"TTYPE{idx}", name))
            cards.append((f"TFORM{idx}", "1D"))
        _write_header(stream, cards)
        raw = table.tobytes()
        stream.write(raw)
        padding = (BLOCK_SIZE - (len(raw) % BLOCK_SIZE)) % BLOCK_SIZE
        if padding:
            stream.write(b"\0" * padding)


def write_multi_extension(path: Path, extensions: list[tuple[str, np.ndarray]]) -> None:
    primary_cards: list[tuple[str, object | None]] = [
        ("SIMPLE", True),
        ("BITPIX", 8),
        ("NAXIS", 0),
        ("EXTEND", True),
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        _write_header(stream, primary_cards)
        for name, data in extensions:
            arr = np.asarray(data, dtype=np.float64)
            cards = [("XTENSION", "IMAGE"), ("BITPIX", -64), ("NAXIS", arr.ndim)]
            for axis_index, length in enumerate(reversed(arr.shape), start=1):
                cards.append((f"NAXIS{axis_index}", int(length)))
            cards.append(("EXTNAME", name))
            _write_header(stream, cards)
            _write_image_data(stream, arr)
