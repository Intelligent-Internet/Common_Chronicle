import json
import time
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from app.services.llm_interface import LLMInterface
from app.utils.logger import setup_logger

logger = setup_logger("ollama_client")


class OllamaClient(LLMInterface):
    """
    LLM Client implementation for a local Ollama API.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        default_model: str = "llama3:instruct",
        request_timeout: float = 120.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.request_timeout = request_timeout

        logger.debug(
            f"Initializing Ollama client with base_url: {self.base_url}, model: {default_model}, timeout: {request_timeout}s"
        )

        try:
            self._client = httpx.AsyncClient(
                base_url=self.base_url, timeout=self.request_timeout
            )
            logger.info(
                f"Ollama client initialized successfully. Base URL: {self.base_url}, Default Model: {self.default_model}, Timeout: {self.request_timeout}s"
            )
        except Exception as e:
            logger.error(f"Failed to initialize Ollama client: {e}", exc_info=True)
            raise

    async def _make_request(
        self, endpoint: str, payload: dict[str, Any], stream: bool = False
    ) -> dict[str, Any] | AsyncGenerator[dict[str, Any], None]:
        start_time = time.perf_counter()
        model_name = payload.get("model", "unknown_model")

        logger.debug(
            f"Making Ollama request to {endpoint} with model {model_name}, stream: {stream}"
        )
        logger.debug(f"Request payload: {payload}")

        try:
            if stream:
                chunk_count = 0
                total_response_size = 0

                async def stream_generator():
                    nonlocal chunk_count, total_response_size
                    try:
                        logger.debug(f"Starting streaming request to {endpoint}")
                        async with self._client.stream(
                            "POST", endpoint, json=payload
                        ) as response:
                            if response.status_code != 200:
                                error_content = await response.aread()
                                error_text = error_content.decode()
                                logger.error(
                                    f"Ollama API error ({response.status_code}) at {endpoint} for model {model_name}: {error_text}"
                                )
                                response.raise_for_status()  # Will raise an HTTPStatusError

                            async for line in response.aiter_lines():
                                if line:
                                    chunk_count += 1
                                    total_response_size += len(line)

                                    # Log chunk details for debugging (first few chunks and every 10th chunk)
                                    if chunk_count <= 3 or chunk_count % 10 == 0:
                                        logger.debug(
                                            f"Ollama stream chunk {chunk_count} for model {model_name}: {line[:200]}..."
                                        )

                                    try:
                                        chunk = json.loads(line)
                                        yield chunk
                                    except json.JSONDecodeError as e:
                                        logger.warning(
                                            f"Ollama stream for model {model_name}: could not decode JSON line {chunk_count}: {line[:100]}... Error: {e}"
                                        )
                    finally:
                        end_time = time.perf_counter()
                        duration = end_time - start_time
                        logger.info(
                            f"Ollama _make_request (stream) for {endpoint} with model {model_name} completed in {duration:.4f}s. "
                            f"Processed {chunk_count} chunks, total size: {total_response_size} bytes"
                        )
                        if duration > 60:
                            logger.warning(
                                f"Very slow Ollama streaming response: {duration:.4f}s"
                            )

                return stream_generator()
            else:
                logger.debug(f"Making non-streaming request to {endpoint}")
                response = await self._client.post(endpoint, json=payload)

                if response.status_code != 200:
                    error_text = response.text
                    logger.error(
                        f"Ollama API error ({response.status_code}) at {endpoint} for model {model_name}: {error_text}"
                    )
                    response.raise_for_status()

                response_json = response.json()
                response_size = len(response.content)

                end_time = time.perf_counter()
                duration = end_time - start_time

                logger.info(
                    f"Ollama _make_request (non-stream) for {endpoint} with model {model_name} completed successfully in {duration:.4f}s. "
                    f"Response size: {response_size} bytes"
                )

                if duration > 30:
                    logger.warning(f"Slow Ollama response: {duration:.4f}s")

                logger.debug(f"Ollama response for {endpoint}: {response_json}")

                return response_json

        except httpx.HTTPStatusError as http_status_error:
            end_time = time.perf_counter()
            duration = end_time - start_time

            error_text = ""
            if hasattr(http_status_error, "response") and http_status_error.response:
                try:
                    error_text = http_status_error.response.text
                except Exception:
                    error_text = "Could not read error response"

            logger.error(
                f"Ollama HTTP Status Error for model {model_name} at {endpoint} after {duration:.4f}s: "
                f"Status {http_status_error.response.status_code if http_status_error.response else 'unknown'} - {error_text}",
                exc_info=True,
            )
            raise http_status_error
        except httpx.RequestError as request_error:
            end_time = time.perf_counter()
            duration = end_time - start_time
            logger.error(
                f"Ollama Request Error for model {model_name} at {endpoint} after {duration:.4f}s: {request_error}",
                exc_info=True,
            )
            raise request_error
        except Exception as other_error:
            end_time = time.perf_counter()
            duration = end_time - start_time
            logger.error(
                f"Unexpected error in Ollama client for model {model_name} at {endpoint} after {duration:.4f}s: {other_error}",
                exc_info=True,
            )
            raise other_error

    async def generate_text(
        self,
        prompt: str,
        temperature: float | None = None,  # Ollama uses "options": {"temperature": ...}
        max_tokens: int | None = None,  # Ollama uses "options": {"num_predict": ...}
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

        payload = {
            "model": effective_model,
            "prompt": prompt,
            "stream": False,  # For generate_text, we want the full response
            "options": {},
        }
        if temperature is not None:
            payload["options"]["temperature"] = temperature
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens

        # Merge other kwargs into options if they are valid Ollama options
        # This requires knowing which kwargs are meant for Ollama options
        valid_ollama_options = [
            "mirostat",
            "mirostat_eta",
            "mirostat_tau",
            "num_ctx",
            "repeat_last_n",
            "repeat_penalty",
            "seed",
            "stop",
            "tfs_z",
            "top_k",
            "top_p",
        ]
        for k, v in kwargs.items():
            if k in valid_ollama_options:
                payload["options"][k] = v
                logger.debug(f"Added Ollama option: {k}={v}")

        logger.debug(f"Final Ollama generate payload: {payload}")

        response_data = await self._make_request("/api/generate", payload, stream=False)

        # Ollama /api/generate response structure: {"model": ..., "response": "...", "done": true, ...}
        result_text = response_data.get("response", "").strip()

        if not result_text:
            logger.warning(
                f"Empty response from Ollama generate for model {effective_model}"
            )
        else:
            logger.debug(
                f"Successfully got Ollama generate response, length: {len(result_text)}"
            )

        # Log additional response metadata if available
        if "done" in response_data:
            logger.debug(f"Ollama generate done status: {response_data['done']}")
        if "total_duration" in response_data:
            total_duration_ns = response_data["total_duration"]
            total_duration_s = total_duration_ns / 1_000_000_000
            logger.debug(f"Ollama generate total duration: {total_duration_s:.4f}s")

        return result_text

    async def generate_chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
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

        payload = {
            "model": effective_model,
            "messages": messages,  # Ollama /api/chat expects messages in OpenAI format
            "stream": stream,
            "options": {},
        }
        if temperature is not None:
            payload["options"]["temperature"] = temperature
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens

        valid_ollama_options = [
            "mirostat",
            "mirostat_eta",
            "mirostat_tau",
            "num_ctx",
            "repeat_last_n",
            "repeat_penalty",
            "seed",
            "stop",
            "tfs_z",
            "top_k",
            "top_p",
        ]
        for k, v in kwargs.items():
            if k in valid_ollama_options:
                payload["options"][k] = v
                logger.debug(f"Added Ollama chat option: {k}={v}")

        logger.debug(f"Final Ollama chat payload: {payload}")

        response_data_or_stream = await self._make_request(
            "/api/chat", payload, stream=stream
        )

        if stream:
            chunk_count = 0
            total_content_length = 0

            async def adapted_stream_generator():
                nonlocal chunk_count, total_content_length
                try:
                    logger.debug("Starting Ollama chat streaming")
                    async for chunk in response_data_or_stream:
                        chunk_count += 1

                        # Log chunk details for debugging (first few chunks and every 10th chunk)
                        if chunk_count <= 3 or chunk_count % 10 == 0:
                            logger.debug(
                                f"Ollama chat stream chunk {chunk_count}: {chunk}"
                            )

                        # Adapt Ollama chat stream chunk to interface
                        # Chunk: { "model": "...", "message": { "role": "assistant", "content": "..."}, "done": false }
                        # We need to yield something like { "choices": [{"delta": {"content": "..."}}], ... }
                        # Or a simpler format as defined by the interface.
                        # For now, returning a simplified chunk. `is_final` indicates if it's the last part of the message.
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            total_content_length += len(content)

                        yield {
                            "content": content,
                            "is_final": chunk.get("done", False),
                        }

                        # Log completion status
                        if chunk.get("done"):
                            logger.debug(
                                f"Ollama chat stream completed at chunk {chunk_count}"
                            )
                finally:
                    logger.info(
                        f"Ollama chat streaming completed. Processed {chunk_count} chunks, total content: {total_content_length} chars"
                    )

            return adapted_stream_generator()
        else:
            # Adapt Ollama chat response to interface
            # Response: { "model": "...", "message": { "role": "assistant", "content": "..."}, "done": true, ...}
            # Interface expects: { "choices": [{"message": {"role": "assistant", "content": "..."}}], ...}

            message_content = response_data_or_stream.get(
                "message", {"role": "assistant", "content": ""}
            )
            content = message_content.get("content", "")

            if not content:
                logger.warning(
                    f"Empty content in Ollama chat response for model {effective_model}"
                )
            else:
                logger.debug(
                    f"Successfully got Ollama chat response, content length: {len(content)}"
                )

            # Log additional response metadata if available
            if "done" in response_data_or_stream:
                logger.debug(
                    f"Ollama chat done status: {response_data_or_stream['done']}"
                )
            if "total_duration" in response_data_or_stream:
                total_duration_ns = response_data_or_stream["total_duration"]
                total_duration_s = total_duration_ns / 1_000_000_000
                logger.debug(f"Ollama chat total duration: {total_duration_s:.4f}s")

            # Log token usage if available
            prompt_eval_count = response_data_or_stream.get("prompt_eval_count", 0)
            eval_count = response_data_or_stream.get("eval_count", 0)
            total_tokens = prompt_eval_count + eval_count

            if prompt_eval_count or eval_count:
                logger.debug(
                    f"Ollama chat token usage - prompt: {prompt_eval_count}, completion: {eval_count}, total: {total_tokens}"
                )

            return {
                "choices": [{"message": message_content}],
                "usage": {  # Placeholder for usage if available (Ollama provides total_duration, etc.)
                    "prompt_tokens": prompt_eval_count,
                    "completion_tokens": eval_count,
                    "total_tokens": total_tokens,
                },
            }

    async def close(self):
        logger.info("Closing Ollama client.")
        try:
            await self._client.aclose()
            logger.info("Ollama client closed successfully.")
        except Exception as e:
            logger.error(f"Error closing Ollama client: {e}", exc_info=True)
            raise
