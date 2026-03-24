from __future__ import annotations

from pydantic import ValidationError

from app.config import RoleModelSettings
from app.prompts.state_manager import build_state_manager_prompts
from app.schemas.common import Action, ActionType
from app.schemas.multi_agent import (
    StoryTransitionProposalDraft,
    StoryTransitionProposalRequest,
    StoryTransitionProposalResponse,
    WorldBlueprint,
)
from app.schemas.story import StoryMessage
from app.services.file_logger import log_llm_error
from app.services.llm_client import BaseLlmClient, LlmError
from app.game.models import GameState


class StoryStateManagerAgent:
    def __init__(self, settings: RoleModelSettings, llm_client: BaseLlmClient):
        self.settings = settings
        self.llm_client = llm_client

    def propose(
        self,
        state: GameState,
        world_blueprint: WorldBlueprint,
        discovery_log: list[str],
        history: list[StoryMessage],
        intent: Action,
    ) -> StoryTransitionProposalResponse:
        request = StoryTransitionProposalRequest(
            state=state,
            world_blueprint=world_blueprint,
            discovery_log=discovery_log,
            history=history,
            intent=intent,
        )
        system_prompt, user_prompt = build_state_manager_prompts(request)
        try:
            result = self.llm_client.generate_json(
                schema_name="story_transition_proposal",
                schema_model=StoryTransitionProposalDraft,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            draft = StoryTransitionProposalDraft.model_validate(result.payload)
            return StoryTransitionProposalResponse(
                **draft.model_dump(mode="json"),
                source=f"{result.provider}_llm",
                provider=result.provider,
                model=result.model,
                used_fallback=False,
                token_usage=result.token_usage,
            )
        except (LlmError, ValidationError) as error:
            log_llm_error(
                role="state_manager",
                provider=self.settings.provider,
                model=self.settings.model,
                stage="fallback",
                error=str(error),
                extra={"intent": intent.model_dump(mode="json")},
            )
            return self._fallback(state, world_blueprint, intent, str(error))

    def _fallback(
        self,
        state: GameState,
        world_blueprint: WorldBlueprint,
        intent: Action,
        reason: str,
    ) -> StoryTransitionProposalResponse:
        state_patch: dict[str, object] = {}
        discovered: list[str] = []
        scene_summary = world_blueprint.opening_hook
        risk_tags: list[str] = [f"proposal_fallback:{reason}"]
        location_label = self._location_label(world_blueprint, state.player.location_id)

        if intent.action_type == ActionType.MOVE and intent.target:
            state_patch = {"player": {"location_id": intent.target}}
            target_label = self._location_label(world_blueprint, intent.target)
            scene_summary = f"{target_label} 쪽으로 전진하면서 {world_blueprint.core_conflict}의 징후가 조금 더 가까워진다."
        elif intent.action_type == ActionType.INVESTIGATE:
            scene_summary = f"{location_label}에서 새로운 흔적이 있는지 더 세밀하게 살핀다."
            discovered = [f"{location_label}에서 새롭게 눈에 띄는 흔적이 있는지 확인했다."]
        elif intent.action_type == ActionType.TALK:
            npc_id = self._npc_id_for_location(world_blueprint, state.player.location_id)
            if npc_id:
                affinity = state.relations.npc_affinity.get(npc_id, 5) + 1
                state_patch = {"relations": {"npc_affinity": {npc_id: affinity}}}
            discovered = ["대화 속에서 이 장소를 둘러싼 경고와 암시를 더 많이 알게 되었다."]
            scene_summary = "짧은 대화가 지나간 뒤, 상황의 긴장과 의도가 조금 더 또렷해진다."
        elif intent.action_type == ActionType.USE_ITEM:
            state_patch = {"player": {"flags": sorted(set(state.player.flags + ["torch_lit"]))}}
            scene_summary = "도구를 사용하자 숨겨져 있던 질감과 흔적이 드러난다."
        elif intent.action_type == ActionType.REST:
            state_patch = {"player": {"hp": min(100, state.player.hp + 5)}}
            scene_summary = "잠시 숨을 고르며 다음 선택을 준비한다."
        elif intent.action_type == ActionType.FLEE:
            state_patch = {"player": {"location_id": world_blueprint.starting_location_id}}
            scene_summary = "한 걸음 물러서며 지금까지의 위험을 다시 가늠한다."

        return StoryTransitionProposalResponse(
            scene_summary=scene_summary,
            state_patch=state_patch,
            discovered_facts=discovered,
            choice_candidates=self._choices_for_state(state, world_blueprint),
            risk_tags=risk_tags,
            source="state_manager_fallback",
            provider=self.settings.provider,
            model=self.settings.model,
            used_fallback=True,
        )

    def _choices_for_state(self, state: GameState, world_blueprint: WorldBlueprint) -> list[str]:
        choices: list[str] = []
        location_label = self._location_label(world_blueprint, state.player.location_id)
        choices.append(f"{location_label} 주변을 조사한다")
        for npc in world_blueprint.npcs:
            if npc.home_location_id == state.player.location_id:
                choices.append(f"{npc.label}{self._topic_particle(npc.label)} 대화한다")
                break
        current = next((location for location in world_blueprint.locations if location.id == state.player.location_id), None)
        if current:
            for connection in current.connections[:2]:
                target_label = self._location_label(world_blueprint, connection)
                choices.append(f"{target_label}{self._direction_particle(target_label)} 이동한다")
        choices.append("잠시 숨을 고르며 상황을 정리한다")
        deduped: list[str] = []
        for choice in choices:
            if choice not in deduped:
                deduped.append(choice)
        return deduped[:4]

    def _npc_id_for_location(self, world_blueprint: WorldBlueprint, location_id: str) -> str | None:
        for npc in world_blueprint.npcs:
            if npc.home_location_id == location_id:
                return npc.id
        return None

    def _location_label(self, world_blueprint: WorldBlueprint, location_id: str) -> str:
        for location in world_blueprint.locations:
            if location.id == location_id:
                return location.label
        return location_id

    def _topic_particle(self, text: str) -> str:
        if not text:
            return "와"
        last = text[-1]
        if not ("\uac00" <= last <= "\ud7a3"):
            return "와"
        return "과" if (ord(last) - ord("\uac00")) % 28 else "와"

    def _direction_particle(self, text: str) -> str:
        if not text:
            return "로"
        last = text[-1]
        if not ("\uac00" <= last <= "\ud7a3"):
            return "로"
        jong = (ord(last) - ord("\uac00")) % 28
        return "으로" if jong not in (0, 8) else "로"
