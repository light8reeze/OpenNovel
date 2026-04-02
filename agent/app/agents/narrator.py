from __future__ import annotations

from pydantic import ValidationError

from app.config import RoleModelSettings
from app.prompts.narrative_builder import build_narrative_prompts
from app.retrieval.schemas import RetrievalContext
from app.retrieval.search import RetrievalService
from app.schemas.narrative import NarrativeLlmResponse, NarrativeRequest, NarrativeResponse
from app.services.fallback_renderer import render_opening, render_turn
from app.services.file_logger import log_llm_error
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
                schema_model=NarrativeLlmResponse,
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
                    "token_usage": result.token_usage.model_dump(mode="json") if result.token_usage else None,
                }
            )
        except (LlmError, ValidationError) as error:
            log_llm_error(
                role="narrator",
                provider=self.settings.provider,
                model=self.settings.model,
                stage="fallback",
                error=str(error),
                extra={
                    "kind": kind,
                    "message_code": request.engine_result.message_code if request.engine_result else "GAME_STARTED",
                    "retrieval_used": context.used,
                    "retrieved_document_ids": context.document_ids,
                },
            )
            response = self._fallback(kind, request, context, str(error))
        return self._validate(kind, response, request)

    def _retrieve_context(self, kind: str, request: NarrativeRequest) -> RetrievalContext:
        return self.retrieval.search_for_narrator(kind, request)

    def _validate(self, kind: str, response: NarrativeResponse, request: NarrativeRequest) -> NarrativeResponse:
        allowed_choices = [choice.strip() for choice in request.allowed_choices if isinstance(choice, str) and choice.strip()]
        if request.engine_result and request.engine_result.message_code == "OBJECTIVE_COMPLETED":
            response.narrative = self._ending_narrative(request)
            response.choices = []
            return response

        response.choices = allowed_choices[:6]
        if not response.narrative.strip():
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

    def _ending_narrative(self, request: NarrativeRequest) -> str:
        ending = request.engine_result.ending_reached if request.engine_result else None
        location_name = request.scene_context.location_name or "이 장소"
        endings = {
            "sealed": (
                f"{location_name}에 들끓던 의식의 맥이 마침내 가라앉는다. "
                "횃불 아래 흔들리던 기운은 서서히 봉합되고, 우물 안을 파고들던 속삭임도 힘을 잃는다. "
                "상처와 대가는 남았지만, 당신은 끝내 의식을 봉합해 마을을 붙들던 균열을 닫아냈다."
            ),
            "recovered": (
                f"{location_name}에 얽혀 있던 기억의 결이 한꺼번에 되돌아온다. "
                "흩어져 있던 단서와 공포가 하나의 진실로 묶이며, 당신은 실종과 맹세의 전말을 스스로 회수한다. "
                "잃어버린 기억을 되찾은 순간, 이 세계를 붙들던 오래된 거짓도 함께 무너진다."
            ),
            "bargained": (
                f"{location_name}에 남은 기운과 마주 선 당신은 끝내 새로운 조건을 끌어낸다. "
                "위협만 남아 있던 거래는 다시 쓰이고, 기억의 대가도 더는 예전과 같은 방식으로 요구되지 않는다. "
                "당신은 산신과의 재협상을 성사시키며 이 이야기의 결말을 스스로 바꿔 놓았다."
            ),
        }
        return endings.get(
            ending,
            f"{location_name}에서 마침내 갈등의 결말이 확정된다. 당신은 끝내 이 장면을 돌파하고 이야기를 매듭지었다.",
        )
