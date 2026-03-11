from __future__ import annotations

from pydantic import ValidationError

from app.config import RoleModelSettings
from app.prompts.intent_builder import build_intent_prompts
from app.retrieval.schemas import RetrievalContext
from app.retrieval.search import RetrievalService
from app.schemas.common import Action, ActionType
from app.schemas.intent import IntentValidationRequest, IntentValidationResponse
from app.services.llm_client import BaseLlmClient, LlmError


class IntenderAgent:
    def __init__(self, settings: RoleModelSettings, llm_client: BaseLlmClient, retrieval: RetrievalService):
        self.settings = settings
        self.llm_client = llm_client
        self.retrieval = retrieval

    def handle(self, request: IntentValidationRequest) -> IntentValidationResponse:
        context = self._retrieve_context(request)
        system_prompt, user_prompt = build_intent_prompts(request, context)
        try:
            result = self.llm_client.generate_json(
                schema_name="intent_validation",
                schema_model=IntentValidationResponse,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            response = IntentValidationResponse.model_validate(
                {
                    **result.payload,
                    "source": f"{result.provider}_llm",
                    "provider": result.provider,
                    "model": result.model,
                    "retrieval_used": context.used,
                    "retrieved_document_ids": context.document_ids,
                }
            )
        except (LlmError, ValidationError) as error:
            response = self._fallback(request, context, str(error))
        return self._validate(response, request)

    def _retrieve_context(self, request: IntentValidationRequest) -> RetrievalContext:
        return self.retrieval.search_for_intender(request)

    def _validate(
        self,
        response: IntentValidationResponse,
        request: IntentValidationRequest,
    ) -> IntentValidationResponse:
        if response.action.action_type not in request.allowed_actions:
            response.action.action_type = ActionType.INVESTIGATE
            response.action.target = None
            response.validation_flags.append("action_not_allowed")
            response.confidence = min(response.confidence, 0.25)

        if response.action.target and response.action.target not in request.scene_context.visible_targets:
            response.action.target = None
            response.validation_flags.append("target_not_visible")
            response.confidence = min(response.confidence, 0.25)
        return response

    def _fallback(
        self,
        request: IntentValidationRequest,
        context: RetrievalContext,
        reason: str,
    ) -> IntentValidationResponse:
        normalized = request.player_input.strip().lower()
        action_type = ActionType.INVESTIGATE
        target = None
        confidence = 0.55

        if any(token in normalized for token in ("창고", "warehouse")):
            action_type = ActionType.MOVE
            target = "warehouse"
            confidence = 0.92
        elif any(token in normalized for token in ("골목", "alley")):
            action_type = ActionType.MOVE
            target = "alley"
            confidence = 0.92
        elif any(token in normalized for token in ("여관", "tavern", "inn")):
            action_type = ActionType.MOVE
            target = "tavern"
            confidence = 0.92
        elif any(token in normalized for token in ("광장", "square")):
            action_type = ActionType.MOVE
            target = "village_square"
            confidence = 0.88
        elif any(token in normalized for token in ("아리아", "aria", "대화", "talk")):
            action_type = ActionType.TALK
            target = "aria"
            confidence = 0.94
        elif any(token in normalized for token in ("휴식", "rest")):
            action_type = ActionType.REST
            confidence = 0.86
        elif any(token in normalized for token in ("횃불", "torch")):
            action_type = ActionType.USE_ITEM
            target = "torch"
            confidence = 0.84
        elif any(token in normalized for token in ("도망", "flee")):
            action_type = ActionType.FLEE
            confidence = 0.83

        return IntentValidationResponse(
            action=Action(action_type=action_type, target=target, raw_input=request.player_input),
            confidence=confidence,
            validation_flags=[f"heuristic_intent_fallback:{reason}"],
            source="heuristic",
            provider=self.settings.provider,
            model=self.settings.model,
            retrieval_used=context.used,
            retrieved_document_ids=context.document_ids,
        )
