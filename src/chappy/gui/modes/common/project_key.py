"""Opaque project keys for local UI restoration state."""

from __future__ import annotations

import hashlib
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path, PurePath
from uuid import UUID, uuid4

DirectoryEntries = Callable[[Path], Iterable[Path]]
SameFile = Callable[[Path, Path], bool]


class ProjectPathCanonicalizationError(RuntimeError):
    """Raised when an existing path cannot be canonicalized safely."""


@dataclass(frozen=True, slots=True)
class ProjectKey:
    """Identity used only for local UI restoration state."""

    value: str
    persistent: bool

    @classmethod
    def for_saved_path(cls, path: str | Path) -> ProjectKey:
        """Build a deterministic key for an existing saved-project file.

        The project session calls this only after a successful open or save,
        so accepting a missing path would hide an invalid project-context event.
        """
        canonical_path = canonical_project_path(path)
        digest = hashlib.sha256(canonical_path.encode("utf-8")).hexdigest()
        return cls(value=f"saved:{digest}", persistent=True)

    @classmethod
    def for_unsaved_session(cls, session_id: UUID | None = None) -> ProjectKey:
        """Build a non-persistent key for one in-process project session."""
        return cls(value=f"session:{session_id or uuid4()}", persistent=False)


def canonical_project_path(path: str | Path) -> str:
    """Return the volume-aware canonical path of an existing project file.

    Canonicalization enumerates each parent directory. A filesystem that allows
    traversal but denies directory listing raises
    :class:`ProjectPathCanonicalizationError` instead of deriving an unstable
    key from caller-provided spelling.
    """
    expanded = Path(path).expanduser()
    try:
        resolved = expanded.resolve(strict=True)
    except FileNotFoundError:
        raise
    except OSError as error:
        message = f"Cannot resolve saved project path: {expanded}"
        raise ProjectPathCanonicalizationError(message) from error
    if not resolved.is_file():
        message = f"Saved project path must identify an existing file: {expanded}"
        raise ValueError(message)
    return str(_canonicalize_resolved_path(resolved))


def _canonicalize_resolved_path(
    resolved: Path,
    *,
    directory_entries: DirectoryEntries | None = None,
    same_file: SameFile | None = None,
) -> Path:
    """Recover stored entry spelling without conflating case-sensitive files.

    ``Path.resolve()`` removes symlinks and ``..`` but preserves caller-provided
    letter case on case-insensitive macOS volumes. Each existing entry is
    therefore matched by filesystem identity and its stored name is retained.
    The injectable filesystem operations keep the selection rule independently
    testable on both case-sensitive and case-insensitive hosts.
    """
    list_entries = directory_entries or _directory_entries
    identities_match = same_file or _same_file
    anchor, requested_parts = _split_absolute_path(resolved)
    canonical = Path(anchor)
    for requested_name in requested_parts:
        requested_entry = canonical / requested_name
        try:
            candidates = tuple(list_entries(canonical))
        except OSError as error:
            message = f"Cannot list project path parent: {canonical}"
            raise ProjectPathCanonicalizationError(message) from error
        requested_lookup = _case_lookup_key(requested_name)
        identity_candidates: list[tuple[str, bool]] = []
        for entry in candidates:
            if _case_lookup_key(entry.name) != requested_lookup:
                continue
            try:
                matches = identities_match(entry, requested_entry)
            except OSError as error:
                message = f"Cannot compare project path entry identity: {requested_entry}"
                raise ProjectPathCanonicalizationError(message) from error
            identity_candidates.append((entry.name, matches))
        selected_name = _select_canonical_entry_name(requested_name, identity_candidates)
        canonical /= selected_name
    return canonical


def _split_absolute_path(path: PurePath) -> tuple[str, tuple[str, ...]]:
    """Split a POSIX, Windows-drive, or Windows-UNC absolute path."""
    if not path.is_absolute() or not path.anchor:
        message = f"Resolved project path must be absolute: {path}"
        raise ValueError(message)
    return path.anchor, tuple(path.parts[1:])


def _case_lookup_key(name: str) -> str:
    """Return a Unicode-stable key used only to find identity candidates."""
    return unicodedata.normalize("NFC", name).casefold()


def _select_canonical_entry_name(
    requested_name: str, candidates: Iterable[tuple[str, bool]]
) -> str:
    """Select stored spelling from case-equivalent entries with matching identity."""
    identity_matches = tuple(name for name, matches in candidates if matches)
    exact = next((name for name in identity_matches if name == requested_name), None)
    if exact is not None:
        return exact
    if len(identity_matches) == 1:
        return identity_matches[0]
    message = f"Cannot resolve canonical spelling for project path entry: {requested_name}"
    raise ProjectPathCanonicalizationError(message)


def _directory_entries(directory: Path) -> Iterable[Path]:
    """Return direct children used to recover filesystem-stored spelling."""
    return directory.iterdir()


def _same_file(first: Path, second: Path) -> bool:
    """Return whether two existing paths identify the same filesystem entry."""
    return first.samefile(second)


__all__ = ["ProjectKey", "ProjectPathCanonicalizationError", "canonical_project_path"]
