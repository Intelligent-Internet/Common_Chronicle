"""
Unified Embedding Service - Centralized embedding model management

Provides consistent, CPU-compatible Snowflake embedding functionality
across all application components with proper error handling and caching.

Based on the successful implementation from article_acquisition/components.py
"""

from __future__ import annotations

import os

import numpy as np
import torch
from transformers import AutoConfig, AutoModel, AutoTokenizer

from app.config import settings
from app.utils.logger import setup_logger

# Disable xformers memory efficient attention for CPU compatibility
os.environ["XFORMERS_DISABLED"] = "1"
os.environ["DISABLE_FLASH_ATTN"] = "1"

logger = setup_logger("embedding_service", level="DEBUG")


class UnifiedEmbeddingService:
    """
    Centralized embedding service using Snowflake model with CPU compatibility.

    Based on the successful implementation from article_acquisition/components.py
    Uses singleton pattern to ensure only one model instance across the application.
    """

    _instance = None  # Singleton pattern

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return

        self.model_name = settings.event_merger_embedding_model
        self.tokenizer = None
        self.model = None
        self.device = "cpu"  # CPU environment
        self._initialized = False

        self._load_model()

    def _load_model(self):
        """Load Snowflake model with CPU compatibility (based on components.py)"""
        try:
            logger.info(f"Loading unified embedding model: {self.model_name}")

            # 1. Load tokenizer (same as components.py)
            logger.info(f"Loading tokenizer: '{self.model_name}'")
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_name,
                trust_remote_code=settings.trust_remote_code_for_embeddings,
            )
            logger.info("Successfully loaded tokenizer.")

            # 2. Load config and disable memory efficient attention (same as components.py)
            logger.info(f"Loading model config for: '{self.model_name}'")
            config_obj = AutoConfig.from_pretrained(
                self.model_name,
                trust_remote_code=settings.trust_remote_code_for_embeddings,
            )

            # Critical: Disable memory efficient attention for CPU compatibility
            if hasattr(config_obj, "use_memory_efficient_attention"):
                config_obj.use_memory_efficient_attention = False
                logger.info(
                    "Disabled use_memory_efficient_attention for CPU compatibility"
                )

            # 3. Load model with eager attention (same as components.py)
            logger.info(
                f"Loading model '{self.model_name}' on {self.device} with eager attention"
            )
            self.model = AutoModel.from_pretrained(
                self.model_name,
                config=config_obj,  # Pass modified config
                trust_remote_code=settings.trust_remote_code_for_embeddings,
                attn_implementation="eager",  # Force standard attention
            ).to(self.device)
            self.model.eval()  # Set to evaluation mode

            self._initialized = True
            logger.info(f"Successfully loaded unified embedding model on {self.device}")

        except ImportError as ie:
            logger.error(
                f"ImportError during model loading: {ie}. This might be related to missing dependencies for the model '{self.model_name}'."
            )
            self.model = None
            self.tokenizer = None
            self._initialized = False
        except Exception as e:
            logger.error(f"Failed to load unified embedding model: {e}", exc_info=True)
            self.model = None
            self.tokenizer = None
            self._initialized = False

    def is_ready(self) -> bool:
        """Check if the embedding service is ready to use"""
        return (
            self._initialized and self.model is not None and self.tokenizer is not None
        )

    def encode(
        self,
        texts: str | list[str],
        convert_to_numpy: bool = True,
        normalize_embeddings: bool = True,
        add_query_prefix: bool = True,
    ) -> np.ndarray | torch.Tensor:
        """
        Encode text(s) to embeddings using Snowflake model.

        Args:
            texts: Single text or list of texts to encode
            convert_to_numpy: Whether to return numpy array (True) or torch tensor (False)
            normalize_embeddings: Whether to apply L2 normalization
            add_query_prefix: Whether to add "query: " prefix (for Snowflake model)

        Returns:
            Embeddings as numpy array or torch tensor (768 dimensions)
        """
        if not self.is_ready():
            logger.error("Embedding service not ready. Cannot encode texts.")
            # Return zero vector as fallback
            if isinstance(texts, str):
                fallback = np.zeros(768) if convert_to_numpy else torch.zeros(768)
            else:
                fallback = (
                    np.zeros((len(texts), 768))
                    if convert_to_numpy
                    else torch.zeros(len(texts), 768)
                )
            return fallback

        # Normalize input
        if isinstance(texts, str):
            texts = [texts]
            single_input = True
        else:
            single_input = False

        try:
            # Add query prefix if requested (Snowflake model convention, same as components.py)
            if add_query_prefix:
                prefixed_texts = [f"query: {text}" for text in texts]
            else:
                prefixed_texts = texts

            # Tokenize (same as components.py)
            inputs = self.tokenizer(
                prefixed_texts,
                padding=True,
                truncation=True,
                return_tensors="pt",
                max_length=512,
            ).to(self.device)

            # Forward pass (same as components.py)
            with torch.no_grad():
                outputs = self.model(**inputs)
                # Mean pooling (same as components.py)
                embeddings = torch.mean(outputs.last_hidden_state, dim=1)

            # L2 normalization (same as components.py)
            if normalize_embeddings:
                embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)

            # Convert to numpy if requested
            if convert_to_numpy:
                embeddings = embeddings.cpu().numpy()
                return embeddings.squeeze() if single_input else embeddings

            return embeddings.squeeze() if single_input else embeddings

        except Exception as e:
            logger.error(f"Error during text encoding: {e}", exc_info=True)
            # Return zero vector as fallback
            if single_input:
                fallback = np.zeros(768) if convert_to_numpy else torch.zeros(768)
            else:
                fallback = (
                    np.zeros((len(texts), 768))
                    if convert_to_numpy
                    else torch.zeros(len(texts), 768)
                )
            return fallback

    async def encode_async(
        self, texts: str | list[str], **kwargs
    ) -> np.ndarray | torch.Tensor:
        """Async wrapper for encode method"""
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.encode, texts, **kwargs)

    def get_embedding_for_pgvector(self, text: str) -> str:
        """
        Get embedding as string format for pgvector storage.

        Returns:
            String representation of embedding vector suitable for pgvector
        """
        try:
            embedding = self.encode(
                text, convert_to_numpy=True, normalize_embeddings=True
            )
            if embedding is not None and embedding.size > 0:
                return "[" + ",".join(map(str, embedding.tolist())) + "]"
            else:
                logger.warning("Empty embedding result, using zero vector fallback")
                return "[" + ",".join(["0.0"] * 768) + "]"
        except Exception as e:
            logger.error(f"Error generating pgvector embedding: {e}", exc_info=True)
            # Return zero vector string as fallback
            return "[" + ",".join(["0.0"] * 768) + "]"


# Global singleton instance
embedding_service = UnifiedEmbeddingService()
