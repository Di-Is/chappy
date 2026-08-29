"""Application logging configuration utilities."""

from __future__ import annotations

import atexit
import contextlib
import errno
import logging
import os
import sys
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from logging.handlers import QueueHandler, QueueListener
from pathlib import Path
from queue import SimpleQueue
from typing import Any, TextIO

from pythonjsonlogger import json as jsonlogger

_LOG_DIR_ENV = "CHAPPY_LOG_DIR"
_LOG_LEVEL_ENV = "CHAPPY_LOG_LEVEL"
_LOG_CONSOLE_ENV = "CHAPPY_LOG_CONSOLE"
_LOG_MAX_FILES_ENV = "CHAPPY_LOG_MAX_FILES"
_LOG_MAX_SIZE_ENV = "CHAPPY_LOG_MAX_SIZE_MB"
_BUILD_STAGE_ENV = "CHAPPY_BUILD_STAGE"

_DEFAULT_MAX_SIZE_MB = 10
_DEFAULT_MAX_FILES = 10
_DEFAULT_RETENTION_DAYS = 30
_LOG_FILE_PREFIX = "chappy"
_LOG_DIR_PERMISSIONS = 0o755

_DISK_FULL_ERRNOS = {errno.ENOSPC, errno.EDQUOT}

_handler_lock = threading.Lock()


class _LoggingState:
    """Holds mutable logging state without relying on globals."""

    __slots__ = ("listener",)

    def __init__(self) -> None:
        self.listener: QueueListener | None = None


_STATE = _LoggingState()


@dataclass(slots=True)
class LoggingOptions:
    """Resolved logging options used for configuration."""

    level: int
    level_name: str
    console_enabled: bool
    console_format: str
    log_dir: Path
    max_files: int
    max_bytes: int


class ChappyRotatingFileHandler(logging.Handler):
    """Rotating file handler that writes structured NDJSON logs."""

    def __init__(self, options: LoggingOptions) -> None:
        super().__init__()
        self._options = options
        self._lock = threading.RLock()
        self._base_stem = self._build_base_stem()
        self._rotation_index = 0
        self._current_path: Path | None = None
        self._current_file: TextIO | None = None
        self._current_size = 0
        self._ensure_directory()
        self._open_new_log()

    def _build_base_stem(self) -> str:
        timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
        return f"{_LOG_FILE_PREFIX}_{timestamp}_{os.getpid()}"

    def _ensure_directory(self) -> None:
        self._options.log_dir.mkdir(mode=_LOG_DIR_PERMISSIONS, parents=True, exist_ok=True)

    def _next_log_path(self) -> Path:
        suffix = "" if self._rotation_index == 0 else f"_{self._rotation_index:03d}"
        return self._options.log_dir / f"{self._base_stem}{suffix}.log"

    def _open_new_log(self) -> None:
        self._current_path = self._next_log_path()
        self._current_file = self._current_path.open("a", encoding="utf-8", buffering=1)
        if self._current_path.exists():
            self._current_size = self._current_path.stat().st_size
        else:
            self._current_size = 0
        _enforce_file_limits(self._options.log_dir, self._options.max_files, self._current_path)

    def _rotate(self) -> None:
        if self._current_file:
            self._current_file.close()
        self._rotation_index += 1
        self._open_new_log()

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        encoded = f"{msg}\n"
        encoded_bytes = encoded.encode("utf-8")
        encoded_size = len(encoded_bytes)

        with self._lock:
            try:
                if self._should_rotate(encoded_size):
                    self._rotate()
                self._write(encoded, encoded_bytes)
            except OSError as error:  # Disk space failures shouldn't interrupt app flow
                if error.errno in _DISK_FULL_ERRNOS and self._try_recover_from_disk_full():
                    self._write(encoded, encoded_bytes)
                else:
                    raise

    def _should_rotate(self, incoming_size: int) -> bool:
        return self._current_size + incoming_size > self._options.max_bytes

    def _write(self, encoded: str, encoded_bytes: bytes) -> None:
        if self._current_file is None:
            self._open_new_log()
        if self._current_file is None:
            msg = "Log file handle is unavailable after attempting to open a new log."
            raise RuntimeError(msg)
        self._current_file.write(encoded)
        self._current_file.flush()
        self._current_size += len(encoded_bytes)

    def _try_recover_from_disk_full(self) -> bool:
        removed = _remove_oldest_log(self._options.log_dir, exclude=self._current_path)
        if not removed:
            removed = self._truncate_current_log()
        if removed and self._current_file is None:
            self._open_new_log()
        return removed

    def _truncate_current_log(self) -> bool:
        if not self._current_file or not self._current_path:
            return False
        try:
            self._current_file.close()
            self._current_file = self._current_path.open("w", encoding="utf-8", buffering=1)
            self._current_size = 0
        except OSError:
            return False
        else:
            return True

    def close(self) -> None:
        with self._lock:
            if self._current_file:
                self._current_file.close()
                self._current_file = None
        super().close()


