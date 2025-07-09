"""
Logging utilities with Windows-compatible file rotation and performance monitoring.

Key Features:
    - Windows-safe file rotation with permission error handling
    - Performance monitoring with context managers
    - Dynamic log level management
    - Automatic log cleanup and size management
"""

import datetime
import logging
import os
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# Generate a timestamp string for the current run
RUN_DATE = datetime.datetime.now().strftime("%Y-%m-%d")
RUN_TIMESTAMP = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
LOG_FILE_BASENAME = "timeline_app"
LOG_FILE = LOG_DIR / RUN_DATE / f"{LOG_FILE_BASENAME}_{RUN_TIMESTAMP}.log"

if not LOG_FILE.parent.exists():
    LOG_FILE.parent.mkdir(parents=True)

# Enhanced log format with more context
LOG_FORMAT = (
    "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
CONSOLE_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DEFAULT_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


class SafeTimedRotatingFileHandler(TimedRotatingFileHandler):
    """Windows-compatible file rotation handler with graceful error handling."""

    def doRollover(self):
        """Override doRollover to handle Windows file permission issues gracefully."""
        try:
            super().doRollover()
        except (OSError, PermissionError) as e:
            # Log the error to stderr since we can't use the logger itself
            import sys

            error_msg = f"Log rotation failed: {e}. Continuing with current log file.\n"
            sys.stderr.write(error_msg)
            sys.stderr.flush()

            # Reset the rollover time to try again later
            if hasattr(self, "rolloverAt"):
                # Add 1 hour to retry later
                self.rolloverAt = self.rolloverAt + 3600


def _get_log_level(level_str: str) -> int:
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    return level_map.get(level_str.upper(), logging.INFO)


def setup_logger(name: str, level: str | None = None) -> logging.Logger:
    """Set up logger with both console and file handlers."""
    logger = logging.getLogger(name)

    # Determine the appropriate log level
    if level:
        log_level = _get_log_level(level)
    else:
        log_level = _get_log_level(DEFAULT_LOG_LEVEL)

    logger.setLevel(log_level)

    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger

    # Console handler with simpler format
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter(CONSOLE_FORMAT, DATE_FORMAT)
    console_handler.setFormatter(console_formatter)

    # File handler with time-based rotation (safer for Windows)
    # Rotate daily at midnight, keep 30 days of logs
    file_handler = SafeTimedRotatingFileHandler(
        LOG_FILE,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
        utc=False,
    )
    file_handler.setLevel(log_level)
    file_formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
    file_handler.setFormatter(file_formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger


def set_module_log_level(module_name: str, level: str):
    """Dynamically set the log level for a specific module."""
    logger = logging.getLogger(module_name)
    log_level = _get_log_level(level)
    logger.setLevel(log_level)

    # Update handlers as well
    for handler in logger.handlers:
        handler.setLevel(log_level)

    logger.info(f"Log level for '{module_name}' changed to {level}")


def get_current_log_file() -> Path:
    """Return the current log file path."""
    return LOG_FILE


def list_log_files() -> list[Path]:
    """Return a list of all log files in the log directory."""
    # Include both current format and rotated format files
    current_files = list(LOG_DIR.glob(f"{LOG_FILE_BASENAME}_*.log"))
    rotated_files = list(LOG_DIR.glob(f"{LOG_FILE_BASENAME}_*.log.*"))
    return current_files + rotated_files


def cleanup_old_logs(keep_days: int = 7):
    """
    Clean up log files older than specified days.
    Enhanced to handle Windows file locking issues gracefully.
    """
    cutoff_time = datetime.datetime.now() - datetime.timedelta(days=keep_days)
    deleted_count = 0
    failed_count = 0

    for log_file in list_log_files():
        try:
            file_time = datetime.datetime.fromtimestamp(log_file.stat().st_mtime)
            if file_time < cutoff_time:
                # Try to delete the file
                log_file.unlink()
                print(f"Deleted old log file: {log_file}")
                deleted_count += 1
        except PermissionError as e:
            print(f"Permission denied when deleting log file {log_file}: {e}")
            failed_count += 1
        except FileNotFoundError:
            # File was already deleted, ignore
            pass
        except Exception as e:
            print(f"Error deleting log file {log_file}: {e}")
            failed_count += 1

    if deleted_count > 0 or failed_count > 0:
        print(
            f"Log cleanup completed: {deleted_count} files deleted, {failed_count} files failed to delete"
        )


def force_cleanup_large_logs(max_size_mb: int = 50):
    """
    Force cleanup of large log files to prevent disk space issues.
    Enhanced to handle Windows file locking issues gracefully.
    """
    max_size_bytes = max_size_mb * 1024 * 1024
    cleaned_count = 0

    for log_file in list_log_files():
        try:
            if log_file.stat().st_size > max_size_bytes:
                # For very large files, try to truncate instead of delete
                # This preserves the file handle for any active processes
                try:
                    with open(log_file, "w", encoding="utf-8") as f:
                        f.write(
                            f"# Log file truncated due to size ({log_file.stat().st_size / 1024 / 1024:.1f}MB) at {datetime.datetime.now()}\n"
                        )
                    print(f"Truncated large log file: {log_file}")
                    cleaned_count += 1
                except PermissionError:
                    print(f"Cannot truncate log file {log_file}: file is in use")
        except Exception as e:
            print(f"Error checking log file size {log_file}: {e}")

    if cleaned_count > 0:
        print(f"Large log cleanup completed: {cleaned_count} files truncated")


class PerformanceLogger:
    """Utility class for performance logging."""

    def __init__(self, logger: logging.Logger, operation_name: str):
        self.logger = logger
        self.operation_name = operation_name
        self.start_time = None

    def __enter__(self):
        self.start_time = datetime.datetime.now()
        self.logger.debug(f"Starting operation: {self.operation_name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration = datetime.datetime.now() - self.start_time
            duration_ms = duration.total_seconds() * 1000

            if exc_type:
                self.logger.error(
                    f"Operation '{self.operation_name}' failed after {duration_ms:.2f}ms: {exc_val}"
                )
            else:
                self.logger.info(
                    f"Operation '{self.operation_name}' completed in {duration_ms:.2f}ms"
                )


def log_performance(logger: logging.Logger, operation_name: str):
    """
    Decorator for logging function performance.
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            with PerformanceLogger(logger, operation_name):
                return func(*args, **kwargs)

        return wrapper

    return decorator
