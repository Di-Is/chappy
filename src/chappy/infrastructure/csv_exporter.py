"""CSV export adapters for optimization results."""

from __future__ import annotations

import csv
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path


class CsvExporter:
    """Write optimization export documents to CSV files."""

    def write(
        self,
        path: Path,
        header: Iterable[str],
        rows: Iterable[Iterable[str]],
        *,
        encoding: str = "utf-8",
    ) -> None:
        """Write a CSV file.

        Args:
            path: Output file path.
            header: Column headers.
            rows: Data rows.
            encoding: File encoding.
        """
        write_csv(path, header, rows, encoding=encoding)


def write_csv(
    path: Path, header: Iterable[str], rows: Iterable[Iterable[str]], *, encoding: str = "utf-8"
) -> None:
    """Write rows to CSV.

    Args:
        path: Output file path.
        header: Column headers.
        rows: Data rows.
        encoding: File encoding.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding=encoding, newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


__all__ = ["CsvExporter", "write_csv"]
