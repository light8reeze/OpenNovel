from __future__ import annotations

from dataclasses import replace
from itertools import count
from threading import Lock
from time import time_ns

from app.agents.story import StoryAgent
from app.config import RoleModelSettings
from app.game.models import (
    ActionRequest,
    ActionResponse,
    ContentBundle,
    GameState,
    StartOptions,
    StartResponse,
    StateResponse,
    TurnResult,
    initial_state,
)
from app.schemas.story import StoryMessage
from app.services.file_logger import log_game_result, log_intent_result, log_narrative_result
from app.services.llm_client import build_llm_client


class SessionNotFoundError(KeyError):
    pass


class InvalidActionRequestError(ValueError):
    pass


class SessionRecord:
    def __init__(self, state: GameState, story_agent: StoryAgent, history: list[StoryMessage], choices: list[str]):
        self.state = state
        self.story_agent = story_agent
        self.history = history
        self.choices = choices


class GameSessionService:
    def __init__(
        self,
        content: ContentBundle,
        default_story_agent: StoryAgent,
        story_agent_settings: RoleModelSettings,
    ):
        self.content = content
        self.default_story_agent = default_story_agent
        self.story_agent_settings = story_agent_settings
        self.sessions: dict[str, SessionRecord] = {}
        self.lock = Lock()
        self.counter = count(1)

    def start_game(self, options: StartOptions) -> StartResponse:
        session_id = f"session-{time_ns()}-{next(self.counter)}"
        state = initial_state()
        story_agent = self._build_session_story_agent(options)
        turn = story_agent.start(state)
        history = [StoryMessage(role="assistant", content=turn.narrative)]
        with self.lock:
            self.sessions[session_id] = SessionRecord(
                state=turn.state,
                story_agent=story_agent,
                history=history,
                choices=turn.choices,
            )
        response = StartResponse(sessionId=session_id, narrative=turn.narrative, choices=turn.choices, state=turn.state)
        log_narrative_result(
            "/game/start",
            {"mode": "opening"},
            turn.model_dump(mode="json", by_alias=True),
            context={"sessionId": session_id, "turn": 0},
        )
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
            story_agent = session.story_agent
            history = list(session.history)
        history.append(StoryMessage(role="player", content=input_text))
        turn = story_agent.advance(state, history, input_text)
        history.append(StoryMessage(role="assistant", content=turn.narrative))
        with self.lock:
            self.sessions[payload.session_id] = SessionRecord(
                state=turn.state,
                story_agent=story_agent,
                history=history,
                choices=turn.choices,
            )
        response = ActionResponse(
            narrative=turn.narrative,
            choices=turn.choices,
            engineResult=turn.engine_result,
            state=turn.state,
        )
        if turn.action is not None:
            log_intent_result(
                "/game/action",
                {"player_input": input_text},
                {
                    "action": turn.action.model_dump(mode="json"),
                    "confidence": 1.0,
                    "validation_flags": [],
                    "source": turn.source,
                    "provider": turn.provider,
                    "model": turn.model,
                    "retrieval_used": turn.retrieval_used,
                    "retrieved_document_ids": turn.retrieved_document_ids,
                },
                context={"sessionId": payload.session_id, "turn": turn.state.meta.turn},
            )
        log_narrative_result(
            "/game/action",
            {"player_input": input_text, "history_length": len(history)},
            turn.model_dump(mode="json", by_alias=True),
            context={"sessionId": payload.session_id, "turn": turn.state.meta.turn},
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
            "관리인과 대화한다",
            "함정방으로 이동한다",
            "성소로 이동한다",
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

    def _build_session_story_agent(self, options: StartOptions) -> StoryAgent:
        api_key = (options.gemini_api_key or "").strip()
        if not api_key:
            return self.default_story_agent
        model = (options.gemini_model or "").strip() or "gemini-2.5-flash"
        settings = replace(
            self.story_agent_settings,
            provider="gemini",
            model=model,
            api_key=api_key,
            base_url=self.story_agent_settings.base_url,
        )
        return StoryAgent(
            settings=settings,
            llm_client=build_llm_client(settings),
            retrieval=self.default_story_agent.retrieval,
        )

    def _game_started_engine_result(self):
        from app.schemas.common import EngineResult

        return EngineResult(
            success=True,
            message_code="AGENT_OPENING",
            location_changed=False,
            quest_stage_changed=False,
            ending_reached=None,
            details=["story_agent_opening"],
        )
