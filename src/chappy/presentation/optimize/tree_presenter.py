"""Qt-independent optimize tree view models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OptimizeTreeRow:
    """Read-only snapshot of a row displayed in the optimize tree."""

    values: tuple[tuple[str, str], ...]
    children: tuple[OptimizeTreeRow, ...] = ()

    def value(self, column_key: str) -> str:
        """Return the displayed text for a column key.

        Args:
            column_key: Stable column key to read.

        Returns:
            Displayed text for the column, or an empty string when the key is absent.
        """
        for key, text in self.values:
            if key == column_key:
                return text
        return ""


@dataclass(frozen=True, slots=True)
class OptimizeTreeGroup:
    """Top-level optimize tree group view model."""

    row: OptimizeTreeRow


class OptimizeTreePresenter:
    """Build optimize tree view models from UI-neutral row values."""

    def build_row(
        self, values: tuple[tuple[str, str], ...], children: tuple[OptimizeTreeRow, ...] = ()
    ) -> OptimizeTreeRow:
        """Build a tree row view model.

        Args:
            values: Column key/text pairs.
            children: Child row view models.

        Returns:
            Tree row view model.
        """
        return OptimizeTreeRow(values=values, children=children)
