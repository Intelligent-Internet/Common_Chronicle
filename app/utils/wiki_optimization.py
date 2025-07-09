"""
Wikipedia API optimization utilities for performance and reliability.

Provides adaptive rate limiting, intelligent retry mechanisms, performance
monitoring, and caching strategies. Handles various Wikipedia API error
conditions with robust error recovery.

Key Features:
    - Adaptive concurrent request limiting based on success rates
    - Intelligent retry strategies with exponential backoff
    - Comprehensive error classification and handling
    - Performance metrics collection and monitoring
    - HTTP/2 client optimization with connection pooling
    - Caching system with TTL and size limits
    - Dynamic timeout configuration based on operation type
"""

import asyncio
import time
from enum import Enum
from typing import Any

import httpx
from async_lru import alru_cache

from app.utils.logger import setup_logger

logger = setup_logger("wiki_optimization")


def _get_settings():
    """Lazy import of settings to avoid circular import."""
    from app.config import settings

    return settings


class WikiErrorType(Enum):
    """Wikipedia API error type enumeration for error classification."""

    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    SERVER_BUSY = "server_busy"
    NOT_FOUND = "not_found"
    NETWORK_ERROR = "network_error"
    UNKNOWN = "unknown"


class WikiAPIMetrics:
    """Performance monitoring metrics for Wikipedia API requests."""

    def __init__(self):
        self.request_count = 0
        self.success_count = 0
        self.error_count = 0
        self.total_response_time = 0.0
        self.cache_hit_count = 0
        self.error_by_type: dict[WikiErrorType, int] = {}

    def record_request(
        self,
        success: bool,
        response_time: float,
        from_cache: bool = False,
        error_type: WikiErrorType | None = None,
    ):
        """Record request metrics for performance monitoring."""
        self.request_count += 1
        self.total_response_time += response_time

        if from_cache:
            self.cache_hit_count += 1

        if success:
            self.success_count += 1
        else:
            self.error_count += 1
            if error_type:
                self.error_by_type[error_type] = (
                    self.error_by_type.get(error_type, 0) + 1
                )

    @property
    def success_rate(self) -> float:
        return self.success_count / self.request_count if self.request_count > 0 else 0

    @property
    def average_response_time(self) -> float:
        return (
            self.total_response_time / self.request_count
            if self.request_count > 0
            else 0
        )

    @property
    def cache_hit_rate(self) -> float:
        return (
            self.cache_hit_count / self.request_count if self.request_count > 0 else 0
        )

    def get_stats(self) -> dict[str, Any]:
        """Get comprehensive statistics about API performance."""
        return {
            "total_requests": self.request_count,
            "success_rate": round(self.success_rate, 3),
            "average_response_time": round(self.average_response_time, 3),
            "cache_hit_rate": round(self.cache_hit_rate, 3),
            "errors_by_type": {
                error_type.value: count
                for error_type, count in self.error_by_type.items()
            },
        }


# Global metrics instance for tracking Wikipedia API performance
wiki_metrics = WikiAPIMetrics()


def get_dynamic_timeout(
    page_size_hint: str | None = None, is_text_extraction: bool = False
) -> tuple[int, int]:
    """
    Get appropriate timeout settings based on page size and operation type.

    Dynamically adjusts timeouts based on expected operation complexity.
    Text extraction operations require longer timeouts due to content processing.
    """
    base_connect, base_read = _get_settings().wiki_api_timeout

    # Text extraction operations need longer read timeout
    if is_text_extraction:
        base_read = int(base_read * 1.5)

    if page_size_hint == "large":
        return (base_connect, min(base_read * 2, 120))  # Maximum 120 seconds
    elif page_size_hint == "medium":
        return (base_connect, int(base_read * 1.3))
    elif page_size_hint == "small":
        return (base_connect, max(int(base_read * 0.8), 15))  # Minimum 15 seconds
    else:
        return (base_connect, base_read)


