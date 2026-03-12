from __future__ import annotations

from pydantic import ValidationError

from app.config import RoleModelSettings
from app.prompts.narrative_builder import build_narrative_prompts
from app.retrieval.schemas import RetrievalContext
from app.retrieval.search import RetrievalService
from app.schemas.narrative import NarrativeRequest, NarrativeResponse
from app.services.fallback_renderer import render_opening, render_turn
from app.services.llm_client import BaseLlmClient, LlmError


class NarratorAgent:
    def __init__(self, settings: RoleModelSettings, llm_client: BaseLlmClient, retrieval: RetrievalService):
        self.settings = settings
        self.llm_client = llm_client
        self.retrieval = retrieval

    def render_opening(self, request: NarrativeRequest) -> NarrativeResponse:
        return self._render("opening", request)

    def render_turn(self, request: NarrativeRequest) -> NarrativeResponse:
        return self._render("turn", request)

    def _render(self, kind: str, request: NarrativeRequest) -> NarrativeResponse:
        context = self._retrieve_context(kind, request)
        system_prompt, user_prompt = build_narrative_prompts(kind, request, context)
        try:
            result = self.llm_client.generate_json(
                schema_name=f"{kind}_narrative",
                schema_model=NarrativeResponse,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            response = NarrativeResponse.model_validate(
                {
                    **result.payload,
                    "source": f"{result.provider}_llm",
                    "provider": result.provider,
                    "model": result.model,
                    "used_fallback": False,
                    "retrieval_used": context.used,
                    "retrieved_document_ids": context.document_ids,
                }
            )
        except (LlmError, ValidationError) as error:
            response = self._fallback(kind, request, context, str(error))
        return self._validate(kind, response, request)

    def _retrieve_context(self, kind: str, request: NarrativeRequest) -> RetrievalContext:
        return self.retrieval.search_for_narrator(kind, request)

    def _validate(self, kind: str, response: NarrativeResponse, request: NarrativeRequest) -> NarrativeResponse:
        response.choices = [choice for choice in response.choices if choice in request.allowed_choices][:4]
        if len(response.choices) < 2 or not response.narrative.strip():
            fallback = self._fallback(kind, request, RetrievalContext(), "invalid_narrative_output")
            fallback.safety_flags.append("invalid_narrative_output")
            return fallback
        return response

    def _fallback(
        self,
        kind: str,
        request: NarrativeRequest,
        context: RetrievalContext,
        reason: str,
    ) -> NarrativeResponse:
        response = render_opening(request) if kind == "opening" else render_turn(request)
        response.safety_flags.append(f"template_fallback:{reason}")
        response.provider = self.settings.provider
        response.model = self.settings.model
        response.retrieval_used = context.used
        response.retrieved_document_ids = context.document_ids
        return response
