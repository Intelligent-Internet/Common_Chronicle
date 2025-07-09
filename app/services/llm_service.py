"""
LLM Service Manager - Centralized management of multiple LLM providers.

Provides unified interface for managing OpenAI, Gemini, and Ollama clients
with automatic initialization, configuration validation, and graceful fallback.
"""

from typing import Any

from app.config import settings
from app.services.llm_interface import LLMInterface
from app.services.llm_providers.gemini_client import GeminiClient
from app.services.llm_providers.ollama_client import OllamaClient
from app.services.llm_providers.openai_client import OpenAIClient
from app.utils.logger import setup_logger

logger = setup_logger("llm_service_manager", level="DEBUG")

# Client instances cache
_initialized_clients: dict[str, LLMInterface] = {}

# Mapping of provider names to their constructor classes
_client_constructors: dict[str, type[LLMInterface]] = {
    "openai": OpenAIClient,
    "gemini": GeminiClient,
    "ollama": OllamaClient,
}

# Default models for each provider if not specified in get_llm_client or constructor
_default_provider_models = {
    "openai": settings.default_openai_model,
    "gemini": settings.default_gemini_model,
    "ollama": "llama3:instruct",  # Sensible default for Ollama
}


def _get_client_config(provider_name: str) -> dict[str, Any]:
    logger.debug(f"Getting configuration for provider: {provider_name}")

    if provider_name == "openai":
        config = {
            "api_key": settings.openai_api_key,
            "base_url": settings.openai_base_url,
            "default_model": _default_provider_models["openai"],
        }
        # Log config without exposing sensitive data
        logger.debug(
            f"OpenAI config - base_url: {config['base_url']}, model: {config['default_model']}, api_key: {config['api_key'][:5] + '...' if config['api_key'] else 'None'}"
        )
        return config
    elif provider_name == "gemini":
        config = {
            "api_key": settings.gemini_api_key,
            "default_model": _default_provider_models["gemini"],
        }
        logger.debug(
            f"Gemini config - model: {config['default_model']}, api_key: {config['api_key'][:5] + '...' if config['api_key'] else 'None'}"
        )
        return config
    elif provider_name == "ollama":
        config = {
            "base_url": settings.ollama_base_url,
            "default_model": _default_provider_models["ollama"],
        }
        logger.debug(
            f"Ollama config - base_url: {config['base_url']}, model: {config['default_model']}"
        )
        return config
    else:
        logger.warning(f"Unknown provider name: {provider_name}")
        return {}


def initialize_all_llm_clients():
    """Initialize all LLM clients based on available configuration."""
    logger.info("Initializing LLM clients based on available configuration...")

    initialization_results = {"successful": [], "failed": [], "skipped": []}

    for provider_name in _client_constructors.keys():
        logger.debug(f"Processing provider: {provider_name}")

        if provider_name in _initialized_clients:
            logger.debug(f"{provider_name} client already initialized, skipping")
            initialization_results["skipped"].append(provider_name)
            continue

        config = _get_client_config(provider_name)
        constructor = _client_constructors[provider_name]

        # Check required configuration for each provider
        if provider_name == "openai" and not config.get("api_key"):
            logger.warning(
                "OpenAI API key not configured. Skipping OpenAI client initialization."
            )
            initialization_results["skipped"].append(provider_name)
            continue
        if provider_name == "gemini" and not config.get("api_key"):
            logger.warning(
                "Gemini API key not configured. Skipping Gemini client initialization."
            )
            initialization_results["skipped"].append(provider_name)
            continue
        # Ollama usually doesn't require an API key, base_url is the main config
        if provider_name == "ollama" and not config.get("base_url"):
            logger.warning(
                "Ollama base URL not configured. Skipping Ollama client initialization."
            )
            initialization_results["skipped"].append(provider_name)
            continue

        try:
            logger.debug(f"Attempting to initialize {provider_name} client")

            # Filter config for keys relevant to the constructor to avoid passing unexpected arguments
            relevant_config_keys = []
            if provider_name == "openai":
                relevant_config_keys = ["api_key", "base_url", "default_model"]
            elif provider_name == "gemini":
                relevant_config_keys = ["api_key", "default_model"]
            elif provider_name == "ollama":
                relevant_config_keys = [
                    "base_url",
                    "default_model",
                    "request_timeout",
                ]

            constructor_args = {
                k: v
                for k, v in config.items()
                if k in relevant_config_keys and v is not None
            }

            logger.debug(
                f"Constructor args for {provider_name}: {list(constructor_args.keys())}"
            )

            _initialized_clients[provider_name] = constructor(**constructor_args)
            logger.info(
                f"{provider_name.capitalize()} client successfully initialized."
            )
            initialization_results["successful"].append(provider_name)

        except ValueError as ve:
            logger.error(
                f"Configuration error initializing {provider_name} client: {ve}"
            )
            initialization_results["failed"].append(provider_name)
        except Exception as e:
            logger.error(
                f"Failed to initialize {provider_name} client: {e}", exc_info=True
            )
            initialization_results["failed"].append(provider_name)

    logger.info(
        f"LLM client initialization complete. "
        f"Successful: {initialization_results['successful']}, "
        f"Failed: {initialization_results['failed']}, "
        f"Skipped: {initialization_results['skipped']}"
    )