class StructuredJSONFormatter(jsonlogger.JsonFormatter):
    """Produces NDJSON records adhering to logging requirements."""

    def add_fields(
        self, log_record: dict[str, Any], record: logging.LogRecord, message_dict: dict[str, Any]
    ) -> None:
        """Add custom fields to the JSON log record.

        Args:
            log_record: Dictionary that will be serialized to JSON
            record: LogRecord instance containing log event data
            message_dict: Additional fields from the message
        """
        super().add_fields(log_record, record, message_dict)

        # Custom field mappings to match existing format
        log_record["timestamp"] = _format_timestamp(record.created)
        log_record["level"] = record.levelname
        log_record["logger"] = record.name
        log_record["message"] = record.getMessage()
        log_record["module"] = record.module
        log_record["function"] = record.funcName
        log_record["line"] = record.lineno

        # Handle exception information
        if record.exc_info:
            exc_type, exc_value, _ = record.exc_info
            log_record["exception"] = {
                "type": exc_type.__name__ if exc_type else "Exception",
                "message": str(exc_value) if exc_value else "",
            }
            log_record["traceback"] = self.formatException(record.exc_info)

        # Handle stack trace information
        if record.stack_info:
            log_record.setdefault("traceback", record.stack_info)

        # Handle custom context data
        context_data = getattr(record, "context", None)
        if context_data is not None:
            log_record["context"] = context_data


