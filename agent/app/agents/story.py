from __future__ import annotations

from pydantic import ValidationError

from app.config import RoleModelSettings
from app.game.models import GameState
from app.prompts.story_builder import build_story_prompts
from app.retrieval.schemas import RetrievalContext
from app.retrieval.search import RetrievalService
from app.schemas.common import Action, ActionType, EngineResult, SceneContext
from app.schemas.narrative import NarrativeRequest
from app.schemas.story import StoryActionDraft, StoryEngineResultDraft, StoryMessage, StoryTurnDraft, StoryTurnRequest, StoryTurnResponse
from app.services.file_logger import log_llm_error
from app.services.llm_client import BaseLlmClient, LlmError


class StoryAgent:
    def __init__(self, settings: RoleModelSettings, llm_client: BaseLlmClient, retrieval: RetrievalService):
        self.settings = settings
        self.llm_client = llm_client
        self.retrieval = retrieval

    def start(self, state: GameState) -> StoryTurnResponse:
        request = StoryTurnRequest(mode="opening", state=state, history=[])
        return self._render(request)

    def advance(self, state: GameState, history: list[StoryMessage], player_input: str) -> StoryTurnResponse:
        request = StoryTurnRequest(mode="turn", state=state, history=history, player_input=player_input)
        return self._render(request)

    def _render(self, request: StoryTurnRequest) -> StoryTurnResponse:
        context = self._retrieve_context(request)
        system_prompt, user_prompt = build_story_prompts(request, context)
        try:
            result = self.llm_client.generate_json(
                schema_name=f"story_{request.mode}",
                schema_model=StoryTurnDraft,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            draft = StoryTurnDraft.model_validate(result.payload)
            normalized_action = self._normalize_action(request, draft.action)
            next_state = self._merge_state(request.state, draft.state)
            response = StoryTurnResponse.model_validate(
                {
                    "narrative": draft.narrative,
                    "choices": draft.choices,
                    "state": next_state,
                    "engineResult": self._normalize_engine_result(request, draft.engine_result, normalized_action),
                    "action": normalized_action,
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
                role="story_agent",
                provider=self.settings.provider,
                model=self.settings.model,
                stage="fallback",
                error=str(error),
                extra={
                    "mode": request.mode,
                    "player_input": request.player_input,
                    "retrieval_used": context.used,
                    "retrieved_document_ids": context.document_ids,
                },
            )
            response = self._fallback(request, context, str(error))
        return self._validate(request, response)

    def _retrieve_context(self, request: StoryTurnRequest) -> RetrievalContext:
        narrative_request = NarrativeRequest(
            state_summary=request.state.summary(),
            scene_context=self._scene_context(request.state),
            engine_result=None,
            allowed_choices=[],
        )
        return self.retrieval.search_for_narrator(request.mode, narrative_request)

    def _scene_context(self, state: GameState) -> SceneContext:
        visible_targets = ["hall", "trap_room", "sanctum", "ruins_entrance", "caretaker", "torch"]
        if state.player.location_id == "collapsed_hall":
            visible_targets = ["trap_room", "ruins_entrance", "torch"]
        elif state.player.location_id == "trap_chamber":
            visible_targets = ["sanctum", "hall", "torch"]
        elif state.player.location_id == "buried_sanctum":
            visible_targets = ["trap_room", "torch"]
        return SceneContext(
            location_name=state.player.location_id.replace("_", " "),
            npcs_in_scene=["caretaker"] if state.player.location_id == "ruins_entrance" else [],
            visible_targets=visible_targets,
        )

    def _validate(self, request: StoryTurnRequest, response: StoryTurnResponse) -> StoryTurnResponse:
        if not response.narrative.strip():
            return self._fallback(request, RetrievalContext(), "empty_narrative")
        response.choices = [choice.strip() for choice in response.choices if choice.strip()][:4]
        if len(response.choices) < 2:
            fallback = self._fallback(request, RetrievalContext(), "not_enough_choices")
            fallback.safety_flags.append("not_enough_choices")
            return fallback
        expected_turn = request.state.meta.turn if request.mode == "opening" else request.state.meta.turn + 1
        response.state.meta.turn = expected_turn
        response.state.meta.seed = request.state.meta.seed
        return response

    def _fallback(self, request: StoryTurnRequest, context: RetrievalContext, reason: str) -> StoryTurnResponse:
        state = request.state.model_copy(deep=True)
        action = self._infer_action(request.player_input or "")
        if request.mode == "turn":
            state.meta.turn += 1
            self._apply_story_heuristic(state, action)
        choices = self._choices_for_state(state)
        narrative = self._narrative_for_state(request, state, action)
        engine_result = self._default_engine_result(request, action=action)
        response = StoryTurnResponse(
            narrative=narrative,
            choices=choices,
            state=state,
            engineResult=engine_result,
            action=action if request.mode == "turn" else None,
            source="story_template",
            provider=self.settings.provider,
            model=self.settings.model,
            used_fallback=True,
            retrieval_used=context.used,
            retrieved_document_ids=context.document_ids,
            safety_flags=[f"story_template_fallback:{reason}"],
        )
        return response

    def _infer_action(self, player_input: str) -> Action:
        normalized = player_input.strip().lower()
        if any(token in normalized for token in ("회랑", "hall")):
            return Action(action_type=ActionType.MOVE, target="collapsed_hall", raw_input=player_input)
        if any(token in normalized for token in ("함정방", "trap")):
            return Action(action_type=ActionType.MOVE, target="trap_chamber", raw_input=player_input)
        if any(token in normalized for token in ("성소", "제단", "sanctum", "altar")):
            return Action(action_type=ActionType.MOVE, target="buried_sanctum", raw_input=player_input)
        if any(token in normalized for token in ("입구", "돌아", "entrance")):
            return Action(action_type=ActionType.MOVE, target="ruins_entrance", raw_input=player_input)
        if any(token in normalized for token in ("관리인", "대화", "talk")):
            return Action(action_type=ActionType.TALK, target="caretaker", raw_input=player_input)
        if any(token in normalized for token in ("휴식", "rest")):
            return Action(action_type=ActionType.REST, raw_input=player_input)
        if any(token in normalized for token in ("횃불", "torch")):
            return Action(action_type=ActionType.USE_ITEM, target="torch", raw_input=player_input)
        if any(token in normalized for token in ("후퇴", "도망", "flee", "retreat")):
            return Action(action_type=ActionType.FLEE, raw_input=player_input)
        return Action(action_type=ActionType.INVESTIGATE, raw_input=player_input)

    def _normalize_action(self, request: StoryTurnRequest, action: StoryActionDraft | None) -> Action | None:
        if request.mode == "opening":
            return None
        if action is None or not action.action_type:
            return self._infer_action(request.player_input or "")
        action_type = self._coerce_action_type(action.action_type)
        return Action(
            action_type=action_type,
            target=self._normalize_target(action.target, action_type),
            raw_input=request.player_input or action.raw_input or "",
        )

    def _normalize_engine_result(
        self,
        request: StoryTurnRequest,
        draft: StoryEngineResultDraft | None,
        action: Action | None,
    ) -> EngineResult:
        if draft is None:
            return self._default_engine_result(request, action=action)
        message_code = draft.message_code or self._message_code_from_text(draft.message) or self._default_engine_result(
            request,
            action=action,
        ).message_code
        location_changed = draft.location_changed
        quest_stage_changed = draft.quest_stage_changed
        if location_changed is None:
            location_changed = bool(action and action.action_type == ActionType.MOVE)
        if quest_stage_changed is None:
            quest_stage_changed = bool(action and action.action_type == ActionType.INVESTIGATE)
        details = list(draft.details)
        if not details and action is not None:
            details = [action.action_type.value]
        return EngineResult(
            success=draft.success,
            message_code=message_code,
            location_changed=location_changed,
            quest_stage_changed=quest_stage_changed,
            ending_reached=draft.ending_reached,
            details=details,
        )

    def _coerce_action_type(self, value: str) -> ActionType:
        normalized = value.strip().upper()
        try:
            return ActionType(normalized)
        except ValueError:
            return self._infer_action(value).action_type

    def _normalize_target(self, target: str | None, action_type: ActionType) -> str | None:
        if target is None:
            return None
        normalized = target.strip().lower()
        mapping = {
            "hall": "collapsed_hall",
            "ruins_hallway": "collapsed_hall",
            "collapsed_hall": "collapsed_hall",
            "trap_room": "trap_chamber",
            "trap_chamber": "trap_chamber",
            "sanctum": "buried_sanctum",
            "buried_sanctum": "buried_sanctum",
            "altar": "buried_sanctum",
            "ruins_entrance": "ruins_entrance",
            "entrance": "ruins_entrance",
            "caretaker": "caretaker",
            "torch": "torch",
        }
        mapped = mapping.get(normalized, target)
        if action_type == ActionType.MOVE and mapped not in {
            "collapsed_hall",
            "trap_chamber",
            "buried_sanctum",
            "ruins_entrance",
        }:
            return None
        return mapped

    def _message_code_from_text(self, message: str | None) -> str | None:
        if not message:
            return None
        normalized = message.strip().lower()
        mapping = {
            "opening": "AGENT_OPENING",
            "continue": "AGENT_CONTINUE",
            "choice": "AGENT_CHOICE",
            "free_input": "AGENT_FREE_INPUT",
        }
        return mapping.get(normalized)

    def _apply_story_heuristic(self, state: GameState, action: Action) -> None:
        if action.action_type == ActionType.MOVE and action.target:
            state.player.location_id = action.target
            if action.target == "collapsed_hall":
                state.quests.sunken_ruins.stage = max(state.quests.sunken_ruins.stage, 1)
            elif action.target == "trap_chamber":
                state.quests.sunken_ruins.stage = max(state.quests.sunken_ruins.stage, 2)
            elif action.target == "buried_sanctum":
                state.quests.sunken_ruins.stage = max(state.quests.sunken_ruins.stage, 3)
        elif action.action_type == ActionType.INVESTIGATE:
            marker = f"turn_{state.meta.turn}_searched"
            if marker not in state.player.flags:
                state.player.flags.append(marker)
            state.quests.sunken_ruins.stage = min(6, state.quests.sunken_ruins.stage + 1)
        elif action.action_type == ActionType.TALK:
            state.relations.npc_affinity["caretaker"] = state.relations.npc_affinity.get("caretaker", 5) + 1
        elif action.action_type == ActionType.USE_ITEM and "torch_lit" not in state.player.flags:
            state.player.flags.append("torch_lit")

    def _merge_state(self, previous: GameState, patch: dict[str, object]) -> GameState:
        if not patch:
            return previous.model_copy(deep=True)
        merged = previous.model_dump(mode="json")
        self._deep_merge_dict(merged, patch)
        return GameState.model_validate(merged)

    def _deep_merge_dict(self, target: dict[str, object], patch: dict[str, object]) -> None:
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                self._deep_merge_dict(target[key], value)
            else:
                target[key] = value

    def _choices_for_state(self, state: GameState) -> list[str]:
        if state.player.location_id == "ruins_entrance":
            return ["주변을 조사한다", "관리인과 대화한다", "회랑으로 이동한다"]
        if state.player.location_id == "collapsed_hall":
            return ["주변을 조사한다", "함정방으로 이동한다", "입구로 돌아간다"]
        if state.player.location_id == "trap_chamber":
            return ["주변을 조사한다", "성소로 이동한다", "회랑으로 돌아간다"]
        if state.player.location_id == "buried_sanctum":
            return ["주변을 조사한다", "유물에 손을 뻗는다", "함정방으로 이동한다"]
        return ["주변을 조사한다", "입구로 돌아간다"]

    def _narrative_for_state(self, request: StoryTurnRequest, state: GameState, action: Action) -> str:
        if request.mode == "opening":
            return (
                "폐허 입구에는 축축한 밤공기와 오래 잠든 돌의 냄새가 감돈다. "
                "유적 아래로 이어지는 어둠은 아직 누구의 발걸음도 허락하지 않은 듯 고요하다."
            )
        location_names = {
            "ruins_entrance": "폐허 입구",
            "collapsed_hall": "무너진 회랑",
            "trap_chamber": "함정방",
            "buried_sanctum": "매몰된 성소",
        }
        action_label = {
            ActionType.MOVE: "발걸음을 옮기자 장면의 공기가 달라진다.",
            ActionType.TALK: "짧은 대화가 오가며 유적을 둘러싼 긴장이 조금 더 선명해진다.",
            ActionType.INVESTIGATE: "먼지와 돌 틈을 더듬자 장면의 결이 한층 또렷해진다.",
            ActionType.REST: "잠시 숨을 고르자 거칠었던 맥박이 조금 가라앉는다.",
            ActionType.USE_ITEM: "작은 불빛 하나가 어둠 속 질감을 다시 드러낸다.",
            ActionType.FLEE: "쉽게 등을 돌리지는 못했지만, 한 발 물러서며 상황을 가늠할 틈은 생겼다.",
        }.get(action.action_type, "유적은 조용히 다음 반응을 기다린다.")
        return f"{location_names.get(state.player.location_id, state.player.location_id)}. {action_label}"

    def _default_engine_result(self, request: StoryTurnRequest, action: Action | None = None) -> EngineResult:
        if request.mode == "opening":
            return EngineResult(
                success=True,
                message_code="AGENT_OPENING",
                location_changed=False,
                quest_stage_changed=False,
                ending_reached=None,
                details=["story_agent_opening"],
            )
        action_type = action.action_type.value if action else "UNKNOWN"
        return EngineResult(
            success=True,
            message_code="AGENT_CHOICE" if action and action.raw_input else "AGENT_CONTINUE",
            location_changed=bool(action and action.action_type == ActionType.MOVE),
            quest_stage_changed=bool(action and action.action_type == ActionType.INVESTIGATE),
            ending_reached=None,
            details=[action_type],
        )
