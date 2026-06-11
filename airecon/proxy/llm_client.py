"""OpenAI-compatible LLM client for AIRecon.

Speaks the OpenAI Chat Completions API (/v1/chat/completions) via httpx.
Works with any OpenAI-compatible provider:
  - OpenAI (api.openai.com)
  - OpenRouter, Together AI, Groq, etc.
  - Local: Ollama (/v1 compat), vLLM, llama.cpp server, LocalAI
  - Self-hosted: LiteLLM proxy, text-generation-webui, etc.

Chunk format is normalized to the internal AIRecon format so consumers
(loop_tool_cycle, loop_context, etc.) don't need changes.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import threading
import time
from typing import Any, AsyncIterator, Callable, Dict

import httpx

from .config import get_config
from .memory import get_memory_manager

logger = logging.getLogger("airecon.llm")

_CONTEXT_RESET_THRESHOLD = 65536

_PERMANENT_LLM_ERRORS: frozenset[str] = frozenset(
    [
        "model not found",
        "model is not loaded",
        "unsupported model",
        "context length exceeded",
        "context_length_exceeded",
        "maximum context length",
        "out of memory",
        "no gpu",
        "invalid_api_key",
        "insufficient_quota",
    ]
)


class LLMClient:
    """OpenAI-compatible chat completions client.

    Public interface matches the old OllamaClient so existing call sites
    (self.ollama.chat_stream, self.ollama.complete, etc.) work unchanged.
    """

    _global_semaphore: asyncio.Semaphore | None = None
    _httpx_client: httpx.AsyncClient | None = None
    _initialized: bool = False
    _init_lock: asyncio.Lock | None = None
    _semaphore_init_lock = threading.Lock()

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        cfg = get_config()
        host = (base_url or cfg.llm_base_url).rstrip("/")
        if not host.endswith("/v1"):
            host = f"{host}/v1"
        self._host = host
        self.model = model or cfg.llm_model
        self._api_key = api_key if api_key is not None else cfg.llm_api_key

        self._supports_thinking = cfg.llm_supports_thinking
        self._supports_native_tools = cfg.llm_supports_native_tools

        if not self._supports_thinking and self._supports_native_tools:
            logger.warning(
                "native_tools=True requires thinking=True (AIRecon uses reasoning "
                "traces to validate tool calls). Forcing native_tools=False."
            )
            self._supports_native_tools = False

        logger.info(
            "Initializing LLM httpx client for host: %s, model: %s",
            host,
            self.model,
        )

        if LLMClient._global_semaphore is None:
            with LLMClient._semaphore_init_lock:
                if LLMClient._global_semaphore is None:
                    max_concurrent = cfg.llm_max_concurrent_requests
                    LLMClient._global_semaphore = asyncio.Semaphore(max_concurrent)
        self._request_semaphore = LLMClient._global_semaphore

    async def _async_init(self) -> None:
        if LLMClient._initialized:
            return

        if LLMClient._init_lock is None:
            LLMClient._init_lock = asyncio.Lock()

        async with LLMClient._init_lock:
            if LLMClient._initialized:
                return

            logger.info(
                "Initializing LLM httpx client (async init) for model: %s",
                self.model,
            )
            logger.info(
                "Model capabilities: thinking=%s, native_tools=%s",
                self._supports_thinking,
                self._supports_native_tools,
            )

            if LLMClient._httpx_client is None:
                _cfg = get_config()
                _http_timeout = _cfg.llm_timeout
                headers: dict[str, str] = {"Content-Type": "application/json"}
                if self._api_key:
                    headers["Authorization"] = f"Bearer {self._api_key}"
                LLMClient._httpx_client = httpx.AsyncClient(
                    timeout=httpx.Timeout(
                        _http_timeout, connect=10.0, read=_http_timeout, write=10.0
                    ),
                    headers=headers,
                )
                LLMClient._initialized = True
            logger.info("LLM httpx client initialized")

    async def _run_http_request(
        self,
        method: str,
        endpoint: str,
        json_data: dict[str, Any] | None = None,
        stream: bool = False,
        timeout: float | None = None,
    ) -> httpx.Response | None:
        async with self._request_semaphore:
            client = LLMClient._httpx_client
            if client is None:
                raise RuntimeError("HTTP client not initialized")

            url = f"{self._host}{endpoint}"

            if timeout is not None:
                timeout_obj = httpx.Timeout(
                    timeout, connect=10.0, read=timeout, write=10.0
                )
            else:
                _cfg = get_config()
                _http_timeout = _cfg.llm_timeout
                timeout_obj = httpx.Timeout(
                    _http_timeout, connect=10.0, read=_http_timeout, write=10.0
                )

            if stream:
                raise RuntimeError(
                    "stream=True not supported in _run_http_request. "
                    "Use _run_http_stream() for streaming requests."
                )

            resp = await client.request(
                method=method,
                url=url,
                json=json_data,
                timeout=timeout_obj,
            )
            resp.raise_for_status()
            return resp

    # ── Context reset (non-streaming minimal chat) ──────────────────────

    async def reset_context(self, system_prompt: str | None = None) -> bool:
        cfg = get_config()
        timeout = cfg.llm_timeout
        self._last_reset_error = ""
        self._last_reset_status = None

        try:
            messages: list[dict[str, Any]] = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})

            await self._run_http_request(
                "POST",
                "/chat/completions",
                json_data={
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": 100,
                    "stream": False,
                },
                timeout=timeout,
            )
            logger.info("LLM context reset successful")
            return True
        except asyncio.TimeoutError:
            logger.error("LLM context reset timeout after %.0fs", timeout)
            self._last_reset_error = "timeout"
            return False
        except httpx.HTTPError as e:
            self._last_reset_error = str(e)
            if getattr(e, "response", None) is not None:
                self._last_reset_status = e.response.status_code
            logger.error("LLM context reset failed: %s", e)
            return False

    # ── Capability detection ────────────────────────────────────────────

    @property
    def supports_thinking(self) -> bool:
        return self._supports_thinking

    @property
    def supports_native_tools(self) -> bool:
        return self._supports_native_tools

    # ── Lifecycle ───────────────────────────────────────────────────────

    async def close(self) -> None:
        client = LLMClient._httpx_client
        if client is not None:
            await client.aclose()

    async def unload_model(self) -> None:
        """No-op for OpenAI-compatible providers (stateless API)."""
        logger.info("unload_model: no-op for OpenAI-compatible provider")

    async def health_check(self) -> bool:
        try:
            client = LLMClient._httpx_client
            if client is None:
                return False
            resp = await client.get(
                f"{self._host}/models",
                timeout=httpx.Timeout(10.0),
            )
            return resp.status_code == 200
        except Exception:
            return False

    # ── Non-streaming completion ────────────────────────────────────────

    async def complete(
        self,
        messages: list[dict[str, Any]],
        max_retries: int = 3,
        options: dict[str, Any] | None = None,
        operation: str = "compression",
    ) -> str:
        return await self._complete_impl(messages, max_retries, options, operation)

    async def _complete_impl(
        self,
        messages: list[dict[str, Any]],
        max_retries: int = 3,
        options: dict[str, Any] | None = None,
        operation: str = "compression",
    ) -> str:
        max_retries = max(0, max_retries)
        request_started = time.monotonic()

        try:
            for attempt in range(max_retries + 1):
                try:
                    payload = self._build_payload(messages, stream=False, options=options)
                    timeout = self._get_dynamic_timeout(operation)

                    resp = await self._run_http_request(
                        "POST",
                        "/chat/completions",
                        json_data=payload,
                        timeout=timeout,
                    )
                    if resp is None:
                        logger.warning(
                            "LLM returned None response. Attempt %d/%d",
                            attempt + 1,
                            max_retries + 1,
                        )
                        if attempt < max_retries:
                            await asyncio.sleep(2 ** (attempt + 1))
                            continue
                        raise RuntimeError(
                            "LLM returned None response after all retries"
                        )
                    data = resp.json()

                    content = self._extract_content_from_response(data)
                    if content is None:
                        logger.warning(
                            "LLM returned unexpected response format: %r. Attempt %d/%d",
                            data,
                            attempt + 1,
                            max_retries + 1,
                        )
                        if attempt < max_retries:
                            await asyncio.sleep(2 ** (attempt + 1))
                            continue
                        raise RuntimeError(
                            f"Invalid LLM response format: {type(data)}. "
                            f"Expected dict with choices[0].message.content."
                        )

                    elapsed = time.monotonic() - request_started
                    self._record_response_time(elapsed)
                    self._record_model_performance(
                        operation=operation,
                        response_time_sec=elapsed,
                        success=True,
                        messages=messages,
                        options=options,
                    )
                    return content

                except asyncio.TimeoutError:
                    timeout = self._get_dynamic_timeout(operation)
                    logger.warning(
                        "LLM complete() timeout (%.0fs) for model %s (attempt %d/%d)",
                        timeout,
                        self.model,
                        attempt + 1,
                        max_retries + 1,
                    )
                    if attempt < max_retries:
                        await asyncio.sleep(2 ** (attempt + 1))
                        continue
                    raise RuntimeError(
                        f"LLM timeout after {timeout:.0f}s for model {self.model}"
                    )
                except RuntimeError:
                    raise
                except httpx.HTTPStatusError as e:
                    if 500 <= e.response.status_code < 600 and attempt < max_retries:
                        await asyncio.sleep(15 * (attempt + 1))
                        continue
                    raise
                except httpx.NetworkError:
                    if attempt < max_retries:
                        await asyncio.sleep(2 ** (attempt + 1))
                        continue
                    raise

            raise RuntimeError("Unexpected code path in complete()")
        except Exception:
            elapsed = time.monotonic() - request_started
            self._record_model_performance(
                operation=operation,
                response_time_sec=elapsed,
                success=False,
                messages=messages,
                options=options,
            )
            raise

    # ── Streaming chat ──────────────────────────────────────────────────

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
        think: bool = False,
        max_retries: int = 3,
        operation: str = "chat",
        stop_requested_fn: Callable[[], bool] | None = None,
    ) -> AsyncIterator[Any]:
        async for chunk in self._chat_stream_impl(
            messages,
            tools,
            options,
            think,
            max_retries,
            operation,
            stop_requested_fn,
        ):
            yield chunk

    async def _chat_stream_impl(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
        think: bool = False,
        max_retries: int = 3,
        operation: str = "chat",
        stop_requested_fn: Callable[[], bool] | None = None,
    ) -> AsyncIterator[Any]:
        cfg = get_config()

        payload = self._build_payload(
            messages,
            stream=True,
            tools=tools,
            think=think,
            options=options,
        )

        _STOP_POLL = 2.0
        _overall_timeout = cfg.llm_timeout
        _chunk_timeout = cfg.llm_chunk_timeout
        request_started = time.monotonic()

        try:
            for attempt in range(max_retries + 1):
                _next_fut: asyncio.Future | None = None
                _last_activity_time: float | None = None

                # Tool-call accumulator for streaming
                _tool_calls_acc: dict[int, dict[str, Any]] = {}

                async def _cleanup_next_future() -> None:
                    nonlocal _next_fut
                    if _next_fut is None:
                        return
                    fut = _next_fut
                    _next_fut = None
                    if not fut.done():
                        fut.cancel()
                    with contextlib.suppress(
                        asyncio.CancelledError,
                        StopAsyncIteration,
                        Exception,
                    ):
                        await fut

                try:
                    async with self._request_semaphore:
                        client = LLMClient._httpx_client
                        if client is None:
                            raise RuntimeError("HTTP client not initialized")

                        start_time = asyncio.get_running_loop().time()
                        _last_activity_time = start_time

                        url = f"{self._host}/chat/completions"
                        timeout_obj = httpx.Timeout(_overall_timeout, read=_chunk_timeout)

                        async with client.stream(
                            "POST",
                            url,
                            json=payload,
                            timeout=timeout_obj,
                        ) as resp:
                            resp.raise_for_status()
                            _aiter = resp.aiter_lines()

                            chunk_count = 0
                            elapsed = 0.0
                            done_received = False
                            _usage: dict[str, int] = {}

                            while True:
                                current_time = asyncio.get_running_loop().time()

                                if (current_time - start_time) > _overall_timeout:
                                    raise TimeoutError(
                                        f"LLM overall timeout: request took longer than {_overall_timeout:.0f}s"
                                    )

                                if _last_activity_time is not None:
                                    inactivity_time = current_time - _last_activity_time
                                    if inactivity_time > get_config().llm_timeout:
                                        logger.warning(
                                            "LLM inactivity: %.0fs, cancelling request",
                                            inactivity_time,
                                        )
                                        raise TimeoutError("LLM inactivity timeout")

                                if stop_requested_fn and stop_requested_fn():
                                    await _cleanup_next_future()
                                    return

                                if _next_fut is None:
                                    _next_fut = asyncio.ensure_future(_aiter.__anext__())
                                    _next_fut.add_done_callback(
                                        lambda fut: fut.exception()
                                    )

                                remaining = _chunk_timeout - elapsed
                                wait = (
                                    min(_STOP_POLL, remaining)
                                    if remaining > 0
                                    else _STOP_POLL
                                )

                                try:
                                    if _next_fut is None:
                                        raise RuntimeError(
                                            "LLM stream state error: next future is None"
                                        )
                                    line = await asyncio.wait_for(
                                        asyncio.shield(_next_fut),
                                        timeout=wait,
                                    )
                                except StopAsyncIteration:
                                    _next_fut = None
                                    if _last_activity_time is not None:
                                        _last_activity_time = (
                                            asyncio.get_running_loop().time()
                                        )
                                    break
                                except asyncio.TimeoutError:
                                    elapsed += wait
                                    if elapsed >= _chunk_timeout:
                                        if _next_fut is not None and not _next_fut.done():
                                            _next_fut.cancel()
                                            try:
                                                await _next_fut
                                            except (
                                                StopAsyncIteration,
                                                asyncio.CancelledError,
                                            ):
                                                pass
                                        _next_fut = None
                                        raise TimeoutError(
                                            f"LLM stream timeout: no chunk received for {_chunk_timeout:.0f}s "
                                            f"after {chunk_count} chunks."
                                        )
                                    continue

                                elapsed = 0.0
                                if _last_activity_time is not None:
                                    _last_activity_time = asyncio.get_running_loop().time()
                                _next_fut = None

                                # Skip empty lines and non-data SSE lines
                                if not line or line.startswith(":"):
                                    continue

                                # Strip SSE "data: " prefix
                                if line.startswith("data: "):
                                    line = line[6:]
                                elif line.startswith("data:"):
                                    line = line[5:]

                                # End of stream marker
                                if line.strip() == "[DONE]":
                                    done_received = True
                                    break

                                try:
                                    raw_chunk = json.loads(line)
                                except json.JSONDecodeError:
                                    continue

                                # Normalize OpenAI chunk → internal format
                                normalized = self._normalize_chunk(
                                    raw_chunk, _tool_calls_acc
                                )
                                if normalized is None:
                                    continue

                                # Capture usage if present (some providers send it in last chunk)
                                if "usage" in raw_chunk and raw_chunk["usage"]:
                                    _usage = raw_chunk["usage"]

                                yield normalized
                                chunk_count += 1

                                if normalized.get("done"):
                                    done_received = True
                                    break

                    # After stream ends, emit final chunk with accumulated tool_calls
                    # if there are any and they weren't already yielded
                    final_tool_calls = self._finalize_tool_calls(_tool_calls_acc)
                    if final_tool_calls:
                        yield {
                            "message": {
                                "content": "",
                                "thinking": None,
                                "tool_calls": final_tool_calls,
                            },
                            "done": True,
                            "eval_count": _usage.get("completion_tokens", 0),
                            "prompt_eval_count": _usage.get("prompt_tokens", 0),
                        }
                        done_received = True

                    # Patch final chunk with usage data if we got usage
                    # (the normalized done chunk above already has it if
                    #  the provider sent usage in the last SSE event)

                    elapsed_total = time.monotonic() - request_started
                    if done_received or chunk_count > 0:
                        self._record_response_time(elapsed_total)
                        self._record_model_performance(
                            operation=operation,
                            response_time_sec=elapsed_total,
                            success=True,
                            messages=messages,
                            options=options,
                        )
                    return

                except TimeoutError:
                    await _cleanup_next_future()
                    raise

                except httpx.ReadError as e:
                    await _cleanup_next_future()
                    if attempt < max_retries:
                        wait = 2 ** (attempt + 1)
                        logger.warning(
                            "LLM stream read error (attempt %d/%d), retrying in %ds: %s",
                            attempt + 1,
                            max_retries + 1,
                            wait,
                            e,
                        )
                        await asyncio.sleep(wait)
                        continue
                    logger.error(
                        "LLM stream read error after %d attempts: %s",
                        max_retries + 1,
                        e,
                    )
                    raise TimeoutError(
                        f"LLM stream disconnected after {max_retries + 1} retries: {e}"
                    ) from e

                except httpx.HTTPStatusError as e:
                    err_msg = str(e).lower()

                    if any(p in err_msg for p in _PERMANENT_LLM_ERRORS):
                        logger.error("Permanent LLM error (not retrying): %s", e)
                        raise

                    if 400 <= e.response.status_code < 500:
                        logger.error("Permanent LLM error (client error): %s", e)
                        raise

                    if attempt < max_retries:
                        is_5xx = 500 <= e.response.status_code < 600
                        wait = (15 * (attempt + 1)) if is_5xx else (2 ** (attempt + 1))
                        logger.warning(
                            "LLM HTTP error (attempt %d/%d), retrying in %ss: %s",
                            attempt + 1,
                            max_retries + 1,
                            wait,
                            e,
                        )
                        await asyncio.sleep(wait)
                        continue
                    logger.error(
                        "LLM HTTP error after %d attempts: %s",
                        max_retries + 1,
                        e,
                    )
                    raise

                except Exception as e:
                    await _cleanup_next_future()

                    err_str = str(e).lower()
                    is_transient = any(
                        k in err_str
                        for k in (
                            "connection reset",
                            "connection refused",
                            "eof",
                            "broken pipe",
                            "timeout",
                            "timed out",
                            "network",
                            "connection error",
                            "stream ended",
                        )
                    )

                    if is_transient and attempt < max_retries:
                        wait = 2 ** (attempt + 1)
                        logger.warning(
                            "Transient LLM error (attempt %d/%d), retrying in %ss: %s",
                            attempt + 1,
                            max_retries + 1,
                            wait,
                            e,
                        )
                        await asyncio.sleep(wait)
                        continue

                    logger.exception("Unexpected error: %s", e)
                    raise
        except Exception:
            elapsed_total = time.monotonic() - request_started
            self._record_model_performance(
                operation=operation,
                response_time_sec=elapsed_total,
                success=False,
                messages=messages,
                options=options,
            )
            raise

    # ── Payload builder ─────────────────────────────────────────────────

    def _build_payload(
        self,
        messages: list[dict[str, Any]],
        *,
        stream: bool = False,
        tools: list[dict[str, Any]] | None = None,
        think: bool = False,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build OpenAI-compatible request payload from internal params."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
        }

        # Map Ollama-style options → OpenAI params
        if options:
            if "temperature" in options:
                payload["temperature"] = options["temperature"]
            if "num_predict" in options:
                payload["max_tokens"] = options["num_predict"]
            # num_ctx is not a standard OpenAI param — pass as extra if provider supports it
            # repeat_penalty → frequency_penalty (approximate mapping)
            if "repeat_penalty" in options:
                rp = options["repeat_penalty"]
                # Ollama: 1.05 → OpenAI: 0.05 (frequency_penalty range is -2.0 to 2.0)
                payload["frequency_penalty"] = max(0.0, min(2.0, float(rp) - 1.0))

        # Stream options: include usage in response
        if stream:
            payload["stream_options"] = {"include_usage": True}

        # Tools in OpenAI format (already in OpenAI format from tool_defs)
        if tools:
            payload["tools"] = tools

        # Thinking/reasoning support — provider-specific extra params
        if think and self._supports_thinking:
            cfg = get_config()
            extra_body = cfg.llm_extra_body
            if extra_body:
                payload.update(extra_body)
            else:
                # Default: try common thinking params
                # Ollama OpenAI compat: {"think": true}
                # OpenAI reasoning models: {"reasoning_effort": "low"}
                payload["think"] = True

        return payload

    # ── Chunk normalization (OpenAI → internal format) ──────────────────

    def _normalize_chunk(
        self,
        raw: dict[str, Any],
        tool_calls_acc: dict[int, dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Normalize an OpenAI SSE chunk to internal AIRecon format.

        Returns None for empty/noop chunks.
        """
        choices = raw.get("choices", [])
        if not choices:
            # Could be a usage-only chunk
            if "usage" in raw and raw.get("usage"):
                usage = raw["usage"]
                final_tcs = self._finalize_tool_calls(tool_calls_acc)
                return {
                    "message": {
                        "content": "",
                        "thinking": None,
                        "tool_calls": final_tcs if final_tcs else None,
                    },
                    "done": True,
                    "eval_count": usage.get("completion_tokens", 0),
                    "prompt_eval_count": usage.get("prompt_tokens", 0),
                }
            return None

        choice = choices[0]
        delta = choice.get("delta", {})
        finish_reason = choice.get("finish_reason")

        # Extract content
        content = delta.get("content") or ""

        # Extract thinking/reasoning (provider-specific field names)
        thinking = (
            delta.get("reasoning_content")
            or delta.get("reasoning")
            or delta.get("thinking")
            or None
        )

        # Accumulate tool_calls from streaming deltas
        delta_tool_calls = delta.get("tool_calls")
        if delta_tool_calls:
            for tc_delta in delta_tool_calls:
                idx = tc_delta.get("index", 0)
                if idx not in tool_calls_acc:
                    tool_calls_acc[idx] = {
                        "id": tc_delta.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": "",
                            "arguments": "",
                        },
                    }
                # Accumulate function name and arguments
                func = tc_delta.get("function", {})
                if func.get("name"):
                    tool_calls_acc[idx]["function"]["name"] = func["name"]
                if func.get("arguments"):
                    tool_calls_acc[idx]["function"]["arguments"] += func["arguments"]

        # Determine if this is a "done" chunk
        is_done = finish_reason is not None

        if is_done:
            final_tcs = self._finalize_tool_calls(tool_calls_acc)
            usage = raw.get("usage", {})
            return {
                "message": {
                    "content": content,
                    "thinking": thinking,
                    "tool_calls": final_tcs if final_tcs else None,
                },
                "done": True,
                "eval_count": usage.get("completion_tokens", 0) if usage else 0,
                "prompt_eval_count": usage.get("prompt_tokens", 0) if usage else 0,
            }

        # Regular chunk — don't emit tool_calls yet (still accumulating)
        return {
            "message": {
                "content": content,
                "thinking": thinking,
                "tool_calls": None,
            },
            "done": False,
        }

    @staticmethod
    def _finalize_tool_calls(
        acc: dict[int, dict[str, Any]],
    ) -> list[dict[str, Any]] | None:
        """Convert accumulated tool_calls to final format.

        Parses JSON argument strings and converts to the internal dict format
        that the rest of AIRecon expects.
        """
        if not acc:
            return None

        result: list[dict[str, Any]] = []
        for idx in sorted(acc.keys()):
            tc = acc[idx]
            func = tc.get("function", {})
            name = func.get("name", "")
            args_str = func.get("arguments", "")

            if not name:
                continue

            # Parse JSON arguments string → dict
            try:
                arguments = json.loads(args_str) if args_str else {}
            except json.JSONDecodeError:
                logger.warning(
                    "Failed to parse tool call arguments for '%s': %s",
                    name,
                    args_str[:200],
                )
                arguments = {}

            # Internal format expected by AIRecon
            result.append({
                "function": {
                    "name": name,
                    "arguments": arguments,
                },
            })

        return result if result else None

    @staticmethod
    def _extract_content_from_response(data: dict[str, Any]) -> str | None:
        """Extract text content from a non-streaming OpenAI response."""
        if not isinstance(data, dict):
            return None
        choices = data.get("choices", [])
        if not choices:
            return None
        message = choices[0].get("message", {})
        content = message.get("content")
        return content if content is not None else None

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_task_type(operation: str) -> str:
        task_type = str(operation or "").strip().lower()
        aliases = {
            "inference": "chat",
            "validation": "analysis",
            "summarization": "compression",
        }
        return aliases.get(task_type, task_type or "general")

    @staticmethod
    def _estimate_context_size(
        messages: list[dict[str, Any]],
        options: dict[str, Any] | None = None,
    ) -> int:
        total_chars = 0
        for message in messages or []:
            if not isinstance(message, dict):
                total_chars += len(str(message))
                continue
            for key in ("content", "thinking", "tool_calls"):
                value = message.get(key)
                if value in (None, ""):
                    continue
                if isinstance(value, str):
                    total_chars += len(value)
                else:
                    try:
                        total_chars += len(json.dumps(value, ensure_ascii=False))
                    except Exception:
                        total_chars += len(str(value))

        estimated_tokens = total_chars // 4
        if estimated_tokens > 0:
            return estimated_tokens

        if isinstance(options, dict):
            try:
                return max(0, int(options.get("num_ctx", 0) or 0))
            except (TypeError, ValueError):
                return 0
        return 0

    def _record_model_performance(
        self,
        operation: str,
        response_time_sec: float,
        success: bool,
        messages: list[dict[str, Any]],
        options: dict[str, Any] | None = None,
    ) -> None:
        model_name = str(getattr(self, "model", "") or "").strip()
        if not model_name:
            return

        try:
            get_memory_manager().record_model_performance(
                model_name=model_name,
                task_type=self._normalize_task_type(operation),
                response_time_sec=max(0.0, float(response_time_sec or 0.0)),
                success=success,
                context_size_used=self._estimate_context_size(messages, options),
            )
        except Exception as exc:
            logger.debug("Failed to record model performance: %s", exc)

    def _get_dynamic_timeout(self, operation: str = "inference") -> float:
        cfg = get_config()

        if operation == "compression":
            return max(180.0, cfg.llm_chunk_timeout)
        return cfg.llm_chunk_timeout

    def _record_response_time(self, response_time: float) -> None:
        if not hasattr(self, "_response_times"):
            self._response_times: list[float] = []
        if not hasattr(self, "_max_response_times"):
            self._max_response_times = 20
        self._response_times.append(response_time)
        max_len = self._max_response_times
        if len(self._response_times) > max_len:
            self._response_times = self._response_times[-max_len:]

    def get_response_time_stats(self) -> Dict[str, float]:
        if not hasattr(self, "_response_times"):
            self._response_times = []
        times = self._response_times[-10:] if self._response_times else []
        if not times:
            return {"avg": 0.0, "min": 0.0, "max": 0.0, "count": 0}
        return {
            "avg": sum(times) / len(times),
            "min": min(times),
            "max": max(times),
            "count": len(self._response_times),
        }


# Backward-compatible alias for existing imports
OllamaClient = LLMClient
