from datetime import datetime, timedelta, timezone

import httpx

from app.services.llm_client import (
    _extract_retry_delay_from_body,
    _parse_retry_after_seconds,
    _retry_delay_seconds,
)


def test_parse_retry_after_seconds_supports_delta_seconds() -> None:
    assert _parse_retry_after_seconds("7") == 7.0


def test_parse_retry_after_seconds_supports_http_date() -> None:
    retry_at = datetime.now(timezone.utc) + timedelta(seconds=2)
    parsed = _parse_retry_after_seconds(retry_at.strftime("%a, %d %b %Y %H:%M:%S GMT"))

    assert 0.0 < parsed <= 3.0


def test_extract_retry_delay_from_body_supports_google_style_retry_delay() -> None:
    response = httpx.Response(
        429,
        json={
            "error": {
                "status": "RESOURCE_EXHAUSTED",
                "message": "quota hit",
                "retryDelay": "11s",
            }
        },
    )

    assert _extract_retry_delay_from_body(response) == 11.0


def test_retry_delay_seconds_prefers_provider_backoff_hints_over_default() -> None:
    response = httpx.Response(429, headers={"retry-after": "9"})

    assert _retry_delay_seconds(response, attempt=0) == 9.0
