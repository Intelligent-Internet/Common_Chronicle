import time
from collections.abc import AsyncGenerator
from typing import Any

from openai import AsyncOpenAI, OpenAIError

from app.config import settings
from app.services.llm_interface import LLMInterface
from app.utils.logger import setup_logger

logger = setup_logger("openai_client")


class OpenAIClient(LLMInterface):
    """
    LLM Client implementation for OpenAI API.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        default_model: str = settings.default_openai_model,
    ):
        if not api_key:
            logger.error("OpenAI API key is required but not provided")
            raise ValueError("OpenAI API key is required.")

        self.api_key = api_key
        self.base_url = base_url
        self.default_model = default_model

        logger.debug(
            f"Initializing OpenAI client with model: {default_model}, base_url: {base_url or 'Default'}"
        )

        client_args = {"api_key": self.api_key}
        if self.base_url:
            client_args["base_url"] = self.base_url

        try:
            self._client = AsyncOpenAI(**client_args)
            logger.info(
                f"OpenAI client initialized successfully. Base URL: {'Default' if not self.base_url else self.base_url}, Default Model: {self.default_model}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}", exc_info=True)
            raise

    async def generate_text(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 8000,
        **kwargs: Any,
    ) -> str:
        # Input validation and logging
        if not prompt or not prompt.strip():
            logger.warning("Empty or whitespace-only prompt provided to generate_text")
            return ""

        prompt_length = len(prompt)
        effective_model = self.default_model

        logger.debug(
            f"generate_text called with prompt length: {prompt_length}, temperature: {temperature}, max_tokens: {max_tokens}, model: {effective_model}"
        )

        if prompt_length > 100000:  # Arbitrary large threshold
            logger.warning(
                f"Very large prompt provided ({prompt_length} chars), this may cause performance issues"
            )

        start_time = time.perf_counter()
        try:
            logger.debug(
                f"Making OpenAI completions API call for text generation with model: {effective_model}"
            )

            response = await self._client.completions.create(
                model=effective_model,
                prompt=prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )

            if not response.choices:
                logger.error("No choices returned in OpenAI completions response")
                result_text = ""
            else:
                result_text = response.choices[0].text.strip()
                logger.debug(
                    f"Successfully got completion text, length: {len(result_text)}"
                )

            end_time = time.perf_counter()
            duration = end_time - start_time

            # Performance logging
            logger.info(
                f"OpenAI generate_text completed successfully for model {effective_model} in {duration:.4f}s, "
                f"input: {prompt_length} chars, output: {len(result_text)} chars"
            )

            # Log performance warnings
            if duration > 30:
                logger.warning(f"Slow API response: {duration:.4f}s for generate_text")

            return result_text

        except OpenAIError as e:
            end_time = time.perf_counter()
            duration = end_time - start_time

            # Enhanced error logging for OpenAI specific errors
            error_type = type(e).__name__
            logger.error(
                f"OpenAI API error during text generation for model {effective_model} after {duration:.4f}s: "
                f"{error_type}: {e}",
                exc_info=True,
            )

            # Log additional context for debugging
            logger.error(
                f"Failed request context - prompt_length: {prompt_length}, temperature: {temperature}, max_tokens: {max_tokens}"
            )

            raise
        except Exception as e:
            end_time = time.perf_counter()
            duration = end_time - start_time

            # Enhanced error logging for unexpected errors
            error_type = type(e).__name__
            logger.error(
                f"Unexpected error during OpenAI text generation for model {effective_model} after {duration:.4f}s: "
                f"{error_type}: {e}",
                exc_info=True,
            )

            # Log additional context for debugging
            logger.error(
                f"Failed request context - prompt_length: {prompt_length}, temperature: {temperature}, max_tokens: {max_tokens}"
            )

            raise

    async def generate_chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 8000,
        stream: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any] | AsyncGenerator[dict[str, Any], None]:
        # Input validation and logging
        if not messages:
            logger.error("Empty messages list provided to generate_chat_completion")
            raise ValueError("Messages list cannot be empty")

        effective_model = self.default_model

        logger.debug(
            f"generate_chat_completion called with {len(messages)} messages, temperature: {temperature}, max_tokens: {max_tokens}, stream: {stream}, model: {effective_model}"
        )

        # Log message details for debugging
        # for i, msg in enumerate(messages):
        #     role = msg.get("role", "unknown")
        #     content_length = len(msg.get("content", ""))
        # logger.debug(f"Message {i}: role={role}, content_length={content_length}")

        start_time = time.perf_counter()

        # Prepare request parameters
        request_params = {
            "model": effective_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
            **kwargs,  # Pass through other kwargs first
        }

        # Check for response_format for JSON mode (OpenAI specific)
        # This assumes kwargs might contain response_format, which we pop or use.
        response_format_arg = kwargs.get(
            "response_format"
        )  # Get from kwargs, don't pop yet if it's also in **kwargs
        if (
            isinstance(response_format_arg, dict)
            and response_format_arg.get("type") == "json_object"
        ):
            # Ensure this is a valid parameter for the OpenAI SDK version being used.
            # For recent versions, client.chat.completions.create supports response_format.
            # We add it here explicitly; if it was already in kwargs, it might be duplicated
            # or overridden depending on Python's dict merging behavior, so it's better to handle it.
            # To avoid duplication if it's already in kwargs, we can pop it from kwargs if we add it here.
            # However, if it's already in kwargs, it would be passed by **kwargs anyway.
            # Let's assume for now that if provided, it's meant for this.
            # A cleaner way might be to have response_format as an explicit param in the interface and client.
            request_params["response_format"] = response_format_arg
            logger.info(
                f"OpenAI client: JSON mode requested for model {effective_model}."
            )

        # logger.debug(f"OpenAI request parameters: {request_params}")

        try:
            logger.debug(
                f"Making OpenAI chat completions API call with model: {effective_model}"
            )

            response_data = await self._client.chat.completions.create(**request_params)

            if stream:
                chunk_count = 0
                total_content_length = 0

                async def generator():
                    nonlocal chunk_count, total_content_length
                    try:
                        logger.debug("Starting streaming chat completion")
                        async for chunk in response_data:
                            chunk_count += 1
                            chunk_dict = chunk.dict()

                            # Log chunk details for debugging
                            if (
                                chunk_count <= 5 or chunk_count % 10 == 0
                            ):  # Log first 5 chunks and every 10th chunk
                                logger.debug(
                                    f"OpenAI stream chunk {chunk_count}: {chunk_dict}"
                                )

                            # Track content length
                            if chunk_dict.get("choices") and chunk_dict["choices"][
                                0
                            ].get("delta", {}).get("content"):
                                content = chunk_dict["choices"][0]["delta"]["content"]
                                total_content_length += len(content)

                            yield chunk_dict
                    finally:
                        end_time = time.perf_counter()
                        duration = end_time - start_time
                        logger.info(
                            f"OpenAI generate_chat_completion (stream) for model {effective_model} completed in {duration:.4f}s. "
                            f"Processed {chunk_count} chunks, total content: {total_content_length} chars"
                        )
                        if duration > 60:
                            logger.warning(
                                f"Very slow streaming response: {duration:.4f}s"
                            )

                return generator()
            else:
                response_dict = response_data.dict()

                # Log response details
                if response_dict.get("choices"):
                    content = (
                        response_dict["choices"][0]
                        .get("message", {})
                        .get("content", "")
                    )
                    content_length = len(content) if content else 0
                    logger.debug(
                        f"Successfully got chat completion response, content length: {content_length}"
                    )
                else:
                    logger.warning(
                        "No choices found in OpenAI chat completion response"
                    )

                end_time = time.perf_counter()
                duration = end_time - start_time

                # Performance and success logging
                logger.info(
                    f"OpenAI generate_chat_completion (non-stream) for model {effective_model} completed successfully in {duration:.4f}s. "
                    f"Input: {len(messages)} messages, output: {content_length if 'content_length' in locals() else 'unknown'} chars"
                )

                if duration > 30:
                    logger.warning(f"Slow chat completion response: {duration:.4f}s")

                return response_dict

        except OpenAIError as e:
            end_time = time.perf_counter()
            duration = end_time - start_time

            # Enhanced error logging for OpenAI specific errors
            error_type = type(e).__name__
            logger.error(
                f"OpenAI API error during chat completion for model {effective_model} after {duration:.4f}s: "
                f"{error_type}: {e}",
                exc_info=True,
            )

            # Log additional context for debugging
            logger.error(
                f"Failed chat request context - messages: {len(messages)}, temperature: {temperature}, max_tokens: {max_tokens}, stream: {stream}"
            )

            raise
        except Exception as e:
            end_time = time.perf_counter()
            duration = end_time - start_time

            # Enhanced error logging for unexpected errors
            error_type = type(e).__name__
            logger.error(
                f"Unexpected error during OpenAI chat completion for model {effective_model} after {duration:.4f}s: "
                f"{error_type}: {e}",
                exc_info=True,
            )

            # Log additional context for debugging
            logger.error(
                f"Failed chat request context - messages: {len(messages)}, temperature: {temperature}, max_tokens: {max_tokens}, stream: {stream}"
            )

            raise

    async def close(self):
        logger.info("Closing OpenAI client.")
        try:
            await self._client.close()
            logger.info("OpenAI client closed successfully.")
        except Exception as e:
            logger.error(f"Error closing OpenAI client: {e}", exc_info=True)
            raise
