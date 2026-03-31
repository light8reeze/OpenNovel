from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import count
from threading import Lock
from time import time_ns

from app.agents.intender import IntenderAgent
from app.agents.narrator import NarratorAgent
from app.agents.state_manager import StoryStateManagerAgent
from app.agents.world_builder import WorldBuilderAgent
from app.config import RoleModelSettings
from app.game.models import (
    ActionRequest,
    ActionResponse,
    ChoicesResponse,
    ContentBundle,
    GameState,
    StartOptions,
    StartResponse,
    ThemePack,
    StateResponse,
    TurnResult,
)
from app.schemas.common import Action, ActionType, SceneContext
from app.schemas.intent import IntentValidationRequest, IntentValidationResponse
from app.schemas.multi_agent import ValidationResult, WorldBlueprint, WorldNpc
from app.schemas.narrative import NarrativeRequest
from app.schemas.story import StoryMessage
from app.schemas.story_setup import StorySetup
from app.services.file_logger import (
    log_game_result,
    log_intent_result,
    log_narrative_result,
    log_stage_result,
)
from app.services.llm_client import build_llm_client
from app.services.validator import RuleValidator


class SessionNotFoundError(KeyError):
    pass


class InvalidActionRequestError(ValueError):
    pass


@dataclass
class SessionAgents:
    intender: IntenderAgent
    narrator: NarratorAgent
    world_builder: WorldBuilderAgent
    state_manager: StoryStateManagerAgent


class SessionRecord:
    def __init__(
        self,
        state: GameState,
        agents: SessionAgents,
        history: list[StoryMessage],
        choices: list[str],
        story_setup: StorySetup,
        world_blueprint: WorldBlueprint,
        discovery_log: list[str],
    ):
        self.state = state
        self.agents = agents
        self.history = history
        self.choices = choices
        self.story_setup = story_setup
        self.world_blueprint = world_blueprint
        self.discovery_log = discovery_log


