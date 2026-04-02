from __future__ import annotations

import json
import math
import sys
import time
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel

from app.config import RoleModelSettings
from app.schemas.common import TokenUsage
from app.services.file_logger import log_llm_error


class LlmError(RuntimeError):
    pass


@dataclass
class LlmJsonResult:
    payload: dict[str, Any]
    provider: str
    model: str
    token_usage: TokenUsage | None = None


class BaseLlmClient:
    def __init__(self, settings: RoleModelSettings):
        self.settings = settings

    def generate_json(
        self,
        schema_name: str,
        schema_model: type[BaseModel],
        system_prompt: str,
        user_prompt: str,
    ) -> LlmJsonResult:
        raise NotImplementedError


class MockLlmClient(BaseLlmClient):
    def __init__(self, settings: RoleModelSettings):
        super().__init__(settings)

    def generate_json(
        self,
        schema_name: str,
        schema_model: type[BaseModel],
        system_prompt: str,
        user_prompt: str,
    ) -> LlmJsonResult:
        raise LlmError("mock provider does not generate remote completions")


class OpenAICompatibleClient(BaseLlmClient):
    def __init__(self, settings: RoleModelSettings):
        if not settings.api_key:
            raise LlmError("missing role API key")
        super().__init__(settings)
        self.base_url = (settings.base_url or "https://api.openai.com/v1").rstrip("/")

    def generate_json(
        self,
        schema_name: str,
        schema_model: type[BaseModel],
        system_prompt: str,
        user_prompt: str,
    ) -> LlmJsonResult:
        schema = schema_model.model_json_schema()
        payload = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "schema": schema,
                },
            },
        }
        response_json = _post_json(
            settings=self.settings,
            url=f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
            },
            payload=payload,
            timeout_seconds=self.settings.timeout_seconds,
        )
        try:
            content = response_json["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            log_llm_error(
                role="provider",
                provider=self.settings.provider,
                model=self.settings.model,
                stage="response_shape",
                error=str(error),
                extra={"schema_name": schema_name},
            )
            raise LlmError(f"openai-compatible response shape invalid: {error}") from error

        parsed = _parse_json_response_text(
            provider=self.settings.provider,
            model=self.settings.model,
            schema_name=schema_name,
            text=content,
            error_prefix="openai-compatible content was not valid json",
        )

        token_usage = _extract_openai_token_usage(response_json) or _estimate_token_usage(
            system_prompt,
            user_prompt,
            content,
        )
        return LlmJsonResult(
            payload=parsed,
            provider=self.settings.provider,
            model=self.settings.model,
            token_usage=token_usage,
        )