class SimpleConsoleFormatter(logging.Formatter):
    """A terse human-readable console formatter."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = _format_timestamp(record.created)
        base = f"{timestamp} [{record.levelname}] {record.getMessage()}"
        if record.exc_info:
            base = f"{base}\n{''.join(self.formatException(record.exc_info))}"
        return base


@dataclass(slots=True)
class LoggingRuntime:
    """Holds references to active logging components."""

    listener: QueueListener
    handlers: tuple[logging.Handler, ...]


def configure_logging(
    *,
    level_name: str | None = None,
    console_enabled: bool | None = None,
    console_format: str | None = None,
) -> LoggingRuntime:
    """Configure application-wide logging according to requirements."""
    options = _resolve_options(level_name, console_enabled, console_format)

    file_handler = ChappyRotatingFileHandler(options)
    file_handler.setLevel(logging.NOTSET)
    file_handler.setFormatter(StructuredJSONFormatter())

    handlers: list[logging.Handler] = [file_handler]

    if options.console_enabled:
        console_handler = logging.StreamHandler()
        console_handler.setStream(_resolve_console_stream())
        console_handler.setLevel(logging.NOTSET)
        if options.console_format == "simple":
            console_handler.setFormatter(SimpleConsoleFormatter())
        else:
            console_handler.setFormatter(StructuredJSONFormatter())
        handlers.append(console_handler)

    queue: SimpleQueue[logging.LogRecord] = SimpleQueue()
    queue_handler = QueueHandler(queue)
    queue_handler.setLevel(options.level)

    root = logging.getLogger()
    with _handler_lock:
        _teardown_existing_listener()
        root.handlers.clear()
        root.setLevel(logging.NOTSET)
        root.addHandler(queue_handler)

        listener = QueueListener(queue, *handlers, respect_handler_level=True)
        listener.start()
        _register_shutdown(listener, handlers)

    _set_library_log_levels(options.level)

    return LoggingRuntime(listener=listener, handlers=tuple(handlers))


def shutdown_logging() -> None:
    """Stop the queue listener and close handlers."""
    with _handler_lock:
        _teardown_existing_listener()


def _resolve_options(
    level_name: str | None, console_enabled: bool | None, console_format: str | None
) -> LoggingOptions:
    resolved_level_name = _determine_level(level_name)
    level = getattr(logging, resolved_level_name, logging.INFO)

    console = _determine_console_enabled(console_enabled)
    format_choice = console_format or "structured"

    log_dir = _determine_log_dir()

    max_files = _coerce_int(os.getenv(_LOG_MAX_FILES_ENV), _DEFAULT_MAX_FILES, minimum=1)
    max_size_mb = _coerce_int(os.getenv(_LOG_MAX_SIZE_ENV), _DEFAULT_MAX_SIZE_MB, minimum=1)

    _cleanup_old_logs(log_dir, retention_days=_DEFAULT_RETENTION_DAYS)

    return LoggingOptions(
        level=level,
        level_name=resolved_level_name,
        console_enabled=console,
        console_format=format_choice,
        log_dir=log_dir,
        max_files=max_files,
        max_bytes=max_size_mb * 1024 * 1024,
    )


def _determine_level(level_name: str | None) -> str:
    if level_name:
        return level_name.upper()

    env_level = os.getenv(_LOG_LEVEL_ENV)
    if env_level:
        return env_level.upper()

    build_stage = os.getenv(_BUILD_STAGE_ENV, "alpha").lower()
    if build_stage in {"release", "prod", "production"}:
        return "WARNING"
    return "INFO"


def _determine_console_enabled(cli_value: bool | None) -> bool:
    if cli_value:
        return True

    env_value = os.getenv(_LOG_CONSOLE_ENV)
    if env_value is None:
        return False

    return env_value.strip().lower() in {"1", "true", "yes", "on"}


def _determine_log_dir() -> Path:
    override = os.getenv(_LOG_DIR_ENV)
    if override:
        return Path(override).expanduser()

    return Path.home() / ".chappy" / "log"


def _cleanup_old_logs(log_dir: Path, *, retention_days: int) -> None:
    if not log_dir.exists():
        return
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    for path in log_dir.glob(f"{_LOG_FILE_PREFIX}_*.log"):
        with contextlib.suppress(FileNotFoundError, OSError):
            mtime = datetime.fromtimestamp(path.stat().st_mtime, UTC)
            if mtime < cutoff:
                path.unlink()


def _enforce_file_limits(log_dir: Path, max_files: int, current: Path | None) -> None:
    if not log_dir.exists():
        return

    files = sorted(_iter_log_files(log_dir), key=lambda p: p.stat().st_mtime)
    excess = len(files) - max_files
    if excess <= 0:
        return

    removed = 0
    for path in files:
        if removed >= excess:
            break
        if current and path == current:
            continue
        with contextlib.suppress(FileNotFoundError, OSError):
            path.unlink()
            removed += 1


def _remove_oldest_log(log_dir: Path, *, exclude: Path | None) -> bool:
    for path in sorted(_iter_log_files(log_dir), key=lambda p: p.stat().st_mtime):
        if exclude and path == exclude:
            continue
        with contextlib.suppress(FileNotFoundError, OSError):
            path.unlink()
            return True
    return False


def _iter_log_files(log_dir: Path) -> list[Path]:
    if not log_dir.exists():
        return []
    return list(log_dir.glob(f"{_LOG_FILE_PREFIX}_*.log"))


def _coerce_int(raw: str | None, default: int, *, minimum: int) -> int:
    if raw is None:
        return default

    try:
        value = int(raw)
    except (ValueError, TypeError):
        return default

    if value < minimum:
        return default
    return value


def _format_timestamp(created: float) -> str:
    ts = datetime.fromtimestamp(created, tz=UTC)
    iso = ts.isoformat(timespec="milliseconds")
    return iso.replace("+00:00", "Z")


def _resolve_console_stream() -> TextIO:
    return sys.stderr


def _register_shutdown(listener: QueueListener, handlers: list[logging.Handler]) -> None:
    _STATE.listener = listener

    def _shutdown() -> None:
        with _handler_lock:
            _teardown_existing_listener()

    atexit.register(_shutdown)

    if hasattr(listener, "handlers"):
        listener.handlers = tuple(handlers)


def _teardown_existing_listener() -> None:
    listener = _STATE.listener
    if listener is None:
        return
    try:
        listener.stop()
    finally:
        raw_handlers = getattr(listener, "handlers", ())
        for handler in tuple(raw_handlers):
            with contextlib.suppress(Exception):
                handler.close()
        _STATE.listener = None


def _set_library_log_levels(level: int) -> None:
    logging.getLogger("chappy").setLevel(level)
    logging.getLogger("PySide6").setLevel(logging.WARNING)
    logging.getLogger("Qt").setLevel(logging.ERROR)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)


__all__ = ["LoggingRuntime", "configure_logging", "shutdown_logging"]
