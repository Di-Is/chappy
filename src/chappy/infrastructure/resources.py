"""Infrastructure resource path resolution adapters."""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

_RUNTIME_DATA_ENV = "CHAPPY_DATA_DIR"


class RuntimeResourcePathResolver:
    """Resolve application data resources from runtime search roots."""

    def resolve_data_path(self, relative_path: str | Path) -> Path:
        """Resolve an existing resource path.

        Args:
            relative_path: Relative resource path.

        Returns:
            Resolved path to an existing resource.

        Raises:
            FileNotFoundError: If the resource is not found.
        """
        resolved = resolve_data_path(relative_path)
        if resolved is None:
            msg = f"Resource not found: {relative_path}"
            raise FileNotFoundError(msg)
        return resolved


def resolve_data_path(*relative: str | Path) -> Path | None:
    """Return the first existing path for the given resource fragments.

    Args:
        *relative: One or more path components that form a relative path.

    Returns:
        A resolved ``Path`` if found, otherwise ``None``.
    """
    target = Path(*relative)
    for base in runtime_search_dirs():
        candidate = base / target
        if candidate.exists():
            return candidate
    return None


@lru_cache(maxsize=1)
def runtime_search_dirs() -> tuple[Path, ...]:
    """Compute candidate directories for locating bundled resources.

    Returns:
        Candidate resource directories in lookup order.
    """
    bases: list[Path] = []

    env_override = os.environ.get(_RUNTIME_DATA_ENV)
    if env_override:
        bases.append(Path(env_override).expanduser())

    exe_path = Path(getattr(sys, "executable", sys.argv[0])).resolve()
    exe_dir = exe_path.parent
    module_root = Path(__file__).resolve().parents[3]

    is_frozen = bool(getattr(sys, "frozen", False))

    search_roots: list[Path] = []
    if is_frozen:
        search_roots.append(exe_dir)
        bundle_root = getattr(sys, "_MEIPASS", None)
        if bundle_root:
            search_roots.append(Path(bundle_root))

    if not search_roots:
        search_roots.append(module_root)

    for root in search_roots:
        bases.append(root)
        bases.append(root / "resources")

    if sys.platform == "darwin" and is_frozen:
        contents_dir = exe_dir.parent
        bases.append(contents_dir)
        resources_dir = contents_dir / "Resources"
        bases.append(resources_dir)
        bases.append(resources_dir / "resources")

    bases.append(module_root)
    bases.append(module_root / "resources")
    bases.append(Path.cwd())

    seen: set[Path] = set()
    ordered: list[Path] = []
    for base in bases:
        try:
            resolved = base.resolve()
        except OSError:
            continue
        if resolved not in seen:
            seen.add(resolved)
            ordered.append(resolved)

    return tuple(ordered)


__all__ = ["RuntimeResourcePathResolver", "resolve_data_path", "runtime_search_dirs"]
