"""Tests for structured logging configuration."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from chappy import logging_config
from chappy.logging_config import LoggingRuntime, configure_logging, shutdown_logging


def _get_file_handler(runtime: LoggingRuntime) -> logging_config.ChappyRotatingFileHandler:
    for handler in runtime.handlers:
        if isinstance(handler, logging_config.ChappyRotatingFileHandler):
            return handler
    raise AssertionError("Missing ChappyRotatingFileHandler")


@pytest.fixture(autouse=True)
def clean_logging_handlers() -> None:
    """Ensure logging system is reset before each test."""
    shutdown_logging()
    logging.getLogger().handlers.clear()
    yield
    shutdown_logging()
    logging.getLogger().handlers.clear()


def test_configure_logging_creates_structured_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_root = tmp_path / "logs"
    monkeypatch.setenv("CHAPPY_LOG_DIR", str(log_root))

    runtime = configure_logging(level_name="INFO", console_enabled=False)
    logger = logging.getLogger("tests.struct")
    logger.info("loading project", extra={"context": {"operation_id": "abc123"}})

    shutdown_logging()

    log_files = sorted(log_root.glob("*.log"))
    assert len(log_files) == 1

    content = log_files[0].read_text(encoding="utf-8").strip().splitlines()
    assert content, "Expected at least one log entry"

    record = json.loads(content[-1])
    assert record["level"] == "INFO"
    assert record["logger"] == "tests.struct"
    assert record["message"] == "loading project"
    assert record["module"].startswith("test_logging_config")
    assert record["context"] == {"operation_id": "abc123"}
    assert record["timestamp"].endswith("Z")


def test_build_stage_default_level(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CHAPPY_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("CHAPPY_BUILD_STAGE", "release")

    runtime = configure_logging(level_name=None, console_enabled=False)
    file_handler = _get_file_handler(runtime)
    assert file_handler._options.level_name == "WARNING"  # type: ignore[attr-defined]

    shutdown_logging()

    monkeypatch.delenv("CHAPPY_BUILD_STAGE", raising=False)
    monkeypatch.setenv("CHAPPY_LOG_LEVEL", "debug")

    runtime = configure_logging(level_name=None, console_enabled=False)
    file_handler = _get_file_handler(runtime)
    assert file_handler._options.level_name == "DEBUG"  # type: ignore[attr-defined]


def test_size_rotation_creates_numbered_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_root = tmp_path / "logs"
    monkeypatch.setenv("CHAPPY_LOG_DIR", str(log_root))
    monkeypatch.setenv("CHAPPY_LOG_MAX_SIZE_MB", "1")

    configure_logging(level_name="INFO", console_enabled=False)
    logger = logging.getLogger("tests.rotation")

    logger.info("priming message")
    logger.info("%s", "x" * (1024 * 1050))

    shutdown_logging()

    files = sorted(log_root.glob("*.log"))
    assert len(files) == 2
    stems = {path.stem for path in files}
    assert any(stem.endswith("_001") for stem in stems)