async def close_all_llm_clients():
    """Close all initialized LLM clients."""
    logger.info("Closing all initialized LLM clients.")

    if not _initialized_clients:
        logger.info("No LLM clients to close.")
        return

    close_results = {"successful": [], "failed": [], "no_close_method": []}

    for provider_name, client_instance in _initialized_clients.items():
        logger.debug(f"Attempting to close {provider_name} client")

        if hasattr(client_instance, "close") and callable(client_instance.close):
            try:
                await client_instance.close()
                logger.info(f"{provider_name.capitalize()} client closed successfully.")
                close_results["successful"].append(provider_name)
            except Exception as e:
                logger.error(
                    f"Error closing {provider_name} client: {e}", exc_info=True
                )
                close_results["failed"].append(provider_name)
        else:
            logger.debug(f"{provider_name} client does not have a close method")
            close_results["no_close_method"].append(provider_name)

    _initialized_clients.clear()
    logger.info(
        f"All LLM clients cleared from cache. "
        f"Closed: {close_results['successful']}, "
        f"Failed to close: {close_results['failed']}, "
        f"No close method: {close_results['no_close_method']}"
    )


def get_llm_client(provider_name: str = "openai") -> LLMInterface | None:
    """
    Get an initialized LLM client for the specified provider.

    Returns None if the provider is not available or not properly configured.
    """
    provider_name = provider_name.lower()
    client = _initialized_clients.get(provider_name)
    if client:
        logger.debug(f"Returning cached {provider_name} client")
        return client

    logger.info(
        f"{provider_name.capitalize()} client not pre-initialized. Attempting on-demand initialization."
    )

    if provider_name not in _client_constructors:
        logger.error(
            f"Unknown provider name: {provider_name}. Available providers: {list(_client_constructors.keys())}"
        )
        return None

    config = _get_client_config(provider_name)
    constructor = _client_constructors[provider_name]

    # Validate required configuration
    if provider_name == "openai" and not config.get("api_key"):
        logger.error("Cannot initialize OpenAI client: API key missing.")
        return None
    if provider_name == "gemini" and not config.get("api_key"):
        logger.error("Cannot initialize Gemini client: API key missing.")
        return None
    if provider_name == "ollama" and not config.get("base_url"):
        logger.error("Cannot initialize Ollama client: Base URL missing.")
        return None

    try:
        logger.debug(f"Attempting on-demand initialization of {provider_name} client")

        relevant_config_keys = []
        if provider_name == "openai":
            relevant_config_keys = ["api_key", "base_url", "default_model"]
        elif provider_name == "gemini":
            relevant_config_keys = ["api_key", "default_model"]
        elif provider_name == "ollama":
            relevant_config_keys = ["base_url", "default_model", "request_timeout"]

        constructor_args = {
            k: v
            for k, v in config.items()
            if k in relevant_config_keys and v is not None
        }

        logger.debug(
            f"On-demand constructor args for {provider_name}: {list(constructor_args.keys())}"
        )

        instance = constructor(**constructor_args)
        _initialized_clients[provider_name] = instance
        logger.info(
            f"{provider_name.capitalize()} client initialized on-demand and cached."
        )
        return instance

    except ValueError as ve:
        logger.error(
            f"Configuration error initializing {provider_name} client on demand: {ve}"
        )
        return None
    except Exception as e:
        logger.error(
            f"Failed to initialize {provider_name} client on demand: {e}", exc_info=True
        )
        return None
