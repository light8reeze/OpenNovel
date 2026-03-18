from __future__ import annotations

from dataclasses import replace
from itertools import count
from threading import Lock
from time import time_ns

from app.agents.intender import IntenderAgent
from app.agents.narrator import NarratorAgent
from app.config import RoleModelSettings
from app.game.engine import (
    allowed_actions_for_state,
    choices_for_state,
    heuristic_parse_action,
    resolve_action_input,
    visible_targets_for_state,
)
from app.game.models import (
    ActionRequest,
    ActionResponse,
    ContentBundle,
    GameState,
    Resolution,
    StartOptions,
    StartResponse,
    StateResponse,
    TurnResult,
    initial_state,
)
from app.schemas.common import Action, SceneContext
from app.schemas.intent import IntentValidationRequest
from app.schemas.narrative import NarrativeRequest
from app.services.file_logger import log_game_result, log_intent_result, log_narrative_result
from app.services.llm_client import build_llm_client


class SessionNotFoundError(KeyError):
    pass


class InvalidActionRequestError(ValueError):
    pass


class SessionRecord:
    def __init__(self, state: GameState, narrator: NarratorAgent):
        self.state = state
        self.narrator = narrator


class GameSessionService:
    def __init__(
        self,
        content: ContentBundle,
        intender: IntenderAgent,
        default_narrator: NarratorAgent,
        narrator_settings: RoleModelSettings,
    ):
        self.content = content
        self.intender = intender
        self.default_narrator = default_narrator
        self.narrator_settings = narrator_settings
        self.sessions: dict[str, SessionRecord] = {}
        self.lock = Lock()
        self.counter = count(1)

    def start_game(self, options: StartOptions) -> StartResponse:
        session_id = f"session-{time_ns()}-{next(self.counter)}"
        state = initial_state()
        narrator = self._build_session_narrator(options)
        turn = self._build_opening_turn(state, narrator, session_id=session_id)
        with self.lock:
            self.sessions[session_id] = SessionRecord(state=state, narrator=narrator)
        response = StartResponse(sessionId=session_id, narrative=turn.narrative, choices=turn.choices, state=turn.state)
        log_game_result(
            "/game/start",
            {
                "sessionId": session_id,
                "geminiModel": options.gemini_model,
                "hasGeminiKey": bool(options.gemini_api_key),
            },
            response.model_dump(mode="json", by_alias=True),
            context={"sessionId": session_id, "turn": 0},
        )
        return response

    def apply_action(self, payload: ActionRequest) -> ActionResponse:
        input_text = self._coerce_input(payload)
        with self.lock:
            session = self.sessions.get(payload.session_id)
            if session is None:
                raise SessionNotFoundError(payload.session_id)
            state = session.state
            narrator = session.narrator
        next_turn = state.meta.turn + 1
        resolution = self._resolve_player_input(
            state,
            input_text,
            session_id=payload.session_id,
            turn=next_turn,
        )
        turn = self._build_turn(resolution, narrator, session_id=payload.session_id)
        with self.lock:
            self.sessions[payload.session_id] = SessionRecord(state=turn.state, narrator=narrator)
        response = ActionResponse(
            narrative=turn.narrative,
            choices=turn.choices,
            engineResult=turn.engine_result,
            state=turn.state,
        )
        log_game_result(
            "/game/action",
            payload.model_dump(mode="json", by_alias=True),
            response.model_dump(mode="json", by_alias=True),
            context={"sessionId": payload.session_id, "turn": turn.state.meta.turn},
        )
        return response

    def get_state(self, session_id: str) -> StateResponse:
        with self.lock:
            session = self.sessions.get(session_id)
            if session is None:
                raise SessionNotFoundError(session_id)
            state = session.state
        response = StateResponse(state=state)
        log_game_result("/game/state", {"sessionId": session_id}, response.model_dump(mode="json"))
        return response

    def demo_script(self) -> list[TurnResult]:
        response = self.start_game(StartOptions())
        session_id = response.session_id
        turns = [
            TurnResult(
                narrative=response.narrative,
                choices=response.choices,
                state=response.state,
                engine_result=self._game_started_engine_result(),
            )
        ]
        for input_text in [
            "주변을 조사한다",
            "회랑으로 이동한다",
            "주변을 조사한다",
            "함정방으로 이동한다",
            "주변을 조사한다",
            "성소로 이동한다",
            "주변을 조사한다",
            "주변을 조사한다",
            "함정방으로 이동한다",
            "회랑으로 돌아간다",
            "입구로 돌아간다",
            "주변을 조사한다",
        ]:
            action_response = self.apply_action(ActionRequest(sessionId=session_id, inputText=input_text))
            turns.append(
                TurnResult(
                    narrative=action_response.narrative,
                    choices=action_response.choices,
                    state=action_response.state,
                    engine_result=action_response.engine_result,
                )
            )
        return turns

    def _coerce_input(self, payload: ActionRequest) -> str:
        if payload.input_text and payload.choice_text:
            raise InvalidActionRequestError("inputText and choiceText cannot both be set")
        if payload.input_text:
            return payload.input_text
        if payload.choice_text:
            return payload.choice_text
        raise InvalidActionRequestError("one of inputText or choiceText is required")

    def _resolve_player_input(self, state: GameState, input_text: str, session_id: str, turn: int) -> Resolution:
        request = IntentValidationRequest(
            player_input=input_text,
            allowed_actions=allowed_actions_for_state(state),
            state_summary=state.summary(),
            scene_context=self._scene_context(state),
        )
        fallback = heuristic_parse_action(input_text)
        response = self.intender.handle(request)
        log_intent_result(
            "/game/action",
            request.model_dump(mode="json"),
            response.model_dump(mode="json"),
            context={"sessionId": session_id, "turn": turn},
        )
        if "action_not_allowed" in response.validation_flags or "target_not_visible" in response.validation_flags:
            action = fallback
        else:
            action = Action.model_validate(response.action.model_dump(mode="json"))
        return resolve_action_input(state, self.content, action)

    def _build_opening_turn(self, state: GameState, narrator: NarratorAgent, session_id: str) -> TurnResult:
        request = NarrativeRequest(
            state_summary=state.summary(),
            scene_context=self._scene_context(state),
            engine_result=None,
            allowed_choices=choices_for_state(state),
        )
        response = narrator.render_opening(request)
        log_narrative_result(
            "/game/start",
            request.model_dump(mode="json"),
            response.model_dump(mode="json"),
            context={"sessionId": session_id, "turn": 0},
        )
        return TurnResult(
            narrative=response.narrative,
            choices=response.choices,
            state=state,
            engine_result=self._game_started_engine_result(),
        )

    def _build_turn(self, resolution: Resolution, narrator: NarratorAgent, session_id: str) -> TurnResult:
        request = NarrativeRequest(
            state_summary=resolution.next_state.summary(),
            scene_context=self._scene_context(resolution.next_state),
            engine_result=resolution.engine_result,
            allowed_choices=choices_for_state(resolution.next_state),
        )
        response = narrator.render_turn(request)
        log_narrative_result(
            "/game/action",
            request.model_dump(mode="json"),
            response.model_dump(mode="json"),
            context={"sessionId": session_id, "turn": resolution.next_state.meta.turn},
        )
        return TurnResult(
            narrative=response.narrative,
            choices=response.choices,
            state=resolution.next_state,
            engine_result=resolution.engine_result,
        )

    def _scene_context(self, state: GameState) -> SceneContext:
        return SceneContext(
            location_name=self.content.location_name(state.player.location_id),
            npcs_in_scene=self._npcs_in_scene(state),
            visible_targets=visible_targets_for_state(state),
        )

    def _npcs_in_scene(self, state: GameState) -> list[str]:
        if state.player.location_id == "ruins_entrance":
            return ["caretaker"]
        return []

    def _build_session_narrator(self, options: StartOptions) -> NarratorAgent:
        api_key = (options.gemini_api_key or "").strip()
        if not api_key:
            return self.default_narrator
        model = (options.gemini_model or "").strip() or "gemini-2.5-flash"
        settings = replace(
            self.narrator_settings,
            provider="gemini",
            model=model,
            api_key=api_key,
            base_url=self.narrator_settings.base_url,
        )
        return NarratorAgent(settings=settings, llm_client=build_llm_client(settings), retrieval=self.default_narrator.retrieval)

    def _game_started_engine_result(self):
        from app.schemas.common import EngineResult

        return EngineResult(
            success=True,
            message_code="GAME_STARTED",
            location_changed=False,
            quest_stage_changed=False,
            ending_reached=None,
            details=["session_started"],
        )
