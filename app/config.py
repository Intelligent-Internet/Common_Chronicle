"""
Centralized configuration management using pydantic-settings.
This module provides a single source of truth for all application configuration.
"""


import os

from dotenv import load_dotenv
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.utils.logger import setup_logger

load_dotenv(override=True)


logger = setup_logger("core_config")


class Settings(BaseSettings):
    """
    Application settings managed by pydantic-settings.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        # Allow override from environment variables
        env_prefix="",
    )

    # Feature flags & controls
    REUSE_COMPOSITE_VIEWPOINT: bool = False
    REUSE_BASE_VIEWPOINT: bool = False

    # ===== OpenAI Configuration =====
    openai_api_key: str | None = Field(
        default=None,
        alias="OPENAI_API_KEY",
        description="OpenAI API key for accessing OpenAI services",
    )

    openai_base_url: str | None = Field(
        default=None,
        alias="OPENAI_BASE_URL",
        description="OpenAI API base URL, defaults to https://api.openai.com/v1",
    )

    default_openai_model: str = Field(
        default="deepseek-chat",
        alias="DEFAULT_OPENAI_MODEL",
        description="Default OpenAI model to use",
    )

    # ===== Gemini Configuration =====
    gemini_api_key: str | None = Field(
        default=None, alias="GEMINI_API_KEY", description="Google Gemini API key"
    )

    default_gemini_model: str = Field(
        default="gemini-2.0-flash-lite", description="Default Gemini model to use"
    )

    # ===== Ollama Configuration =====
    ollama_base_url: str = Field(
        default="http://localhost:11434", description="Ollama API base URL"
    )

    # ===== LLM Provider Configuration =====
    default_llm_provider: str = Field(
        default="openai",
        description="Default LLM provider to use (openai, gemini, ollama)",
    )

    # ===== Database Configuration =====
    common_chronicle_schema: str = Field(
        default="common_chronicle_test",
        alias="COMMON_CHRONICLE_SCHEMA",
        description="Database schema name",
    )

    app_database_url: str | None = Field(
        default=None,
        alias="COMMON_CHRONICLE_DATABASE_URL",
        description="Application database URL",
    )

    app_database_url_for_alembic: str | None = Field(
        default=None,
        alias="COMMON_CHRONICLE_DATABASE_URL_FOR_ALEMBIC",
        description="Application database URL for alembic",
    )

    dataset_database_url: str | None = Field(
        default=None,
        alias="COMMON_CHRONICLE_DATASET_URL",
        description="Dataset database URL",
    )

    # ===== Timeout Configuration =====
    llm_timeout_extract: int = Field(
        default=120, description="LLM extraction timeout in seconds"
    )

    # ===== LLM Token Configuration =====
    llm_event_extraction_max_tokens: int = Field(
        default=32000, description="Maximum tokens for event extraction tasks"
    )

    llm_event_extraction_retry_max_tokens: int = Field(
        default=65536, description="Maximum tokens for event extraction retry attempts"
    )

    llm_default_max_tokens: int = Field(
        default=12800, description="Default maximum tokens for general LLM calls"
    )

    # ===== Text Chunking Configuration =====
    text_chunk_size_threshold: int = Field(
        default=16000, description="Text length threshold to trigger chunking strategy"
    )

    text_chunk_size: int = Field(
        default=10000, description="Size of each text chunk in characters"
    )

    text_chunk_overlap: int = Field(
        default=1000, description="Overlap between chunks in characters"
    )

    timeline_generation_timeout_seconds: int = Field(
        default=600,
        description="Timeline generation timeout in seconds (default 10 minutes)",
    )

    single_article_timeout_seconds: int = Field(
        default=120,
        description="Single article processing timeout in seconds (default 2 minutes)",
    )

    min_successful_articles_threshold: int = Field(
        default=1,
        description="Minimum successful articles required to continue processing",
    )

    # ===== Wikipedia API Configuration =====
    max_wiki_retries: int = Field(
        default=5, description="Maximum number of retries for Wikipedia API calls"
    )

    initial_wiki_retry_delay: float = Field(
        default=0.5,
        description="Initial delay between Wikipedia API retries in seconds",
    )

    wiki_api_semaphore_limit: int = Field(
        default=5, description="Maximum concurrent Wikipedia API requests"
    )

    wiki_api_timeout: tuple[float, float] = Field(
        default=(5.0, 60.0),
        description="Wikipedia API timeout (connection, read) in seconds",
    )

    wiki_api_user_agent: str = Field(
        default="CommonChronicleProject/0.1 (Generic Bot; contact: unavailable)",
        description="User-Agent string for Wikipedia API compliance",
    )

    # ===== Feature Flags =====
    enable_event_merger: bool = Field(
        default=True,
        description="Whether to enable the event merging step in timeline generation",
    )

    # ===== Article Processing Configuration =====
    default_article_limit: int = Field(
        default=10,
        alias="DEFAULT_ARTICLE_LIMIT",
        description="Default number of articles to process",
    )

    # ===== Task Management Configuration =====
    stuck_task_timeout_hours: int = Field(
        default=1, description="Hours after which a processing task is considered stuck"
    )

    # ===== Timeline Orchestrator Configuration =====
    # Previously hardcoded in timeline_orchestrator.py
    timeline_relevance_threshold: float = Field(
        default=0.6,
        description="Relevance threshold for timeline orchestrator initialization",
    )

    timeline_batch_size: int = Field(
        default=50, description="Batch size for timeline processing"
    )

    event_merger_relevance_threshold: float = Field(
        default=0.45, description="Relevance threshold for event merger service"
    )

    article_filter_relevance_threshold: float = Field(
        default=0.35,
        description="Relevance threshold for filtering articles by relevance",
    )

    # ===== Server Configuration =====
    # Previously hardcoded in main.py
    server_host: str = Field(default="0.0.0.0", description="Server host address")

    server_port: int = Field(default=8080, description="Server port number")

    server_workers: int = Field(default=1, description="Number of uvicorn workers")

    # ===== CORS Configuration =====
    cors_allow_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",  # Vite dev server default port
            "http://localhost:3000",  # Alternative dev port
            "http://127.0.0.1:5173",  # Local IP variant
            "https://your-domain.com",  # Production domain
        ],
        alias="CORS_ALLOW_ORIGINS",
        description="CORS allowed origins",
    )

    cors_allow_credentials: bool = Field(
        default=True, description="Whether to allow credentials in CORS requests"
    )

    cors_allow_methods: list[str] = Field(
        default_factory=lambda: ["*"], description="CORS allowed methods"
    )

    cors_allow_headers: list[str] = Field(
        default_factory=lambda: ["*"], description="CORS allowed headers"
    )

    # User-facing hint for database connection errors
    db_unavailable_hint: str = os.getenv(
        "DB_UNAVAILABLE_HINT",
        "Database connection failed. The server may be offline or network connectivity is down.",
    )

    @model_validator(mode="after")
    def validate_settings(self) -> "Settings":
        """Validate settings and log warnings for missing critical configurations."""

        # Log warnings for missing critical API keys
        if not self.openai_api_key:
            logger.warning("OPENAI_API_KEY environment variable not set.")

        if not self.openai_base_url:
            logger.warning("OPENAI_BASE_URL environment variable not set.")

        # Log warnings for missing critical database URLs
        if not self.app_database_url:
            logger.warning(
                "COMMON_CHRONICLE_DATABASE_URL environment variable not set."
            )

        # Log the database schema being used
        logger.debug(f"Using database schema: {self.common_chronicle_schema}")

        # Log event merger status
        logger.debug(f"Event merger enabled: {self.enable_event_merger}")

        return self

    @property
    def schema_name(self) -> str:
        return self.common_chronicle_schema


# Global settings instance
settings = Settings()

# Export commonly used values for backward compatibility
SCHEMA_NAME = settings.schema_name
