from __future__ import annotations

from pydantic import ValidationError

from app.config import RoleModelSettings
from app.prompts.intent_builder import build_intent_prompts
from app.retrieval.schemas import RetrievalContext
from app.retrieval.search import RetrievalService
from app.schemas.common import Action, ActionType
from app.schemas.intent import IntentValidationLlmResponse, IntentValidationRequest, IntentValidationResponse
from app.services.file_logger import log_llm_error
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
                schema_model=IntentValidationLlmResponse,
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
                    "token_usage": result.token_usage.model_dump(mode="json") if result.token_usage else None,
                }
            )
        except (LlmError, ValidationError) as error:
            log_llm_error(
                role="intender",
                provider=self.settings.provider,
                model=self.settings.model,
                stage="fallback",
                error=str(error),
                extra={
                    "player_input": request.player_input,
                    "retrieval_used": context.used,
                    "retrieved_document_ids": context.document_ids,
                },
            )
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

        if any(token in normalized for token in ("회랑", "hall")):
            action_type = ActionType.MOVE
            target = "hall"
            confidence = 0.92
        elif any(token in normalized for token in ("함정방", "함정", "trap room", "trap")):
            action_type = ActionType.MOVE
            target = "trap_room"
            confidence = 0.92
        elif any(token in normalized for token in ("성소", "제단", "sanctum", "altar")):
            action_type = ActionType.MOVE
            target = "sanctum"
            confidence = 0.92
        elif any(token in normalized for token in ("입구", "entrance", "되돌아", "돌아간다")):
            action_type = ActionType.MOVE
            target = "ruins_entrance"
            confidence = 0.88
        elif any(token in normalized for token in ("관리인", "안내자", "caretaker", "대화", "talk")):
            action_type = ActionType.TALK
            target = "caretaker"
            confidence = 0.94
        elif any(token in normalized for token in ("휴식", "rest")):
            action_type = ActionType.REST
            confidence = 0.86
        elif any(token in normalized for token in ("횃불", "torch")):
            action_type = ActionType.USE_ITEM
            target = "torch"
            confidence = 0.84
        elif any(token in normalized for token in ("도망", "후퇴", "retreat", "flee")):
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
