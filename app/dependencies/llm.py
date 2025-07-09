from typing import Any

from fastapi import HTTPException, status

from app.services.llm_service import get_llm_client as get_shared_llm_instance
from app.utils.logger import setup_logger

logger = setup_logger("dependencies")


def get_llm_client() -> Any:
    """FastAPI dependency to get the shared LLM client."""
    client = get_shared_llm_instance()
    if client is None:
        logger.critical(
            "LLM client dependency requested, but client is not available. This indicates a startup configuration issue."
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM service is not available due to a configuration error.",
        )
    return client


if __name__ == "__main__":
    llm_client = get_llm_client()
    print(llm_client)
