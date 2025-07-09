import time
from collections.abc import AsyncGenerator
from typing import Any

from google import genai
from google.genai import types

from app.config import settings
from app.services.llm_interface import LLMInterface
from app.utils.logger import setup_logger

logger = setup_logger("gemini_client")


class GeminiClient(LLMInterface):
    """
    LLM Client implementation for Google Gemini API.
    """

    def __init__(
        self, api_key: str, default_model: str = settings.default_gemini_model
    ):
        if not api_key:
            logger.error("Gemini API key is required but not provided")
            raise ValueError("Gemini API key is required.")

        self.api_key = api_key
        self.default_model = default_model

        logger.debug(f"Initializing Gemini client with model: {default_model}")

        try:
            self._client = genai.Client(api_key=self.api_key)
            logger.info(
                f"Gemini client initialized successfully with api_key: {self.api_key[:5]}..., model: {self.default_model}"
            )
        except Exception as e:
            logger.error(f"Failed to configure Gemini SDK: {e}", exc_info=True)
            raise

    async def generate_text(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int | None = 65536,
        **kwargs: Any,
    ) -> str:
        model_name = self.default_model

        # Input validation and logging
        if not prompt or not prompt.strip():
            logger.warning("Empty or whitespace-only prompt provided to generate_text")
            return ""

        prompt_length = len(prompt)
        logger.debug(
            f"generate_text called with prompt length: {prompt_length}, temperature: {temperature}, max_tokens: {max_tokens}"
        )

        if prompt_length > 100000:  # Arbitrary large threshold
            logger.warning(
                f"Very large prompt provided ({prompt_length} chars), this may cause performance issues"
            )

        start_time = time.perf_counter()
        try:
            logger.debug(
                f"Making Gemini API call for text generation with model: {model_name}"
            )

            response = await self._client.aio.models.generate_content(
                model=model_name,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    temperature=temperature, max_output_tokens=max_tokens, **kwargs
                ),
            )

            logger.debug(f"Gemini generate_text raw response object: {response}")
            logger.debug(
                f"Gemini generate_text response.parts: {response.parts if hasattr(response, 'parts') else 'N/A'}"
            )
            logger.debug(
                f"Gemini generate_text response.candidates: {response.candidates if hasattr(response, 'candidates') else 'N/A'}"
            )
            if hasattr(response, "prompt_feedback"):
                logger.debug(
                    f"Gemini generate_text prompt_feedback: {response.prompt_feedback}"
                )

            result_text = response.text

            # Enhanced response processing with detailed logging
            if result_text is None:
                logger.warning(
                    "response.text is None, attempting to reconstruct from parts"
                )

                if not response.candidates:
                    logger.error(
                        "No candidates found in response, cannot reconstruct text"
                    )
                    result_text = ""
                else:
                    try:
                        candidate = response.candidates[0]
                        if hasattr(candidate, "finish_reason"):
                            finish_reason = candidate.finish_reason
                            logger.debug(
                                f"Gemini generate_text candidate.finish_reason: {finish_reason}"
                            )

                            # Log specific finish reasons that might indicate issues
                            if finish_reason == "MAX_TOKENS":
                                logger.warning(
                                    f"Response truncated due to max_tokens limit ({max_tokens})"
                                )
                            elif finish_reason == "SAFETY":
                                logger.warning("Response blocked due to safety filters")
                            elif finish_reason == "RECITATION":
                                logger.warning(
                                    "Response blocked due to recitation concerns"
                                )

                        if candidate.content and candidate.content.parts:
                            parts_with_text = [
                                part.text
                                for part in candidate.content.parts
                                if hasattr(part, "text") and part.text is not None
                            ]
                            result_text = "".join(parts_with_text)
                            logger.debug(
                                f"Reconstructed text from {len(parts_with_text)} parts, total length: {len(result_text)}"
                            )
                        else:
                            logger.warning(
                                "No parts found in candidate content to reconstruct text"
                            )
                            result_text = ""
                    except IndexError:
                        logger.error("No candidates found in response")
                        result_text = ""
                    except Exception as e:
                        logger.error(
                            f"Error reconstructing text from parts: {e}", exc_info=True
                        )
                        result_text = ""
            else:
                logger.debug(
                    f"Successfully got response text, length: {len(result_text)}"
                )

            end_time = time.perf_counter()
            duration = end_time - start_time

            # Performance logging
            logger.info(
                f"Gemini generate_text completed successfully for model {model_name} in {duration:.4f}s, "
                f"input: {prompt_length} chars, output: {len(result_text)} chars"
            )

            # Log performance warnings
            if duration > 30:
                logger.warning(f"Slow API response: {duration:.4f}s for generate_text")

            return result_text

        except Exception as e:
            end_time = time.perf_counter()
            duration = end_time - start_time

            # Enhanced error logging
            error_type = type(e).__name__
            logger.error(
                f"Gemini API error during text generation for model {model_name} after {duration:.4f}s: "
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
        max_tokens: int | None = 65536,
        stream: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any] | AsyncGenerator[dict[str, Any], None]:
        model_name = self.default_model

        # Input validation and logging
        if not messages:
            logger.error("Empty messages list provided to generate_chat_completion")
            raise ValueError("Messages list cannot be empty")

        logger.debug(
            f"generate_chat_completion called with {len(messages)} messages, temperature: {temperature}, max_tokens: {max_tokens}, stream: {stream}"
        )

        # Log message details for debugging
        # for i, msg in enumerate(messages):
        #     role = msg.get("role", "unknown")
        # content_length = len(msg.get("content", ""))
        # logger.debug(f"Message {i}: role={role}, content_length={content_length}")

        start_time = time.perf_counter()

        response_format = kwargs.pop("response_format", None)
        if response_format:
            logger.debug(f"Response format requested: {response_format}")

        # Explicitly construct generation_config_params with only known and supported keys
        generation_config_params: dict[str, Any] = {}
        if temperature is not None:
            generation_config_params["temperature"] = temperature
        if max_tokens is not None:
            generation_config_params["max_output_tokens"] = max_tokens
        if response_format and response_format.get("type") == "json_object":
            generation_config_params["response_mime_type"] = "application/json"
            logger.info("JSON response format enabled for Gemini")

        logger.debug(f"Generation config params: {generation_config_params}")

        # Convert messages to Gemini format - MOVED HERE, AFTER kwargs processing for GenerationConfig
        formatted_history = []
        system_prompt_parts = []

        for i, msg in enumerate(messages):
            logger.debug(f"Processing message {i}: {msg}")
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                # Accumulate system messages if they appear at the beginning
                # or handle them according to specific logic if they appear elsewhere.
                # For Gemini, system messages are not directly part of the chat history turns.
                # We can prepend their content to the first user message if appropriate.
                logger.debug(
                    f"System message encountered: '{content[:100]}...'. It will be handled separately or prepended."
                )
                system_prompt_parts.append(content)
                continue  # Do not add system messages directly to formatted_history for Gemini

            if role == "assistant":
                role = "model"  # Convert to Gemini's expected role

            # If there were preceding system prompts and this is the first non-system message (and it's a user message),
            # prepend the system prompts to its content.
            if (
                system_prompt_parts
                and role == "user"
                and not any(item["role"] == "user" for item in formatted_history)
            ):
                full_content = "\n".join(system_prompt_parts) + "\n\n" + content
                formatted_history.append(
                    {"role": role, "parts": [{"text": full_content}]}
                )
                logger.debug(
                    f"Prepended {len(system_prompt_parts)} system messages to first user message"
                )
                system_prompt_parts = []  # Clear accumulated system prompts
            else:
                formatted_history.append({"role": role, "parts": [{"text": content}]})

        # If there are leftover system prompts (e.g., messages only contained system prompts, or no user prompt followed them to attach to)
        # this is an invalid state for Gemini as a chat must contain user/model turns.
        # The existing validation below should catch if formatted_history is empty or starts incorrectly.
        # If system_prompt_parts is not empty here and formatted_history is also populated,
        # it implies system messages were at the end or not followed by a user message to prepend to.
        # These are effectively ignored by not being added to formatted_history.
        if system_prompt_parts and not formatted_history:
            logger.error(
                "Cannot start a Gemini chat with only system messages. A user message is required."
            )
            raise ValueError(
                "Cannot start a Gemini chat with only system messages. A user message is required."
            )

        # Validate history
        if not formatted_history:
            logger.error("Message list resulted in empty formatted history")
            raise ValueError("Message list cannot be empty.")

        history_for_create = formatted_history[:-1]
        message_to_send = formatted_history[-1]

        logger.debug(
            f"Chat history split: {len(history_for_create)} messages for history, 1 message to send"
        )

        if (
            not history_for_create
        ):  # If history for create is empty, the message_to_send is the start of the conversation
            if message_to_send["role"] != "user":
                logger.error(
                    f"Conversation must start with user turn, but got: {message_to_send['role']}"
                )
                raise ValueError(
                    f"Conversation history must start with a user turn. First message was: {message_to_send['role']}"
                )
        else:  # If history_for_create is not empty, its first turn must be from the user
            if history_for_create[0]["role"] != "user":
                logger.error(
                    f"History must start with user turn, but got: {history_for_create[0]['role']}"
                )
                raise ValueError(
                    f"Conversation history must start with a user turn. First message in provided history was: {history_for_create[0]['role']}"
                )

        # Ensure try-except block is correctly placed
        try:
            if stream:
                logger.debug("Creating streaming chat session")
                chat_session = self._client.aio.chats.create(
                    model=model_name,
                    history=history_for_create,
                    config=generation_config_params,
                )

                async def generator():
                    chunk_count = 0
                    total_content_length = 0
                    try:
                        logger.debug("Starting streaming message send")
                        stream_response = await chat_session.send_message_stream(
                            message=message_to_send["parts"][0]["text"],
                            config=generation_config_params,
                        )
                        async for chunk in stream_response:
                            chunk_count += 1
                            logger.debug(
                                f"Gemini stream chunk {chunk_count} object: {chunk}"
                            )
                            logger.debug(
                                f"Gemini stream chunk.parts: {chunk.parts if hasattr(chunk, 'parts') else 'N/A'}"
                            )
                            logger.debug(
                                f"Gemini stream chunk.candidates: {chunk.candidates if hasattr(chunk, 'candidates') else 'N/A'}"
                            )
                            if hasattr(chunk, "prompt_feedback"):
                                logger.debug(
                                    f"Gemini stream chunk prompt_feedback: {chunk.prompt_feedback}"
                                )

                            chunk_text_content = chunk.text
                            if chunk_text_content is None and chunk.candidates:
                                logger.warning(
                                    f"chunk.text is None for chunk {chunk_count}, attempting to reconstruct from chunk parts."
                                )
                                try:
                                    candidate = chunk.candidates[0]
                                    if hasattr(candidate, "finish_reason"):
                                        finish_reason = candidate.finish_reason
                                        logger.debug(
                                            f"Gemini stream chunk {chunk_count} candidate.finish_reason: {finish_reason}"
                                        )
                                        if finish_reason == "MAX_TOKENS":
                                            logger.warning(
                                                f"Stream chunk {chunk_count} truncated due to max_tokens limit"
                                            )
                                        elif finish_reason == "SAFETY":
                                            logger.warning(
                                                f"Stream chunk {chunk_count} blocked due to safety filters"
                                            )
                                    if candidate.content and candidate.content.parts:
                                        chunk_text_content = "".join(
                                            part.text
                                            for part in candidate.content.parts
                                            if hasattr(part, "text")
                                            and part.text is not None
                                        )
                                        logger.debug(
                                            f"Reconstructed chunk {chunk_count} text, length: {len(chunk_text_content)}"
                                        )
                                    else:
                                        logger.warning(
                                            f"No parts found in chunk {chunk_count} candidate content to reconstruct text."
                                        )
                                except IndexError:
                                    logger.warning(
                                        f"No candidates found in chunk {chunk_count}."
                                    )
                                except Exception as e:
                                    logger.error(
                                        f"Error reconstructing text from chunk {chunk_count} parts: {e}",
                                        exc_info=True,
                                    )

                            # Only yield if there is content
                            if chunk_text_content is not None:
                                total_content_length += len(chunk_text_content)
                                yield {
                                    "content": chunk_text_content,
                                    "is_final": True,  # This might need adjustment based on actual finish_reason
                                }  # Assuming is_final logic needs to be handled by consumer
                            elif (
                                chunk.candidates
                                and hasattr(chunk.candidates[0], "finish_reason")
                                and chunk.candidates[0].finish_reason
                            ):
                                # If content is None, but we have a finish reason, it might be the end of stream signal
                                logger.debug(
                                    f"Stream chunk {chunk_count} has no content, but finish_reason: {chunk.candidates[0].finish_reason}. Not yielding."
                                )
                    finally:
                        end_time = time.perf_counter()
                        duration = end_time - start_time
                        logger.info(
                            f"Gemini generate_chat_completion (stream) for model {model_name} completed in {duration:.4f}s. "
                            f"Processed {chunk_count} chunks, total content: {total_content_length} chars"
                        )
                        if duration > 60:
                            logger.warning(
                                f"Very slow streaming response: {duration:.4f}s"
                            )

                return generator()
            else:
                logger.debug("Creating non-streaming chat session")
                chat_session = self._client.aio.chats.create(
                    model=model_name,
                    history=history_for_create,
                    config=generation_config_params,
                )

                logger.debug("Sending message to chat session")
                response = await chat_session.send_message(
                    message=message_to_send["parts"][0]["text"],
                    config=generation_config_params,
                )
                logger.debug(
                    f"Gemini chat (non-stream) raw response object: {response}"
                )
                logger.debug(
                    f"Gemini chat (non-stream) response.parts: {response.parts if hasattr(response, 'parts') else 'N/A'}"
                )
                logger.debug(
                    f"Gemini chat (non-stream) response.candidates: {response.candidates if hasattr(response, 'candidates') else 'N/A'}"
                )
                if hasattr(response, "prompt_feedback"):
                    logger.debug(
                        f"Gemini chat (non-stream) prompt_feedback: {response.prompt_feedback}"
                    )

                response_text_content = response.text
                if response_text_content is None and response.candidates:
                    logger.warning(
                        "Chat response.text is None, attempting to reconstruct from parts."
                    )
                    try:
                        candidate = response.candidates[0]
                        if hasattr(candidate, "finish_reason"):
                            finish_reason = candidate.finish_reason
                            logger.debug(
                                f"Gemini chat (non-stream) candidate.finish_reason: {finish_reason}"
                            )
                            if finish_reason == "MAX_TOKENS":
                                logger.warning(
                                    f"Chat response truncated due to max_tokens limit ({max_tokens})"
                                )
                            elif finish_reason == "SAFETY":
                                logger.warning(
                                    "Chat response blocked due to safety filters"
                                )
                            elif finish_reason == "RECITATION":
                                logger.warning(
                                    "Chat response blocked due to recitation concerns"
                                )
                        if candidate.content and candidate.content.parts:
                            response_text_content = "".join(
                                part.text
                                for part in candidate.content.parts
                                if hasattr(part, "text") and part.text is not None
                            )
                            logger.debug(
                                f"Reconstructed chat response text, length: {len(response_text_content)}"
                            )
                        else:
                            logger.warning(
                                "No parts found in chat candidate content to reconstruct text."
                            )
                    except IndexError:
                        logger.error("No candidates found in chat response.")
                        response_text_content = ""
                    except Exception as e:
                        logger.error(
                            f"Error reconstructing text from chat parts: {e}",
                            exc_info=True,
                        )
                        response_text_content = ""
                else:
                    logger.debug(
                        f"Successfully got chat response text, length: {len(response_text_content) if response_text_content else 0}"
                    )

                end_time = time.perf_counter()
                duration = end_time - start_time

                # Performance and success logging
                logger.info(
                    f"Gemini generate_chat_completion (non-stream) for model {model_name} completed successfully in {duration:.4f}s. "
                    f"Input: {len(messages)} messages, output: {len(response_text_content) if response_text_content else 0} chars"
                )

                if duration > 30:
                    logger.warning(f"Slow chat completion response: {duration:.4f}s")

                return {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": response_text_content,
                            }
                        }
                    ],
                    "usage": {},
                }
        except Exception as e:
            end_time = time.perf_counter()
            duration = end_time - start_time

            # Enhanced error logging
            error_type = type(e).__name__
            logger.error(
                f"Gemini API error during chat generation for model {model_name} after {duration:.4f}s: "
                f"{error_type}: {e}",
                exc_info=True,
            )

            # Log additional context for debugging
            logger.error(
                f"Failed chat request context - messages: {len(messages)}, temperature: {temperature}, max_tokens: {max_tokens}, stream: {stream}"
            )

            raise e

    async def close(self):
        logger.info("Gemini client does not require explicit closing.")
        logger.debug("Gemini client close() called - no cleanup needed")
