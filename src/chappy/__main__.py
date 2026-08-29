"""Main entry point for Chappy (Code for Handling Absorption Profiles with PYthon)."""

import argparse
import contextlib
import logging
import sys
from importlib.metadata import version as get_version
from pathlib import Path

from PySide6.QtCore import (
    QCoreApplication,
    QLoggingCategory,
    QTimer,
    QtMsgType,
    qInstallMessageHandler,
)
from PySide6.QtWidgets import QApplication, QMessageBox

from chappy.core.settings import AppSettings
from chappy.gui.application_font import configure_application_font
from chappy.gui.modes.identify.presets.preset_store import IdentifyPresetStore
from chappy.gui.shell.composition import create_shell_runtime
from chappy.gui.shell.dependencies import ShellDependencies
from chappy.gui.theme import apply_dark_palette, get_application_stylesheet
from chappy.i18n import QtTranslatorInstaller, get_language_switcher
from chappy.infrastructure.composition import create_default_infrastructure_dependencies
from chappy.logging_config import configure_logging


def qt_message_handler(msg_type: QtMsgType, _context: QLoggingCategory, message: str) -> None:
    """Custom Qt message handler to suppress noisy log messages.

    Args:
        msg_type: Type of Qt message
        context: Qt logging context (unused)
        message: The log message
    """
    # Suppress noisy keymapper warnings on macOS
    if "qt.qpa.keymapper" in message and "Mismatch between Cocoa" in message:
        return

    # Convert Qt message type to Python logging level
    if msg_type == QtMsgType.QtDebugMsg:
        logging.getLogger("Qt").debug(message)
    elif msg_type == QtMsgType.QtInfoMsg:
        logging.getLogger("Qt").info(message)
    elif msg_type == QtMsgType.QtWarningMsg:
        logging.getLogger("Qt").warning(message)
    elif msg_type == QtMsgType.QtCriticalMsg:
        logging.getLogger("Qt").error(message)
    elif msg_type == QtMsgType.QtFatalMsg:
        logging.getLogger("Qt").critical(message)


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="chappy: Code for Handling Absorption Profiles with PYthon", prog="chappy"
    )

    parser.add_argument("file", nargs="?", help="FITS spectrum file or project file to open")

    parser.add_argument("--error-file", help="FITS file containing error/uncertainty data")

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default=None,
        help="Set logging level (default: build-stage dependent)",
    )

    parser.add_argument(
        "--log-console", action="store_true", help="Enable console logging output (stderr)"
    )

    parser.add_argument(
        "--log-format",
        choices=["structured", "simple"],
        default=None,
        help="Select console log format (default: structured)",
    )

    parser.add_argument("--version", action="version", version=f"chappy {get_version('chappy')}")

    parser.add_argument(
        "--no-gui", action="store_true", help="Run in command-line mode (not implemented yet)"
    )

    parser.add_argument(
        "--verbose", action="store_true", help="Enable verbose output for calculations"
    )

    return parser.parse_args()


def main() -> int:
    """Main application entry point.

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    # Parse command line arguments
    args = parse_arguments()

    # Setup structured logging
    configure_logging(
        level_name=args.log_level, console_enabled=args.log_console, console_format=args.log_format
    )
    qInstallMessageHandler(qt_message_handler)
    logger = logging.getLogger(__name__)

    # Set verbose mode
    AppSettings.get_instance().set_verbose(args.verbose)

    logger.info("Starting chappy application")

    # Check for no-gui mode
    if args.no_gui:
        logger.error("Command-line mode not yet implemented")
        return 1

    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("chappy")
    app.setApplicationDisplayName("chappy")
    app.setApplicationVersion(get_version("chappy"))
    app.setOrganizationName("chappy")
    app.setOrganizationDomain("chappy.astronomy")

    # Native macOS style lays widgets out with Aqua layout-item rects (smaller
    # than the painted rect), which makes QSS-painted widgets overlap; Fusion
    # uses the widget rect and renders identically to offscreen test runs.
    app.setStyle("Fusion")
    apply_dark_palette(app)
    app.setStyleSheet(get_application_stylesheet())

    configure_application_font(app)

    # Translation catalogs must be installed before any translation-dependent
    # object (e.g. preset stores) is constructed.
    language_switcher = get_language_switcher()
    translator_installer = QtTranslatorInstaller(app)
    translator_installer.install_language(language_switcher.current_language)
    language_switcher.language_changed.connect(translator_installer.install_language)

    try:
        # Create main window
        dependencies = create_default_infrastructure_dependencies(
            translate_presets=_initial_preset_translate
        )
        shell_runtime = create_shell_runtime(
            ShellDependencies(
                project_io_usecase=dependencies.project_io_usecase,
                atomic_data=dependencies.atomic_repository,
                preset_store=IdentifyPresetStore(dependencies.preset_store),
                optimize_model_addition_usecase=dependencies.optimize_model_addition_usecase,
            )
        )
        shell_runtime.show()

        # Open file if specified
        if args.file:
            file_path = Path(args.file)

            if not file_path.exists():
                logger.error("File not found: %s", file_path)
                shell_runtime.open_initial_file(file_path, error_file=args.error_file)
            elif file_path.suffix.lower() in {".fits", ".fit"}:
                # Try to open as FITS file
                logger.info("Opening FITS file: %s", file_path)
                try:
                    shell_runtime.open_initial_file(file_path, error_file=args.error_file)
                    logger.info("Loaded FITS file: %s", file_path)
                    if args.error_file:
                        logger.info("With error data from: %s", args.error_file)
                except Exception as e:
                    logger.exception("Failed to load FITS file: %s", file_path)
                    template = QCoreApplication.translate("ChappyMain", "Failed to load: {error}")
                    shell_runtime.show_status_message(template.format(error=e), 5000)
            else:
                logger.warning("Unknown file type: %s", file_path)
                shell_runtime.open_initial_file(file_path, error_file=args.error_file)
        else:
            QTimer.singleShot(0, shell_runtime.maybe_show_first_run_welcome)

        logger.info("Application started successfully")

        # Run application event loop
        return app.exec()

    except Exception as e:
        logger.exception("Fatal error during application startup")

        # Try to show error dialog if possible
        with contextlib.suppress(Exception):  # Broad exception needed: Qt may be completely broken
            QMessageBox.critical(None, "Fatal Error", f"Application failed to start:\n{e}")

        return 1

    finally:
        logger.info("Application shutting down")


def _initial_preset_translate(source_text: str) -> str:
    """Return source text until the Qt preset facade installs its translator."""
    return str(source_text)


if __name__ == "__main__":
    sys.exit(main())
