"""Controller for opening generated user manual artifacts."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from chappy.gui.shell.dialog_coordinator import ManualOpenResult, UserManualDialogAdapter

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

    from chappy.i18n import LanguageSwitcher

logger = logging.getLogger(__name__)


class UserManualController:
    """Resolve and open the generated user manual for the active language.

    Args:
        dialogs: Dialog and desktop-service adapter for manual opening.
        language_switcher: Runtime language switcher.
    """

    def __init__(
        self, dialogs: UserManualDialogAdapter, language_switcher: LanguageSwitcher
    ) -> None:
        """Initialize the controller.

        Args:
            dialogs: Dialog and desktop-service adapter for manual opening.
            language_switcher: Runtime language switcher.
        """
        self._dialogs = dialogs
        self._language_switcher = language_switcher

    def open_manual(
        self, parent: QWidget, *, title: str, missing_message: str, failure_message: str
    ) -> None:
        """Open the locally generated user manual in the default viewer.

        Args:
            parent: Parent widget for dialogs.
            title: Dialog title.
            missing_message: Message shown when the manual is missing.
            failure_message: Message shown when desktop opening fails.
        """
        manual_path = self.resolve_entry()
        result = self._dialogs.open_manual(
            parent,
            manual_path=manual_path,
            title=title,
            missing_message=missing_message,
            failure_message=failure_message,
        )
        if result == ManualOpenResult.MISSING:
            logger.warning("User manual not found; ensure docs/user_manual has been generated.")
            return

        if result == ManualOpenResult.FAILED:
            logger.error("Failed to open user manual at %s", manual_path)
            return

        logger.info("Opened user manual at %s", manual_path)

    def resolve_entry(self) -> Path | None:
        """Resolve the best user manual entry point for the active language.

        Returns:
            Existing manual entry path when available.
        """
        language = self._language_switcher.current_language or "ja"
        lang_code = language.split("-", 1)[0].lower()
        suffix = f"_{lang_code}" if lang_code else "_ja"
        candidates: list[Path] = []

        for root in self._manual_root_candidates():
            if root.is_file():
                candidates.append(root)
                continue

            html_candidate = root / f"html{suffix}" / "index.html"
            if html_candidate.exists():
                candidates.append(html_candidate)

            markdown_candidate = root / f"markdown{suffix}" / "index.md"
            if markdown_candidate.exists():
                candidates.append(markdown_candidate)

            direct_html = root / "index.html"
            if direct_html.exists():
                candidates.append(direct_html)

            direct_markdown = root / "index.md"
            if direct_markdown.exists():
                candidates.append(direct_markdown)

        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _manual_root_candidates(self) -> list[Path]:
        """Provide candidate roots that may contain generated manuals.

        Returns:
            Unique existing manual roots.
        """
        roots: list[Path] = []
        env_root = os.environ.get("CHAPPY_MANUAL_ROOT")
        if env_root:
            path = Path(env_root).expanduser()
            roots.append(path)

        bundled_root = Path(__file__).resolve().parents[2] / "manual"
        roots.append(bundled_root)

        project_root = Path(__file__).resolve().parents[5]
        default_root = project_root / "docs" / "user_manual" / "dist"
        roots.append(default_root)

        cwd_root = Path.cwd() / "docs" / "user_manual" / "dist"
        if cwd_root != default_root:
            roots.append(cwd_root)

        unique_roots: list[Path] = []
        seen: set[Path] = set()
        for root in roots:
            if not root.exists():
                continue
            resolved = root.resolve()
            if resolved not in seen:
                unique_roots.append(resolved)
                seen.add(resolved)
        return unique_roots
