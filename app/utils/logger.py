"""
Logging utilities with Windows-compatible file rotation and performance monitoring.

Key Features:
    - Windows-safe file rotation with permission error handling
    - Performance monitoring with context managers
    - Dynamic log level management
    - Automatic log cleanup and size management
    - Combined size and time-based rotation (10MB max per file)
"""

import datetime
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# Global variables to ensure all loggers use the same log file
_GLOBAL_LOG_FILE = None

LOG_FILE_BASENAME = "timeline_app"

# Enhanced log format with more context
LOG_FORMAT = (
    "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
CONSOLE_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DEFAULT_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Log rotation settings
MAX_LOG_SIZE_MB = 5  # Maximum size per log file in MB
MAX_LOG_SIZE_BYTES = MAX_LOG_SIZE_MB * 1024 * 1024
MAX_BACKUP_COUNT = 10  # Maximum number of backup files per day

if _GLOBAL_LOG_FILE is None:
    # Calculate timestamp only once when first needed
    now = datetime.datetime.now()
    run_timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")

    # Create date-based directory
    date_dir = LOG_DIR / now.strftime("%Y-%m-%d")
    date_dir.mkdir(exist_ok=True)

    # Set the global log file path
    _GLOBAL_LOG_FILE = date_dir / f"{LOG_FILE_BASENAME}_{run_timestamp}.log"


class SafeRotatingFileHandler(RotatingFileHandler):
    """Windows-compatible size-based rotation handler with graceful error handling."""

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


class CombinedRotatingFileHandler(logging.Handler):
    """
    Combined handler that rotates logs based on size and uses a global log file.
    Simplified version that ensures all handlers use the same log file.
    """

    def __init__(self, max_bytes=MAX_LOG_SIZE_BYTES, backup_count=MAX_BACKUP_COUNT):
        super().__init__()
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.current_handler = None
        self._setup_current_handler()

    def _setup_current_handler(self):
        """Set up the current rotating file handler using the global log file."""

        # Create size-based rotating handler
        self.current_handler = SafeRotatingFileHandler(
            _GLOBAL_LOG_FILE,
            maxBytes=self.max_bytes,
            backupCount=self.backup_count,
            encoding="utf-8",
        )

        # Set the same formatter as this handler
        if self.formatter:
            self.current_handler.setFormatter(self.formatter)

    def emit(self, record):
        """Emit a record."""
        if self.current_handler:
            self.current_handler.emit(record)

    def setFormatter(self, formatter):
        """Set the formatter for both this handler and the current handler."""
        super().setFormatter(formatter)
        if self.current_handler:
            self.current_handler.setFormatter(formatter)

    def close(self):
        """Close the current handler."""
        if self.current_handler:
            self.current_handler.close()
        super().close()


def _get_log_level(level_str: str) -> int:
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    return level_map.get(level_str.upper(), logging.INFO)


def setup_logger(name: str, level: str = None) -> logging.Logger:
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

    # Combined file handler with size-based rotation using global log file
    file_handler = CombinedRotatingFileHandler(
        max_bytes=MAX_LOG_SIZE_BYTES, backup_count=MAX_BACKUP_COUNT
    )
    file_handler.setLevel(log_level)
    file_formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
    file_handler.setFormatter(file_formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    # Perform cleanup of old/large logs on logger setup
    cleanup_old_logs(keep_days=7)

    return logger


def list_log_files() -> list[Path]:
    """Return a list of all log files in the log directory."""
    all_files = []

    # Search in all date directories
    for date_dir in LOG_DIR.iterdir():
        if date_dir.is_dir():
            # Include both current format and rotated format files
            current_files = list(date_dir.glob(f"{LOG_FILE_BASENAME}_*.log"))
            rotated_files = list(date_dir.glob(f"{LOG_FILE_BASENAME}_*.log.*"))
            all_files.extend(current_files + rotated_files)

    return all_files


def cleanup_old_logs(keep_days: int = 7):
    """
    Clean up log files older than specified days.
    Enhanced to handle Windows file locking issues gracefully.
    """
    cutoff_time = datetime.datetime.now() - datetime.timedelta(days=keep_days)
    deleted_count = 0
    failed_count = 0

    # Clean up old date directories
    for date_dir in LOG_DIR.iterdir():
        if date_dir.is_dir():
            try:
                # Parse directory name to get date
                dir_date = datetime.datetime.strptime(date_dir.name, "%Y-%m-%d")
                if dir_date < cutoff_time:
                    # Delete all files in the directory
                    for log_file in date_dir.iterdir():
                        try:
                            log_file.unlink()
                            deleted_count += 1
                        except (PermissionError, FileNotFoundError):
                            failed_count += 1

                    # Try to remove the directory if empty
                    try:
                        date_dir.rmdir()
                    except (PermissionError, OSError):
                        pass  # Directory may not be empty due to failed deletions

            except ValueError:
                # Directory name doesn't match date format, skip
                continue
            except Exception as e:
                print(f"Error processing directory {date_dir}: {e}")
                failed_count += 1

    # Also clean up individual large files
    for log_file in list_log_files():
        try:
            file_time = datetime.datetime.fromtimestamp(log_file.stat().st_mtime)
            if file_time < cutoff_time:
                log_file.unlink()
                deleted_count += 1
        except (PermissionError, FileNotFoundError):
            failed_count += 1
        except Exception as e:
            print(f"Error deleting log file {log_file}: {e}")
            failed_count += 1

    if deleted_count > 0 or failed_count > 0:
        print(
            f"Log cleanup completed: {deleted_count} files deleted, {failed_count} files failed to delete"
        )
