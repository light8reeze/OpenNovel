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

        if any(token in normalized for token in ("휴식", "쉰다", "rest")):
            action_type = ActionType.REST
            confidence = 0.86
        elif any(token in normalized for token in ("봉인", "재봉인", "의식", "seal")):
            action_type = ActionType.USE_ITEM
            target = next(
                (visible_target for visible_target in request.scene_context.visible_targets if self._matches_label(normalized, visible_target)),
                None,
            )
            confidence = 0.88
        elif any(token in normalized for token in ("횃불", "torch", "등불", "lamp")):
            action_type = ActionType.USE_ITEM
            target = "횃불"
            confidence = 0.84
        elif any(token in normalized for token in ("도망", "후퇴", "retreat", "flee")):
            action_type = ActionType.FLEE
            confidence = 0.83
        elif any(self._matches_label(normalized, npc) for npc in request.scene_context.npcs_in_scene) or any(
            token in normalized for token in ("대화", "말을 건다", "talk")
        ):
            action_type = ActionType.TALK
            target = request.scene_context.npcs_in_scene[0] if request.scene_context.npcs_in_scene else None
            confidence = 0.94
        else:
            for visible_target in request.scene_context.visible_targets:
                if self._matches_label(normalized, visible_target):
                    action_type = ActionType.MOVE
                    target = visible_target
                    confidence = 0.9
                    break

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

    def _matches_label(self, normalized_input: str, label: str) -> bool:
        lowered = label.lower()
        if lowered in normalized_input:
            return True
        parts = [part for part in lowered.replace("(", " ").replace(")", " ").replace("-", " ").split() if len(part) >= 2]
        return any(part in normalized_input for part in parts)
