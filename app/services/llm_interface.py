"""
Abstract interface for Large Language Model (LLM) services.

Defines the standard interface that all LLM providers must implement
for consistent interaction patterns across different language model services.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any

from app.config import settings


class LLMInterface(ABC):
    """
    Abstract Base Class for Large Language Model services.
    Defines a common interface for interacting with different LLM providers.
    """

    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = None,
        **kwargs: Any,
    ) -> str:
        """Generates text based on a given prompt."""
        # Use configured default if max_tokens is None
        if max_tokens is None:
            max_tokens = settings.llm_default_max_tokens

    @abstractmethod
    async def generate_chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any] | AsyncGenerator[dict[str, Any], None]:
        """
        Generates a chat completion based on a list of messages.

        Returns completion dict if stream=False, async generator if stream=True.
        """
        # Use configured default if max_tokens is None
        if max_tokens is None:
            max_tokens = settings.llm_default_max_tokens

    # Placeholder for embedding generation, can be expanded later
    # @abstractmethod
    # async def get_embeddings(
    #     self,
    #     text: str,
    #     model: str = None, # Embedding model might be different
    #     **kwargs: Any
    # ) -> List[float]:
    #     """
    #     Generates embeddings for the given text.
    #     """
    #     pass

    async def close(self):
        """
        Optional method to close any underlying connections or clients.
        Providers that don't need explicit closing can have an empty implementation.
        """
        # Default implementation does nothing
        # Subclasses can override this method if they need to close connections
        return
