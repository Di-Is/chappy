"""Profile registry for documentation exports."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chappy_user_manual_generator.user_manual_manifest import load_user_manual_manifest

if TYPE_CHECKING:
    from collections.abc import Callable

    from chappy_user_manual_generator.models import DocManifest

PROFILE_LOADERS: dict[str, Callable[[str], DocManifest]] = {
    "user-manual": load_user_manual_manifest
}


def available_profiles() -> list[str]:
    """Return the list of registered profile identifiers."""
    return sorted(PROFILE_LOADERS)


def load_profile(name: str, version: str) -> DocManifest:
    """Load a documentation manifest for ``name``."""
    try:
        loader = PROFILE_LOADERS[name]
    except KeyError as exc:
        msg = f"Unknown documentation profile: {name}"
        raise ValueError(msg) from exc
    return loader(version)
