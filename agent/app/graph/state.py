from __future__ import annotations

from typing import TypedDict

from app.schemas.intent import IntentValidationRequest, IntentValidationResponse
from app.schemas.narrative import NarrativeRequest, NarrativeResponse


class IntentGraphState(TypedDict, total=False):
    request: IntentValidationRequest
    system_prompt: str
    user_prompt: str
    raw_result: dict
    error: str
    response: IntentValidationResponse


class NarrativeGraphState(TypedDict, total=False):
    kind: str
    request: NarrativeRequest
    system_prompt: str
    user_prompt: str
    raw_result: dict
    error: str
    response: NarrativeResponse