def get_retry_delay(attempt: int, error_type: WikiErrorType) -> float:
    """
    Calculate exponential backoff delay based on error type and attempt count.

    Different error types use different backoff strategies:
    - Rate limits: aggressive backoff to respect API limits
    - Server busy: standard exponential backoff
    - Timeouts: gentler backoff for transient issues
    """
    base_delay = _get_settings().initial_wiki_retry_delay
    max_delay = 30.0  # Maximum delay of 30 seconds

    if error_type == WikiErrorType.RATE_LIMIT:
        # Rate limit uses more aggressive backoff
        delay = base_delay * (3**attempt)
    elif error_type == WikiErrorType.SERVER_BUSY:
        # Server busy uses standard exponential backoff
        delay = base_delay * (2**attempt)
    elif error_type == WikiErrorType.TIMEOUT:
        # Timeout uses gentler backoff
        delay = base_delay * (1.8**attempt)
    else:
        # Other errors use standard backoff
        delay = base_delay * (1.5**attempt)

    return min(delay, max_delay)


def classify_wiki_error(
    error: Exception, response_data: dict | None = None
) -> WikiErrorType:
    """
    Classify Wikipedia API error types for appropriate handling.

    Uses HTTP status codes, exception types, and API response data
    to determine the most appropriate retry strategy.
    """
    if isinstance(error, httpx.TimeoutException | asyncio.TimeoutError):
        return WikiErrorType.TIMEOUT

    if isinstance(error, httpx.HTTPStatusError):
        status_code = error.response.status_code
        if status_code == 429:
            return WikiErrorType.RATE_LIMIT
        elif status_code in (503, 502, 504):
            return WikiErrorType.SERVER_BUSY
        elif status_code == 404:
            return WikiErrorType.NOT_FOUND

    # Check for error information in API response
    if response_data and isinstance(response_data, dict):
        error_msg = str(response_data.get("error", "")).lower()
        if "maxlag" in error_msg or "busy" in error_msg:
            return WikiErrorType.SERVER_BUSY
        elif "not found" in error_msg or "missing" in error_msg:
            return WikiErrorType.NOT_FOUND

    # Network-related errors
    if isinstance(error, httpx.ConnectError | httpx.NetworkError):
        return WikiErrorType.NETWORK_ERROR

    return WikiErrorType.UNKNOWN


class AdaptiveSemaphore:
    """
    Adaptive concurrency control that adjusts limits based on success rates.

    Monitors error rates and automatically adjusts concurrency limits to
    maintain optimal performance while respecting API constraints.
    """

    def __init__(self, initial_limit: int = 5, min_limit: int = 2, max_limit: int = 15):
        self.initial_limit = initial_limit
        self.min_limit = min_limit
        self.max_limit = max_limit
        self.current_limit = initial_limit
        self.semaphore = asyncio.Semaphore(initial_limit)
        self.error_count = 0
        self.success_count = 0
        self.last_adjustment = time.time()
        self.adjustment_interval = 60  # Evaluate every 60 seconds

    async def __aenter__(self):
        await self.semaphore.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.semaphore.release()

        # Record results
        if exc_type is None:
            self.success_count += 1
        else:
            self.error_count += 1

        # Check if limit adjustment is needed
        await self._maybe_adjust_limit()

    async def _maybe_adjust_limit(self):
        """
        Dynamically adjust concurrency limit based on success rate.

        Uses sliding window analysis to determine if concurrency should be
        increased (low error rate) or decreased (high error rate).
        """
        current_time = time.time()
        if current_time - self.last_adjustment < self.adjustment_interval:
            return

        total_requests = self.error_count + self.success_count
        if total_requests < 10:  # Too few samples, don't adjust
            return

        error_rate = self.error_count / total_requests
        old_limit = self.current_limit

        if error_rate > 0.15:  # Error rate > 15%, reduce concurrency
            new_limit = max(self.min_limit, self.current_limit - 2)
        elif error_rate < 0.05:  # Error rate < 5%, increase concurrency
            new_limit = min(self.max_limit, self.current_limit + 1)
        else:
            new_limit = self.current_limit

        if new_limit != old_limit:
            logger.info(
                f"Adjusting Wikipedia API semaphore limit: {old_limit} -> {new_limit} (error_rate: {error_rate:.3f})"
            )
            self.current_limit = new_limit
            self.semaphore = asyncio.Semaphore(new_limit)

        # Reset counters
        self.error_count = 0
        self.success_count = 0
        self.last_adjustment = current_time