class GeminiClient(BaseLlmClient):
    def __init__(self, settings: RoleModelSettings):
        if not settings.api_key:
            raise LlmError("missing role API key")
        super().__init__(settings)
        self.base_url = (settings.base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        self.model_id = _resolve_gemini_model_id(settings.model)

    def generate_json(
        self,
        schema_name: str,
        schema_model: type[BaseModel],
        system_prompt: str,
        user_prompt: str,
    ) -> LlmJsonResult:
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": f"{system_prompt}\n\n{user_prompt}",
                        }
                    ]
                }
            ],
        }
        if _gemini_supports_json_mode(self.model_id):
            payload["generationConfig"] = {
                "responseMimeType": "application/json",
            }
        response_json = _post_json(
            settings=self.settings,
            url=f"{self.base_url}/models/{self.model_id}:generateContent",
            headers={
                "x-goog-api-key": self.settings.api_key,
                "Content-Type": "application/json",
            },
            payload=payload,
            timeout_seconds=self.settings.timeout_seconds,
        )
        try:
            text = response_json["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as error:
            log_llm_error(
                role="provider",
                provider=self.settings.provider,
                model=self.settings.model,
                stage="response_shape",
                error=str(error),
                extra={"schema_name": schema_name},
            )
            raise LlmError(f"gemini response shape invalid: {error}") from error

        parsed = _parse_json_response_text(
            provider=self.settings.provider,
            model=self.settings.model,
            schema_name=schema_name,
            text=text,
            error_prefix="gemini content was not valid json",
        )

        token_usage = _extract_gemini_token_usage(response_json) or _estimate_token_usage(
            system_prompt,
            user_prompt,
            text,
        )
        return LlmJsonResult(
            payload=parsed,
            provider=self.settings.provider,
            model=self.model_id,
            token_usage=token_usage,
        )


class AnthropicClient(BaseLlmClient):
    def __init__(self, settings: RoleModelSettings):
        if not settings.api_key:
            raise LlmError("missing role API key")
        super().__init__(settings)
        self.base_url = (settings.base_url or "https://api.anthropic.com/v1").rstrip("/")

    def generate_json(
        self,
        schema_name: str,
        schema_model: type[BaseModel],
        system_prompt: str,
        user_prompt: str,
    ) -> LlmJsonResult:
        payload = {
            "model": self.settings.model,
            "max_tokens": 2048,
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": f"{user_prompt}\n\nReturn valid JSON only.",
                }
            ],
        }
        response_json = _post_json(
            settings=self.settings,
            url=f"{self.base_url}/messages",
            headers={
                "x-api-key": self.settings.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            payload=payload,
            timeout_seconds=self.settings.timeout_seconds,
        )
        try:
            blocks = response_json["content"]
            text = "".join(block.get("text", "") for block in blocks if isinstance(block, dict))
        except (KeyError, TypeError) as error:
            log_llm_error(
                role="provider",
                provider=self.settings.provider,
                model=self.settings.model,
                stage="response_shape",
                error=str(error),
                extra={"schema_name": schema_name},
            )
            raise LlmError(f"anthropic response shape invalid: {error}") from error

        parsed = _parse_json_response_text(
            provider=self.settings.provider,
            model=self.settings.model,
            schema_name=schema_name,
            text=text,
            error_prefix="anthropic content was not valid json",
        )

        token_usage = _extract_anthropic_token_usage(response_json) or _estimate_token_usage(
            system_prompt,
            user_prompt,
            text,
        )
        return LlmJsonResult(
            payload=parsed,
            provider=self.settings.provider,
            model=self.settings.model,
            token_usage=token_usage,
        )


def build_llm_client(settings: RoleModelSettings) -> BaseLlmClient:
    if settings.provider == "mock":
        return MockLlmClient(settings)
    if settings.provider in {"openai", "openai_compatible"}:
        return OpenAICompatibleClient(settings)
    if settings.provider == "gemini":
        return GeminiClient(settings)
    if settings.provider == "anthropic":
        return AnthropicClient(settings)
    raise LlmError(f"unsupported provider: {settings.provider}")


def _post_json(
    settings: RoleModelSettings,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    if "pytest" in sys.modules:
        raise LlmError("remote llm calls disabled under pytest")
    timeout = httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 15.0))
    retries = 2
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = httpx.post(url, headers=headers, json=payload, timeout=timeout)
        except httpx.HTTPError as error:
            last_error = error
            should_retry = attempt < retries and _is_retryable_http_error(error)
            log_llm_error(
                role="provider",
                provider=settings.provider,
                model=settings.model,
                stage="http_request",
                error=str(error),
                extra={"url": url, "attempt": attempt + 1, "retrying": should_retry},
            )
            if should_retry:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise LlmError(f"http request failed: {error}") from error

        if response.status_code >= 400:
            should_retry = attempt < retries and response.status_code in {408, 429, 500, 502, 503, 504}
            log_llm_error(
                role="provider",
                provider=settings.provider,
                model=settings.model,
                stage="http_status",
                error=f"status={response.status_code}",
                extra={
                    "url": url,
                    "response_text": response.text[:400],
                    "attempt": attempt + 1,
                    "retrying": should_retry,
                },
            )
            if should_retry:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise LlmError(f"http request returned {response.status_code}: {response.text}")
        break
    else:
        raise LlmError(f"http request failed: {last_error}")

    try:
        return response.json()
    except json.JSONDecodeError as error:
        log_llm_error(
            role="provider",
            provider=settings.provider,
            model=settings.model,
            stage="response_body_parse",
            error=str(error),
            extra={"url": url, "response_text": response.text[:400]},
        )
        raise LlmError(f"provider response was not valid json: {error}") from error


def _resolve_gemini_model_id(model: str) -> str:
    normalized = model.strip()
    if not normalized:
        return normalized

    alias_key = normalized.lower()
    aliases = {
        "gemini 2 flash": "gemini-2.0-flash",
        "gemini 2.0 flash": "gemini-2.0-flash",
        "gemini 2 flash lite": "gemini-2.0-flash-lite",
        "gemini 2.0 flash lite": "gemini-2.0-flash-lite",
        "gemini 2.5 flash": "gemini-2.5-flash",
        "gemini 2.5 pro": "gemini-2.5-pro",
        "gemma 3 27b": "gemma-3-27b-it",
        "gemma 3 12b": "gemma-3-12b-it",
        "gemma 3 4b": "gemma-3-4b-it",
        "gemma 3 1b": "gemma-3-1b-it",
    }
    if alias_key in aliases:
        return aliases[alias_key]

    if " " not in normalized:
        return normalized

    return normalized.lower().replace(" ", "-")


def _gemini_supports_json_mode(model_id: str) -> bool:
    return not model_id.startswith("gemma-")


