from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel

from app.config import Settings


class LlmError(RuntimeError):
    pass


@dataclass
class LlmJsonResult:
    payload: dict[str, Any]
    provider: str
    model: str


class BaseLlmClient:
    def generate_json(
        self,
        schema_name: str,
        schema_model: type[BaseModel],
        system_prompt: str,
        user_prompt: str,
    ) -> LlmJsonResult:
        raise NotImplementedError


class MockLlmClient(BaseLlmClient):
    def __init__(self, settings: Settings):
        self.settings = settings

    def generate_json(
        self,
        schema_name: str,
        schema_model: type[BaseModel],
        system_prompt: str,
        user_prompt: str,
    ) -> LlmJsonResult:
        raise LlmError("mock provider does not generate remote completions")


class OpenAICompatibleClient(BaseLlmClient):
    def __init__(self, settings: Settings):
        if not settings.llm_api_key:
            raise LlmError("missing AGENT_LLM_API_KEY/OPENAI_API_KEY")
        self.settings = settings
        self.base_url = (settings.llm_base_url or "https://api.openai.com/v1").rstrip("/")

    def generate_json(
        self,
        schema_name: str,
        schema_model: type[BaseModel],
        system_prompt: str,
        user_prompt: str,
    ) -> LlmJsonResult:
        schema = schema_model.model_json_schema()
        payload = {
            "model": self.settings.llm_model,
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
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.settings.llm_api_key}",
                "Content-Type": "application/json",
            },
            payload=payload,
            timeout_seconds=self.settings.llm_timeout_seconds,
        )
        try:
            content = response_json["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise LlmError(f"openai-compatible response shape invalid: {error}") from error

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as error:
            raise LlmError(f"openai-compatible content was not valid json: {error}") from error

        return LlmJsonResult(
            payload=parsed,
            provider=self.settings.llm_provider,
            model=self.settings.llm_model,
        )


class GeminiClient(BaseLlmClient):
    def __init__(self, settings: Settings):
        if not settings.llm_api_key:
            raise LlmError("missing AGENT_LLM_API_KEY/GEMINI_API_KEY")
        self.settings = settings
        self.base_url = (settings.llm_base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")

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
            f"{self.base_url}/models/{self.settings.llm_model}:generateContent",
            headers={
                "x-goog-api-key": self.settings.llm_api_key,
                "Content-Type": "application/json",
            },
            payload=payload,
            timeout_seconds=self.settings.llm_timeout_seconds,
        )
        try:
            text = response_json["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as error:
            raise LlmError(f"gemini response shape invalid: {error}") from error

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as error:
            raise LlmError(f"gemini content was not valid json: {error}") from error

        return LlmJsonResult(
            payload=parsed,
            provider=self.settings.llm_provider,
            model=self.settings.llm_model,
        )


def build_llm_client(settings: Settings) -> BaseLlmClient:
    if settings.llm_provider == "mock":
        return MockLlmClient(settings)
    if settings.llm_provider in {"openai", "openai_compatible"}:
        return OpenAICompatibleClient(settings)
    if settings.llm_provider == "gemini":
        return GeminiClient(settings)
    raise LlmError(f"unsupported provider: {settings.llm_provider}")


def _post_json(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=timeout_seconds)
    except httpx.HTTPError as error:
        raise LlmError(f"http request failed: {error}") from error

    if response.status_code >= 400:
        raise LlmError(f"http request returned {response.status_code}: {response.text}")

    try:
        return response.json()
    except json.JSONDecodeError as error:
        raise LlmError(f"provider response was not valid json: {error}") from error