class GameSessionService:
    def __init__(
        self,
        content: ContentBundle,
        default_intender: IntenderAgent,
        default_narrator: NarratorAgent,
        default_world_builder: WorldBuilderAgent,
        default_state_manager: StoryStateManagerAgent,
        agent_settings: RoleModelSettings,
        validator: RuleValidator,
        story_setups: list[StorySetup],
        story_setup_source: str,
    ):
        self.content = content
        self.default_agents = SessionAgents(
            intender=default_intender,
            narrator=default_narrator,
            world_builder=default_world_builder,
            state_manager=default_state_manager,
        )
        self.agent_settings = agent_settings
        self.validator = validator
        self.story_setups = list(story_setups)
        self.story_setup_source = story_setup_source
        self.sessions: dict[str, SessionRecord] = {}
        self.lock = Lock()
        self.counter = count(1)

    def start_game(self, options: StartOptions) -> StartResponse:
        seed = time_ns() % 2_147_483_647
        session_id = f"session-{seed}-{next(self.counter)}"
        agents = self._build_session_agents(options)
        story_setup = self._select_story_setup(options.story_setup_id)
        world_build = agents.world_builder.build(story_setup)
        themed_blueprint = self._apply_theme_pack(world_build.blueprint, self._select_theme_pack(seed))
        themed_world_build = world_build.model_copy(update={"blueprint": themed_blueprint})
        initial_validation = self.validator.initialize_world(themed_blueprint, seed=seed)
        opening_request = NarrativeRequest(
            state_summary=initial_validation.state.summary(),
            scene_context=self._scene_context(initial_validation.state, themed_blueprint),
            engine_result=initial_validation.engine_result,
            allowed_choices=initial_validation.allowed_choices,
            scene_summary=initial_validation.scene_summary,
            progress_kind=initial_validation.progress_kind,
            discovery_log=initial_validation.discovery_log,
            world_title=themed_blueprint.title,
            world_summary=themed_blueprint.world_summary,
            world_tone=themed_blueprint.tone,
            player_goal=themed_blueprint.player_goal,
            opening_hook=themed_blueprint.opening_hook,
        )
        opening = agents.narrator.render_opening(opening_request)
        history = [StoryMessage(role="assistant", content=opening.narrative)]
        with self.lock:
            self.sessions[session_id] = SessionRecord(
                state=initial_validation.state,
                agents=agents,
                history=history,
                choices=opening.choices,
                story_setup=story_setup,
                world_blueprint=themed_blueprint,
                discovery_log=list(initial_validation.discovery_log),
            )
        response = StartResponse(
            sessionId=session_id,
            narrative=opening.narrative,
            choices=[],
            state=initial_validation.state,
            storySetupId=story_setup.id,
        )
        log_stage_result(
            "world_build",
            "/game/start",
            {"storySetupId": story_setup.id},
            themed_world_build.model_dump(mode="json"),
            context={"sessionId": session_id, "turn": 0},
        )
        log_stage_result(
            "validation",
            "/game/start",
            {
                "storySetupId": story_setup.id,
                "worldBlueprintId": themed_blueprint.id,
            },
            initial_validation.model_dump(mode="json"),
            context={"sessionId": session_id, "turn": 0},
        )
        log_narrative_result(
            "/game/start",
            {"mode": "opening", "storySetupId": story_setup.id},
            opening.model_dump(mode="json", by_alias=True),
            context={"sessionId": session_id, "turn": 0},
        )
        log_game_result(
            "/game/start",
            {
                "sessionId": session_id,
                "geminiModel": options.gemini_model,
                "hasGeminiKey": bool(options.gemini_api_key),
                "storySetupId": story_setup.id,
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
            agents = session.agents
            history = list(session.history)
            story_setup = session.story_setup
            world_blueprint = session.world_blueprint
            discovery_log = list(session.discovery_log)
            current_choices = list(session.choices)
        history.append(StoryMessage(role="player", content=input_text))
        intent_request = IntentValidationRequest(
            player_input=input_text,
            allowed_actions=self._allowed_actions_for_state(state, world_blueprint),
            state_summary=state.summary(),
            scene_context=self._scene_context(state, world_blueprint),
        )
        intent = self._intent_from_choice(payload, current_choices, state, world_blueprint) or agents.intender.handle(intent_request)
        proposal = agents.state_manager.propose(state, world_blueprint, discovery_log, history, intent.action)
        validation = self.validator.validate_transition(
            state=state,
            world_blueprint=world_blueprint,
            discovery_log=discovery_log,
            intent=intent.action,
            proposal_summary=proposal.scene_summary,
            proposal_patch=proposal.state_patch,
            proposal_choices=proposal.choice_candidates,
            proposed_facts=proposal.discovered_facts,
            risk_tags=proposal.risk_tags,
        )
        narrative_request = NarrativeRequest(
            state_summary=validation.state.summary(),
            scene_context=self._scene_context(validation.state, world_blueprint),
            engine_result=validation.engine_result,
            allowed_choices=validation.allowed_choices,
            scene_summary=validation.scene_summary,
            progress_kind=validation.progress_kind,
            discovery_log=validation.discovery_log,
            world_title=world_blueprint.title,
            world_summary=world_blueprint.world_summary,
            world_tone=world_blueprint.tone,
            player_goal=world_blueprint.player_goal,
            opening_hook=world_blueprint.opening_hook,
        )
        narrative = agents.narrator.render_turn(narrative_request)
        history.append(StoryMessage(role="assistant", content=narrative.narrative))
        with self.lock:
            self.sessions[payload.session_id] = SessionRecord(
                state=validation.state,
                agents=agents,
                history=history,
                choices=narrative.choices,
                story_setup=story_setup,
                world_blueprint=world_blueprint,
                discovery_log=validation.discovery_log,
            )
        response = ActionResponse(
            narrative=narrative.narrative,
            choices=[],
            engineResult=validation.engine_result,
            state=validation.state,
            storySetupId=story_setup.id,
        )
        log_intent_result(
            "/game/action",
            {"player_input": input_text, "storySetupId": story_setup.id, "currentChoices": current_choices},
            intent.model_dump(mode="json"),
            context={"sessionId": payload.session_id, "turn": validation.state.meta.turn},
        )
        log_stage_result(
            "state_proposal",
            "/game/action",
            {
                "player_input": input_text,
                "storySetupId": story_setup.id,
                "worldBlueprintId": world_blueprint.id,
            },
            proposal.model_dump(mode="json"),
            context={"sessionId": payload.session_id, "turn": validation.state.meta.turn},
        )
        log_stage_result(
            "validation",
            "/game/action",
            {
                "player_input": input_text,
                "intent": intent.action.model_dump(mode="json"),
            },
            validation.model_dump(mode="json"),
            context={"sessionId": payload.session_id, "turn": validation.state.meta.turn},
        )
        log_narrative_result(
            "/game/action",
            {"player_input": input_text, "history_length": len(history), "storySetupId": story_setup.id},
            narrative.model_dump(mode="json", by_alias=True),
            context={"sessionId": payload.session_id, "turn": validation.state.meta.turn},
        )
        log_game_result(
            "/game/action",
            payload.model_dump(mode="json", by_alias=True),
            response.model_dump(mode="json", by_alias=True),
            context={"sessionId": payload.session_id, "turn": validation.state.meta.turn},
        )
        return response

    def get_state(self, session_id: str) -> StateResponse:
        with self.lock:
            session = self.sessions.get(session_id)
            if session is None:
                raise SessionNotFoundError(session_id)
            state = session.state
            story_setup_id = session.story_setup.id
        response = StateResponse(state=state, storySetupId=story_setup_id)
        log_game_result("/game/state", {"sessionId": session_id}, response.model_dump(mode="json"))
        return response

    def get_choices(self, session_id: str) -> ChoicesResponse:
        with self.lock:
            session = self.sessions.get(session_id)
            if session is None:
                raise SessionNotFoundError(session_id)
            response = ChoicesResponse(
                sessionId=session_id,
                choices=list(session.choices),
                storySetupId=session.story_setup.id,
            )
        log_game_result("/game/choices", {"sessionId": session_id}, response.model_dump(mode="json", by_alias=True))
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

    def _build_session_agents(self, options: StartOptions) -> SessionAgents:
        api_key = (options.gemini_api_key or "").strip()
        if not api_key:
            return self.default_agents
        model = (options.gemini_model or "").strip() or "gemini-2.5-flash"
        settings = replace(
            self.agent_settings,
            provider="gemini",
            model=model,
            api_key=api_key,
            base_url=self.agent_settings.base_url,
        )
        llm_client = build_llm_client(settings)
        return SessionAgents(
            intender=IntenderAgent(settings=settings, llm_client=llm_client, retrieval=self.default_agents.intender.retrieval),
            narrator=NarratorAgent(settings=settings, llm_client=llm_client, retrieval=self.default_agents.narrator.retrieval),
            world_builder=WorldBuilderAgent(settings=settings, llm_client=llm_client),
            state_manager=StoryStateManagerAgent(settings=settings, llm_client=llm_client),
        )

    def available_story_setups(self) -> tuple[list[StorySetup], str]:
        return list(self.story_setups), self.story_setup_source

    def _select_story_setup(self, story_setup_id: str | None) -> StorySetup:
        if story_setup_id:
            for preset in self.story_setups:
                if preset.id == story_setup_id:
                    return preset
        return self.story_setups[0]

    def _select_theme_pack(self, seed: int) -> ThemePack | None:
        if not self.content.theme_packs:
            return None
        return self.content.theme_packs[seed % len(self.content.theme_packs)]

    def _apply_theme_pack(self, world_blueprint: WorldBlueprint, theme_pack: ThemePack | None) -> WorldBlueprint:
        if theme_pack is None:
            return world_blueprint
        themed = world_blueprint.model_copy(deep=True)
        themed.theme_id = theme_pack.id
        themed.theme_rules = list(theme_pack.rules)
        themed.objective_label = "던전의 핵심 대상을 원하는 방식으로 해결한다."
        themed.npcs = self._build_theme_npcs(world_blueprint, theme_pack)
        themed.important_npcs = [npc.label for npc in themed.npcs]
        return themed

    def _intent_from_choice(
        self,
        payload: ActionRequest,
        current_choices: list[str],
        state: GameState,
        world_blueprint: WorldBlueprint,
    ) -> IntentValidationResponse | None:
        if not payload.choice_text:
            return None
        choice_text = payload.choice_text.strip()
        if not choice_text or choice_text not in current_choices:
            return None

        location = self._world_location(world_blueprint, state.player.location_id)
        current_label = self._world_location_name(state.player.location_id, world_blueprint)

        if "횃불" in choice_text:
            action = Action(action_type=ActionType.USE_ITEM, target="횃불", raw_input=choice_text)
        elif "잠시 숨을 고르" in choice_text or "상황을 정리" in choice_text:
            action = Action(action_type=ActionType.REST, raw_input=choice_text)
        elif "조사" in choice_text:
            action = Action(action_type=ActionType.INVESTIGATE, target=current_label, raw_input=choice_text)
        elif "대화" in choice_text:
            target = next(
                (
                    npc.label
                    for npc in self._current_npcs(world_blueprint, state.player.location_id)
                    if choice_text.startswith(f"{npc.label}{self.validator._topic_particle(npc.label)}")
                    or choice_text.startswith(npc.label)
                ),
                None,
            )
            action = Action(action_type=ActionType.TALK, target=target, raw_input=choice_text)
        elif "이동한다" in choice_text:
            target = None
            if location:
                for connection in location.connections:
                    label = self._world_location_name(connection, world_blueprint)
                    if choice_text.startswith(f"{label}{self.validator._direction_particle(label)} 이동한다"):
                        target = label
                        break
            action = Action(action_type=ActionType.MOVE, target=target, raw_input=choice_text)
        else:
            return None

        return IntentValidationResponse(
            action=action,
            confidence=1.0,
            validation_flags=["choice_exact_match"],
            source="choice_match",
        )

    def _build_theme_npcs(self, world_blueprint: WorldBlueprint, theme_pack: ThemePack) -> list[WorldNpc]:
        if not theme_pack.npc_roles or not world_blueprint.npcs:
            return world_blueprint.npcs
        npcs: list[WorldNpc] = []
        last_index = max(0, len(world_blueprint.locations) - 1)
        for index, base_npc in enumerate(world_blueprint.npcs):
            role = theme_pack.npc_roles[min(index, len(theme_pack.npc_roles) - 1)]
            location_index = role.location_index if role.location_index >= 0 else last_index
            location_index = min(max(location_index, 0), last_index)
            npcs.append(
                WorldNpc(
                    id=base_npc.id,
                    label=base_npc.label,
                    home_location_id=world_blueprint.locations[location_index].id,
                    role=role.role or base_npc.role,
                    interaction_hint=role.interaction_hint or base_npc.interaction_hint,
                )
            )
        return npcs

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

    def _scene_context(self, state: GameState, world_blueprint: WorldBlueprint) -> SceneContext:
        current_location = self._world_location(world_blueprint, state.player.location_id)
        visible_targets = []
        if current_location:
            visible_targets.extend(self._world_location_name(target_id, world_blueprint) for target_id in current_location.connections[:3])
        visible_targets.extend(npc.label for npc in self._current_npcs(world_blueprint, state.player.location_id)[:2])
        visible_targets.extend(self._theme_visible_targets(state))
        visible_targets.append("횃불")
        location_name = self._world_location_name(state.player.location_id, world_blueprint)
        npcs = [npc.label for npc in self._current_npcs(world_blueprint, state.player.location_id)]
        return SceneContext(
            location_name=location_name,
            npcs_in_scene=npcs,
            visible_targets=[target for target in visible_targets if target],
        )

    def _world_location_name(self, location_id: str, world_blueprint: WorldBlueprint) -> str:
        location = self._world_location(world_blueprint, location_id)
        return location.label if location else self.content.location_name(location_id)

    def _primary_npc_label(self, world_blueprint: WorldBlueprint) -> str:
        if world_blueprint.npcs:
            return world_blueprint.npcs[0].label
        return "안내자"

    def _allowed_actions_for_state(self, state: GameState, world_blueprint: WorldBlueprint):
        from app.schemas.common import ActionType

        actions = [ActionType.MOVE, ActionType.INVESTIGATE, ActionType.REST, ActionType.USE_ITEM, ActionType.FLEE]
        if self._current_npcs(world_blueprint, state.player.location_id):
            actions.insert(1, ActionType.TALK)
        return actions

    def _theme_visible_targets(self, state: GameState) -> list[str]:
        if state.objective.status == "completed":
            return []
        if not state.world.theme_id:
            return []
        for theme_pack in self.content.theme_packs:
            if theme_pack.id == state.world.theme_id:
                return [path.label for path in theme_pack.victory_paths]
        return []

    def _display_npc_label(self, value: str) -> str:
        if not value:
            return ""
        if any("\uac00" <= char <= "\ud7a3" for char in value):
            return value
        mapping = {
            "caretaker": "관리인",
            "village_chief": "촌장",
            "chief": "촌장",
            "shaman": "무당",
            "old_miner": "늙은 광부",
            "grieving_mother": "상복 입은 어머니",
            "court_lady": "상궁",
            "royal_guard": "수문장",
            "investigator": "감찰관",
            "smuggler": "밀수업자",
            "outpost_commander": "주둔지 대장",
            "scout": "정찰병",
        }
        return mapping.get(value.lower(), "주요 인물")

    def _display_location_label(self, value: str, default: str) -> str:
        if not value:
            return default
        if any("\uac00" <= char <= "\ud7a3" for char in value):
            return value
        mapping = {
            "ruins_entrance": "입구",
            "entrance": "입구",
            "village_center": "마을 중심부",
            "shaman_hut": "무당의 오두막",
            "old_mine": "폐광 입구",
            "forgotten_shrine": "잊힌 성소",
            "collapsed_hall": "회랑",
            "hall": "회랑",
            "trap_chamber": "함정방",
            "trap_room": "함정방",
            "buried_sanctum": "지하 성소",
            "sanctum": "지하 성소",
        }
        return mapping.get(value.lower(), default)

    def _world_location(self, world_blueprint: WorldBlueprint, location_id: str):
        return next((location for location in world_blueprint.locations if location.id == location_id), None)

    def _current_npcs(self, world_blueprint: WorldBlueprint, location_id: str):
        return [npc for npc in world_blueprint.npcs if npc.home_location_id == location_id]
