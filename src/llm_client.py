"""OpenAI-compatible LLM client with retry + JSON validation.

Wraps an OpenAI-style endpoint and provides two main methods:
- ``chat`` for raw text completions
- ``chat_json`` for completions validated against a pydantic model,
  with self-correcting retries that feed JSON / schema errors back to the model.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from typing import Any, Type, TypeVar

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)
from pydantic import BaseModel, ValidationError

from .config_loader import get_llm_config

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_RETRYABLE_EXC: tuple[type[BaseException], ...] = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
)


class LLMClient:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or get_llm_config()
        api_key = cfg.get("api_key", "")
        if not api_key:
            raise ValueError(
                "LLM api_key is missing. Set it in config/config.yaml, "
                "LLM_API_KEY env var, or streamlit secrets."
            )
        self.client = OpenAI(base_url=cfg["base_url"], api_key=api_key)
        self.model: str = cfg["model_name"]
        self.temperature: float = float(cfg["temperature"])
        self.max_tokens: int = int(cfg["max_tokens"])
        self.max_retries: int = int(cfg["max_retries"])
        self.retry_delay: float = float(cfg["retry_delay"])

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
    ) -> str:
        """Simple chat completion returning raw text, with retry on transient errors."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return self._create_with_retry(messages, temperature)

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: Type[T],
        temperature: float | None = None,
    ) -> T:
        """Chat completion validated against ``response_model``.

        On JSON-decode or pydantic-validation failure, appends the bad output
        and a corrective user message and retries up to ``max_retries`` times.
        Transient HTTP errors (connection / timeout / rate limit) are retried
        with exponential backoff.
        """
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        attempts = self.max_retries + 1
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                raw = self._create_with_retry(messages, temperature)
                logger.debug("LLM raw output (first 500 chars): %s", raw[:500])
                json_str = self._extract_json(raw)
                json_str = self._repair_json(json_str)
                parsed = json.loads(json_str)
                return response_model.model_validate(parsed)
            except json.JSONDecodeError as e:
                last_error = e
                logger.warning(
                    "JSON decode error (attempt %d/%d): %s",
                    attempt + 1, attempts, e,
                )
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": (
                        "你之前的输出不是有效的JSON格式。"
                        f"错误信息：{e}。"
                        "请严格只输出合法的JSON对象（可以用 ```json ... ``` 包裹），"
                        "不要在JSON前后添加任何解释、注释或Markdown标题。"
                    ),
                })
            except ValidationError as e:
                last_error = e
                logger.warning(
                    "Pydantic validation error (attempt %d/%d): %s",
                    attempt + 1, attempts, e,
                )
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": (
                        "你的JSON结构不符合要求的Schema。"
                        f"校验错误：{e}。"
                        "请仔细检查字段名、类型、必填项和嵌套结构后重新输出，只输出JSON。"
                    ),
                })

            if attempt < attempts - 1:
                self._sleep_backoff(attempt)

        raise RuntimeError(
            f"LLM failed to produce valid JSON after {attempts} attempts; "
            f"last error: {last_error}"
        )

    def _create_with_retry(
        self,
        messages: list[dict[str, str]],
        temperature: float | None,
    ) -> str:
        attempts = self.max_retries + 1
        last_exc: BaseException | None = None

        for attempt in range(attempts):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature if temperature is not None else self.temperature,
                    max_tokens=self.max_tokens,
                )
                content = resp.choices[0].message.content or ""
                if not content.strip():
                    raise RuntimeError("LLM returned empty content")
                return content
            except AuthenticationError:
                raise
            except _RETRYABLE_EXC as e:
                last_exc = e
                logger.warning(
                    "Transient LLM API error (attempt %d/%d): %s",
                    attempt + 1, attempts, e,
                )
                if attempt < attempts - 1:
                    self._sleep_backoff(attempt)
            except APIStatusError as e:
                # 5xx is retryable, 4xx (other than 401/429) is not.
                status = getattr(e, "status_code", None)
                last_exc = e
                if status is not None and 500 <= int(status) < 600 and attempt < attempts - 1:
                    logger.warning(
                        "Server error %s (attempt %d/%d), retrying",
                        status, attempt + 1, attempts,
                    )
                    self._sleep_backoff(attempt)
                else:
                    raise

        raise RuntimeError(
            f"LLM API failed after {attempts} attempts; last error: {last_exc}"
        )

    def _sleep_backoff(self, attempt: int) -> None:
        delay = self.retry_delay * (attempt + 1)
        jitter = random.uniform(0, self.retry_delay)
        time.sleep(delay + jitter)

    @staticmethod
    def _repair_json(text: str) -> str:
        """Attempt to repair common LLM JSON mistakes.

        Handles: single-quoted strings, trailing commas, JavaScript-style
        comments, unquoted keys, and BOM characters.
        """
        text = text.strip()
        if not text:
            return text

        # Remove BOM
        if text.startswith("\ufeff"):
            text = text[1:]

        # Remove JavaScript-style single-line comments (// ...)
        text = re.sub(r'//[^\n]*', '', text)

        # Remove multi-line comments (/* ... */)
        text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)

        # Replace single-quoted strings with double-quoted strings
        # This is a simplistic approach - replace ' with " when not inside a
        # double-quoted string. We process char by char.
        result = []
        in_double = False
        in_single = False
        escape = False
        for ch in text:
            if escape:
                result.append(ch)
                escape = False
                continue
            if ch == '\\' and (in_double or in_single):
                result.append(ch)
                escape = True
                continue
            if ch == '"' and not in_single:
                in_double = not in_double
                result.append(ch)
                continue
            if ch == "'" and not in_double:
                in_single = not in_single
                result.append('"')
                continue
            result.append(ch)
        text = ''.join(result)

        # Remove trailing commas before } or ]
        text = re.sub(r',\s*([}\]])', r'\1', text)

        return text

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract a JSON object/array from text, handling markdown fences.

        Tries, in order:
        1. A ``\\`\\`\\`json ... \\`\\`\\`` block
        2. Any ``\\`\\`\\` ... \\`\\`\\` fenced block
        3. The first balanced ``{...}`` or ``[...]`` substring
        4. The raw text (best effort by ``json.loads``)
        """
        text = text.strip()
        if not text:
            return text

        if text.startswith("```"):
            parts = text.split("```")
            if len(parts) >= 3:
                body = parts[1]
            else:
                body = parts[-1]
            body = body.lstrip("`").strip()
            if "\n" in body:
                first, rest = body.split("\n", 1)
                if first.strip() and not first.strip().startswith(("{", "[")):
                    body = rest
            return body.strip()

        # Heuristic: find first balanced JSON object/array.
        for opener, closer in (("{", "}"), ("[", "]")):
            start = text.find(opener)
            if start == -1:
                continue
            depth = 0
            in_str = False
            escape = False
            for i in range(start, len(text)):
                ch = text[i]
                if in_str:
                    if escape:
                        escape = False
                    elif ch == "\\":
                        escape = True
                    elif ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                elif ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
                    if depth == 0:
                        return text[start:i + 1].strip()
        return text