def _extract_anthropic_token_usage(response_json: dict[str, Any]) -> TokenUsage | None:
    usage = response_json.get("usage")
    if not isinstance(usage, dict):
        return None
    input_tokens = int(usage.get("input_tokens", 0))
    output_tokens = int(usage.get("output_tokens", 0))
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        estimated=False,
    )


def _extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    fence_variants = (
        ("```json", "```"),
        ("```", "```"),
    )
    for start_token, end_token in fence_variants:
        if stripped.startswith(start_token) and stripped.endswith(end_token):
            inner = stripped[len(start_token) : len(stripped) - len(end_token)].strip()
            try:
                return json.loads(inner)
            except json.JSONDecodeError:
                pass

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    candidate = stripped[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        repaired = _repair_common_json_issues(candidate)
        if repaired is None:
            return None
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            return None


def _parse_json_response_text(
    provider: str,
    model: str,
    schema_name: str,
    text: str,
    error_prefix: str,
) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        error = "empty response text"
        log_llm_error(
            role="provider",
            provider=provider,
            model=model,
            stage="response_json_parse",
            error=error,
            extra={"schema_name": schema_name, "content_preview": text[:400]},
        )
        raise LlmError(f"{error_prefix}: {error}")

    parsed = _extract_json_object(stripped)
    if parsed is not None:
        return parsed

    try:
        candidate = json.loads(stripped)
    except json.JSONDecodeError as error:
        log_llm_error(
            role="provider",
            provider=provider,
            model=model,
            stage="response_json_parse",
            error=str(error),
            extra={"schema_name": schema_name, "content_preview": text[:400]},
        )
        raise LlmError(f"{error_prefix}: {error}") from error

    if not isinstance(candidate, dict):
        error = f"json root was {type(candidate).__name__}, expected object"
        log_llm_error(
            role="provider",
            provider=provider,
            model=model,
            stage="response_json_shape",
            error=error,
            extra={"schema_name": schema_name, "content_preview": text[:400]},
        )
        raise LlmError(f"{error_prefix}: {error}")
    return candidate


def _is_retryable_http_error(error: httpx.HTTPError) -> bool:
    return isinstance(error, (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.WriteTimeout, httpx.RemoteProtocolError))


def _repair_common_json_issues(text: str) -> str | None:
    stripped = text.strip()
    if not stripped:
        return None

    repaired = stripped
    fence_variants = ("```json", "```JSON", "```")
    for fence in fence_variants:
        if repaired.startswith(fence):
            repaired = repaired[len(fence) :].lstrip()
    if repaired.endswith("```"):
        repaired = repaired[:-3].rstrip()

    repaired = repaired.replace("\r\n", "\n")
    repaired = _escape_unescaped_inner_quotes(repaired)
    return repaired


def _escape_unescaped_inner_quotes(text: str) -> str:
    chars: list[str] = []
    in_string = False
    escape = False
    i = 0
    while i < len(text):
        ch = text[i]
        if escape:
            chars.append(ch)
            escape = False
            i += 1
            continue
        if ch == "\\":
            chars.append(ch)
            escape = True
            i += 1
            continue
        if ch == '"':
            if in_string:
                j = i + 1
                while j < len(text) and text[j].isspace():
                    j += 1
                if j < len(text) and text[j] not in {",", "}", "]", ":"}:
                    chars.append('\\"')
                    i += 1
                    continue
            in_string = not in_string
            chars.append(ch)
            i += 1
            continue
        chars.append(ch)
        i += 1
    return "".join(chars)


def _extract_openai_token_usage(response_json: dict[str, Any]) -> TokenUsage | None:
    usage = response_json.get("usage")
    if not isinstance(usage, dict):
        return None
    return TokenUsage(
        input_tokens=int(usage.get("prompt_tokens", 0) or 0),
        output_tokens=int(usage.get("completion_tokens", 0) or 0),
        total_tokens=int(usage.get("total_tokens", 0) or 0),
        estimated=False,
    )


def _extract_gemini_token_usage(response_json: dict[str, Any]) -> TokenUsage | None:
    usage = response_json.get("usageMetadata")
    if not isinstance(usage, dict):
        return None
    input_tokens = int(usage.get("promptTokenCount", 0) or 0)
    output_tokens = int(usage.get("candidatesTokenCount", 0) or 0)
    total_tokens = int(usage.get("totalTokenCount", input_tokens + output_tokens) or 0)
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        estimated=False,
    )


def _estimate_token_usage(system_prompt: str, user_prompt: str, response_text: str) -> TokenUsage:
    input_tokens = _estimate_tokens(system_prompt) + _estimate_tokens(user_prompt)
    output_tokens = _estimate_tokens(response_text)
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        estimated=True,
    )


def _estimate_tokens(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    return max(1, math.ceil(len(stripped) / 4))
