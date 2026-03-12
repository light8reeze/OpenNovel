from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel

from app.config import RoleModelSettings
from app.services.file_logger import log_llm_error


class LlmError(RuntimeError):
    pass


@dataclass
class LlmJsonResult:
    payload: dict[str, Any]
    provider: str
    model: str


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

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as error:
            log_llm_error(
                role="provider",
                provider=self.settings.provider,
                model=self.settings.model,
                stage="response_json_parse",
                error=str(error),
                extra={"schema_name": schema_name, "content_preview": content[:400]},
            )
            raise LlmError(f"openai-compatible content was not valid json: {error}") from error

        return LlmJsonResult(
            payload=parsed,
            provider=self.settings.provider,
            model=self.settings.model,
        )


class GeminiClient(BaseLlmClient):
    def __init__(self, settings: RoleModelSettings):
        if not settings.api_key:
            raise LlmError("missing role API key")
        super().__init__(settings)
        self.base_url = (settings.base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")

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
            "generationConfig": {
                "responseMimeType": "application/json",
            },
        }
        response_json = _post_json(
            settings=self.settings,
            url=f"{self.base_url}/models/{self.settings.model}:generateContent",
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

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as error:
            log_llm_error(
                role="provider",
                provider=self.settings.provider,
                model=self.settings.model,
                stage="response_json_parse",
                error=str(error),
                extra={"schema_name": schema_name, "content_preview": text[:400]},
            )
            raise LlmError(f"gemini content was not valid json: {error}") from error

        return LlmJsonResult(
            payload=parsed,
            provider=self.settings.provider,
            model=self.settings.model,
        )


def build_llm_client(settings: RoleModelSettings) -> BaseLlmClient:
    if settings.provider == "mock":
        return MockLlmClient(settings)
    if settings.provider in {"openai", "openai_compatible"}:
        return OpenAICompatibleClient(settings)
    if settings.provider == "gemini":
        return GeminiClient(settings)
    raise LlmError(f"unsupported provider: {settings.provider}")


def _post_json(
    settings: RoleModelSettings,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=timeout_seconds)
    except httpx.HTTPError as error:
        log_llm_error(
            role="provider",
            provider=settings.provider,
            model=settings.model,
            stage="http_request",
            error=str(error),
            extra={"url": url},
        )
        raise LlmError(f"http request failed: {error}") from error

    if response.status_code >= 400:
        log_llm_error(
            role="provider",
            provider=settings.provider,
            model=settings.model,
            stage="http_status",
            error=f"status={response.status_code}",
            extra={"url": url, "response_text": response.text[:400]},
        )
        raise LlmError(f"http request returned {response.status_code}: {response.text}")

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