def create_optimized_http_client() -> httpx.AsyncClient:
    """
    Create HTTP client optimized for Wikipedia API access.

    Configures connection pooling, HTTP/2 support, and appropriate
    headers for efficient Wikipedia API interactions.
    """
    settings = _get_settings()
    timeout_config = httpx.Timeout(
        connect=settings.wiki_api_timeout[0],
        read=settings.wiki_api_timeout[1],
        write=10.0,
        pool=60.0,
    )

    limits_config = httpx.Limits(
        max_keepalive_connections=20, max_connections=50, keepalive_expiry=30.0
    )

    headers = {
        "User-Agent": settings.wiki_api_user_agent,
        "Accept-Encoding": "gzip, deflate",
        "Accept": "application/json",
        "Connection": "keep-alive",
    }

    return httpx.AsyncClient(
        timeout=timeout_config,
        limits=limits_config,
        headers=headers,
        http2=True,  # Enable HTTP/2 support
        follow_redirects=True,
    )


# Cache configuration
WIKI_CACHE_CONFIG = {
    "page_info_cache_size": 2000,
    "page_text_cache_size": 500,
    "cache_ttl": 3600,  # 1 hour
    "error_cache_ttl": 300,  # Error cache 5 minutes
}


@alru_cache(
    maxsize=WIKI_CACHE_CONFIG["page_info_cache_size"],
    ttl=WIKI_CACHE_CONFIG["cache_ttl"],
)
async def cached_wiki_operation(operation_key: str, *args, **kwargs):
    """Generic Wikipedia operation cache decorator."""
    # This is a generic cache framework, specific operations need to be implemented at call time


def get_cache_key(operation: str, *args) -> str:
    """Generate cache key from operation name and arguments."""
    # Convert arguments to strings and combine
    key_parts = [operation] + [str(arg) for arg in args]
    return "|".join(key_parts)


# Error handling strategy configuration
ERROR_HANDLING_STRATEGIES = {
    WikiErrorType.TIMEOUT: {"retry": True, "max_retries": 3},
    WikiErrorType.RATE_LIMIT: {"retry": True, "max_retries": 5},
    WikiErrorType.SERVER_BUSY: {"retry": True, "max_retries": 4},
    WikiErrorType.NOT_FOUND: {"retry": False, "max_retries": 0},
    WikiErrorType.NETWORK_ERROR: {"retry": True, "max_retries": 3},
    WikiErrorType.UNKNOWN: {"retry": True, "max_retries": 2},
}


def should_retry_error(error_type: WikiErrorType, attempt: int) -> bool:
    """Determine whether to retry a specific type of error."""
    strategy = ERROR_HANDLING_STRATEGIES.get(
        error_type, {"retry": False, "max_retries": 0}
    )
    return strategy["retry"] and attempt < strategy["max_retries"]


async def execute_with_retry_and_metrics(
    operation_func,
    *args,
    operation_name: str = "wiki_operation",
    parent_request_id: str | None = None,
    **kwargs,
):
    """
    Execute Wikipedia operation with retry and metrics recording.

    Implements comprehensive retry logic with exponential backoff,
    error classification, and performance monitoring.
    """
    log_prefix = f"[ParentReqID: {parent_request_id}] " if parent_request_id else ""
    start_time = time.time()
    last_exception = None
    settings = _get_settings()

    for attempt in range(settings.max_wiki_retries):
        try:
            result = await operation_func(*args, **kwargs)

            # Record success metrics
            response_time = time.time() - start_time
            wiki_metrics.record_request(success=True, response_time=response_time)

            logger.debug(
                f"{log_prefix}{operation_name} succeeded on attempt {attempt + 1}"
            )
            return result

        except Exception as e:
            last_exception = e
            error_type = classify_wiki_error(e)

            logger.warning(
                f"{log_prefix}{operation_name} failed on attempt {attempt + 1}/{settings.max_wiki_retries}: {e!r} (type: {error_type.value})"
            )

            # Check if we should retry
            if not should_retry_error(error_type, attempt):
                logger.info(
                    f"{log_prefix}Not retrying {operation_name} due to error type: {error_type.value}"
                )
                break

            if attempt < settings.max_wiki_retries - 1:
                delay = get_retry_delay(attempt, error_type)
                logger.info(f"{log_prefix}Retrying {operation_name} in {delay:.2f}s...")
                await asyncio.sleep(delay)

    # Record failure metrics
    response_time = time.time() - start_time
    error_type = (
        classify_wiki_error(last_exception) if last_exception else WikiErrorType.UNKNOWN
    )
    wiki_metrics.record_request(
        success=False, response_time=response_time, error_type=error_type
    )

    logger.error(
        f"{log_prefix}{operation_name} failed after {settings.max_wiki_retries} attempts. Last error: {last_exception!r}"
    )
    raise last_exception
