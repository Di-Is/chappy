"""Qt translator installer for the staged i18n migration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QObject, QTranslator

from chappy.i18n.languages import SOURCE_LANGUAGE_ID, normalize_language_id, require_language

_DEFAULT_CATALOG_PREFIX = "chappy"
_QTBASE_CATALOG_PREFIX = "qtbase"


@dataclass(frozen=True)
class QtTranslatorState:
    """Describe the currently installed Qt translation catalogs."""

    language_code: str
    app_catalog_path: Path | None
    app_translator_loaded: bool
    qtbase_catalog_path: Path | None
    qtbase_translator_loaded: bool


class QtTranslatorInstaller(QObject):
    """Install and remove Qt translators while coexisting with LanguageSwitcher."""

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        translation_root: Path | None = None,
        qt_translation_root: Path | None = None,
        catalog_prefix: str = _DEFAULT_CATALOG_PREFIX,
    ) -> None:
        """Create the installer.

        Args:
            parent: Optional Qt parent object.
            translation_root: Directory containing application ``.qm`` catalogs.
            qt_translation_root: Directory containing Qt standard ``.qm`` catalogs.
            catalog_prefix: Application catalog prefix used before the language code.
        """
        super().__init__(parent)
        self._translation_root = translation_root or default_translation_root()
        self._qt_translation_root = qt_translation_root or default_qt_translation_root()
        self._catalog_prefix = catalog_prefix
        self._app_translator: QTranslator | None = None
        self._qtbase_translator: QTranslator | None = None
        self._state = QtTranslatorState(
            language_code=SOURCE_LANGUAGE_ID,
            app_catalog_path=None,
            app_translator_loaded=False,
            qtbase_catalog_path=None,
            qtbase_translator_loaded=False,
        )

    @property
    def translation_root(self) -> Path:
        """Return the application catalog directory."""
        return self._translation_root

    @property
    def qt_translation_root(self) -> Path:
        """Return the Qt standard catalog directory."""
        return self._qt_translation_root

    @property
    def state(self) -> QtTranslatorState:
        """Return the last installed translation state."""
        return self._state

    @property
    def app_translator_loaded(self) -> bool:
        """Return whether an application translator is currently retained."""
        return self._app_translator is not None

    @property
    def qtbase_translator_loaded(self) -> bool:
        """Return whether a Qt base translator is currently retained."""
        return self._qtbase_translator is not None

    def install_language(self, language_code: str) -> QtTranslatorState:
        """Switch Qt translators to the requested language.

        Args:
            language_code: Language code such as ``en`` or ``ja``.

        Returns:
            Installed catalog state. Missing catalogs are reported as unloaded
            instead of raising, so the staged migration can coexist with YAML
            translations while catalogs are still incomplete.
        """
        normalized_language = normalize_language_id(language_code)
        self.remove_translators()

        definition = require_language(normalized_language)
        if definition.catalog_suffix is None:
            self._state = QtTranslatorState(
                language_code=normalized_language,
                app_catalog_path=None,
                app_translator_loaded=False,
                qtbase_catalog_path=None,
                qtbase_translator_loaded=False,
            )
            return self._state

        qtbase_catalog_path = self._catalog_path(
            root=self._qt_translation_root,
            prefix=_QTBASE_CATALOG_PREFIX,
            catalog_suffix=definition.catalog_suffix,
        )
        app_catalog_path = self._catalog_path(
            root=self._translation_root,
            prefix=self._catalog_prefix,
            catalog_suffix=definition.catalog_suffix,
        )
        self._qtbase_translator = self._load_and_install(qtbase_catalog_path)
        self._app_translator = self._load_and_install(app_catalog_path)
        self._state = QtTranslatorState(
            language_code=normalized_language,
            app_catalog_path=app_catalog_path,
            app_translator_loaded=self._app_translator is not None,
            qtbase_catalog_path=qtbase_catalog_path,
            qtbase_translator_loaded=self._qtbase_translator is not None,
        )
        return self._state

    def remove_translators(self) -> None:
        """Remove retained translators from the current QCoreApplication."""
        if self._app_translator is not None:
            QCoreApplication.removeTranslator(self._app_translator)
            self._app_translator = None
        if self._qtbase_translator is not None:
            QCoreApplication.removeTranslator(self._qtbase_translator)
            self._qtbase_translator = None
        self._state = QtTranslatorState(
            language_code=SOURCE_LANGUAGE_ID,
            app_catalog_path=None,
            app_translator_loaded=False,
            qtbase_catalog_path=None,
            qtbase_translator_loaded=False,
        )

    def _load_and_install(self, catalog_path: Path) -> QTranslator | None:
        """Load a catalog and install it when possible.

        Args:
            catalog_path: Candidate ``.qm`` catalog path.

        Returns:
            Installed translator, or ``None`` when the catalog is missing or
            cannot be loaded.
        """
        if not catalog_path.is_file():
            return None

        translator = QTranslator(self)
        if not translator.load(str(catalog_path)):
            return None
        if not QCoreApplication.installTranslator(translator):
            return None
        return translator

    def _catalog_path(self, *, root: Path, prefix: str, catalog_suffix: str) -> Path:
        """Build a catalog path.

        Args:
            root: Directory containing catalogs.
            prefix: Catalog prefix.
            catalog_suffix: Catalog suffix from the language definition.

        Returns:
            Candidate catalog path.
        """
        return root / f"{prefix}_{catalog_suffix}.qm"


class QtCatalogLookup(QObject):
    """Resolve translations from QM catalogs without installing translators."""

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        translation_root: Path | None = None,
        catalog_prefix: str = _DEFAULT_CATALOG_PREFIX,
    ) -> None:
        """Create the lookup helper.

        Args:
            parent: Optional Qt parent object.
            translation_root: Directory containing application ``.qm`` catalogs.
            catalog_prefix: Application catalog prefix used before the language code.
        """
        super().__init__(parent)
        self._translation_root = translation_root or default_translation_root()
        self._catalog_prefix = catalog_prefix
        self._translators: dict[str, QTranslator | None] = {}

    @property
    def translation_root(self) -> Path:
        """Return the application catalog directory."""
        return self._translation_root

    def translate(
        self, language_code: str, context: str, source_text: str, disambiguation: str | None = None
    ) -> str:
        """Translate source text for a language without changing application state.

        Args:
            language_code: Language code such as ``en`` or ``ja``.
            context: Qt translation context.
            source_text: Source text to translate.
            disambiguation: Optional Qt disambiguation comment.

        Returns:
            Translated text, or the source text when the catalog or entry is missing.
        """
        definition = require_language(language_code)
        if definition.catalog_suffix is None:
            return source_text

        translator = self._translator_for(definition.catalog_suffix)
        if translator is None:
            return source_text

        translated = translator.translate(context, source_text, disambiguation)
        return translated or source_text

    def _translator_for(self, catalog_suffix: str) -> QTranslator | None:
        """Return a cached translator for a catalog suffix.

        Args:
            catalog_suffix: Catalog suffix from the language definition.

        Returns:
            Loaded translator, or ``None`` when unavailable.
        """
        if catalog_suffix in self._translators:
            return self._translators[catalog_suffix]

        catalog_path = self._translation_root / f"{self._catalog_prefix}_{catalog_suffix}.qm"
        if not catalog_path.is_file():
            self._translators[catalog_suffix] = None
            return None

        translator = QTranslator(self)
        if not translator.load(str(catalog_path)):
            self._translators[catalog_suffix] = None
            return None

        self._translators[catalog_suffix] = translator
        return translator


def default_translation_root() -> Path:
    """Return the default application Qt translation catalog directory."""
    return Path(__file__).resolve().parent / "qt"


def default_qt_translation_root() -> Path:
    """Return the default Qt standard translation catalog directory."""
    return Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
