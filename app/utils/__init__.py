"""
Common utilities package for the Common Chronicle application.

Essential utility functions supporting the timeline generation system:
authentication, logging, retry mechanisms, JSON parsing, and Wikipedia
API optimization.
"""

from app.utils.auth import (
    create_access_token,
    decode_access_token,
    extract_username_from_token,
    get_password_hash,
    verify_password,
)
from app.utils.json_parser import extract_json_from_llm_response
from app.utils.logger import PerformanceLogger, log_performance, setup_logger
from app.utils.retry_utils import async_retry_db, is_retryable_db_error
from app.utils.wiki_optimization import (
    WikiErrorType,
    classify_wiki_error,
    create_optimized_http_client,
    get_dynamic_timeout,
    wiki_metrics,
)

__all__ = [
    # Authentication utilities
    "create_access_token",
    "decode_access_token",
    "extract_username_from_token",
    "get_password_hash",
    "verify_password",
    # JSON parsing utilities
    "extract_json_from_llm_response",
    # Logging utilities
    "setup_logger",
    "PerformanceLogger",
    "log_performance",
    # Retry utilities
    "async_retry_db",
    "is_retryable_db_error",
    # Wikipedia optimization utilities
    "create_optimized_http_client",
    "get_dynamic_timeout",
    "classify_wiki_error",
    "WikiErrorType",
    "wiki_metrics",
]
