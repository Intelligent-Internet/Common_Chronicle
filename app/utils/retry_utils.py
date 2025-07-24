"""
Retry utilities for database operations with intelligent error classification.

Provides automatic retry for transient database errors with session rollback
and exponential backoff. Handles SQLAlchemy async sessions and common
connection issues including Windows-specific errors.
"""

import asyncio
import errno  # Added for errno constants
from functools import wraps

from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

# Attempt to import asyncpg specific exceptions if asyncpg is used, for more precise error handling.
# This is optional; the broader DBAPIError/OperationalError will still catch them.
try:
    import asyncpg

    ASYNC_PG_DEFINED = True
except ImportError:
    ASYNC_PG_DEFINED = False
    asyncpg = None  # To satisfy linters if it's used conditionally

from app.utils.logger import setup_logger

logger = setup_logger("retry_utils")


def is_retryable_db_error(e: Exception) -> bool:
    """
    Classify database errors for retry decisions.

    Handles specific connection errors that are typically transient,
    including Windows-specific issues and network timeouts.
    """
    if isinstance(e, DBAPIError | OperationalError):
        # Specific check for ConnectionDoesNotExistError which is a common one for lost connections
        # This is often wrapped by DBAPIError
        if ASYNC_PG_DEFINED and isinstance(
            getattr(e, "orig", None), asyncpg.exceptions.ConnectionDoesNotExistError
        ):
            logger.info("ConnectionDoesNotExistError detected as retryable.")
            return True
        # Add other specific SQLAlchemy/driver errors that are definitely retryable
        return True  # General DBAPI/OperationalError are often retryable

    if isinstance(e, OSError):
        # Check for Windows-specific "semaphore timeout" (WinError 121)
        if hasattr(e, "winerror") and e.winerror == 121:
            logger.info("OSError WinError 121 detected as retryable.")
            return True
        # Check for common POSIX network errors like ETIMEDOUT, ECONNREFUSED, EHOSTUNREACH, ENETUNREACH
        if e.errno in [
            errno.ETIMEDOUT,
            errno.ECONNREFUSED,
            errno.EHOSTUNREACH,
            errno.ENETUNREACH,
        ]:
            logger.info(f"OSError errno {e.errno} detected as retryable.")
            return True

    return False


def async_retry_db(
    max_retries: int = 3, delay_seconds: float = 1.0, backoff_factor: float = 2.0
):
    """
    Decorator for retrying database operations with automatic session rollback.

    Catches SQLAlchemy errors and specific OSErrors indicative of connection issues.
    Automatically rolls back the session on retryable failures to maintain consistency.
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            retries_attempted = 0
            current_delay = delay_seconds
            last_exception_seen = None

            # Find AsyncSession in arguments for rollback on failure
            db_session: AsyncSession | None = None
            for arg in args:
                if isinstance(arg, AsyncSession):
                    db_session = arg
                    break
            if not db_session:
                # Fallback to check keyword arguments
                for val in kwargs.values():
                    if isinstance(val, AsyncSession):
                        db_session = val
                        break

            while retries_attempted < max_retries:
                try:
                    return await func(*args, **kwargs)
                except Exception as e:  # Catch any exception first
                    if is_retryable_db_error(e):
                        # Rollback session to prevent stale state
                        if db_session:
                            try:
                                logger.info(
                                    f"Rolling back session for '{func.__name__}' due to retryable error."
                                )
                                await db_session.rollback()
                            except Exception as rollback_exc:
                                logger.error(
                                    f"Critical: Failed to rollback session for '{func.__name__}' after a retryable error. "
                                    f"Aborting retries. Rollback error: {rollback_exc}",
                                    exc_info=True,
                                )
                                # If rollback fails, it's safer to not continue
                                # Re-raise the original exception
                                raise e from rollback_exc
                        else:
                            logger.warning(
                                f"Could not find DB session to roll back for '{func.__name__}'. "
                                "Proceeding with retry, but this may fail if the session is in a bad state."
                            )

                        logger.warning(
                            f"DB operation '{func.__name__}' failed (Attempt {retries_attempted + 1}/{max_retries}) "
                            f"due to {type(e).__name__}: {str(e)}. Retrying in {current_delay:.2f}s..."
                        )
                        last_exception_seen = e
                        await asyncio.sleep(current_delay)
                        retries_attempted += 1
                        current_delay *= backoff_factor
                    else:
                        # For non-retryable exceptions, log and re-raise immediately
                        logger.error(
                            f"Non-retryable exception in DB operation '{func.__name__}': {type(e).__name__} - {str(e)}",
                            exc_info=True,  # Keep exc_info for non-retryable ones for better debugging
                        )
                        raise

            # If all retries fail
            logger.error(
                f"DB operation '{func.__name__}' ultimately failed after {max_retries} retries."
            )
            if last_exception_seen:
                raise last_exception_seen
            else:
                # This path should ideally not be reached if logic is correct
                # But as a fallback, re-raise a generic error if no specific exception was stored
                raise Exception(
                    f"DB operation '{func.__name__}' failed after max retries, but no specific retryable exception was captured."
                )

        return wrapper

    return decorator
