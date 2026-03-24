from __future__ import annotations

from copy import deepcopy

from app.game.models import ContentBundle, GameState, initial_state
from app.schemas.common import Action, ActionType, EngineResult
from app.schemas.multi_agent import ValidationResult, WorldBlueprint, WorldLocation, WorldNpc


class RuleValidator:
    def __init__(self, content: ContentBundle):
        self.content = content

    def initialize_world(self, blueprint: WorldBlueprint) -> ValidationResult:
        state = initial_state()
        state.player.location_id = self._normalize_location_id(blueprint, blueprint.starting_location_id) or blueprint.starting_location_id
        if blueprint.world_summary:
            state.world.global_flags.append(f"world:{blueprint.id}")
        state.world.alert_by_region = {blueprint.id[:24]: min(10, max(1, len(blueprint.locations)))}
        for npc in blueprint.npcs:
            state.relations.npc_affinity.setdefault(npc.id, 5)
        return ValidationResult(
            state=state,
            engine_result=EngineResult(
                success=True,
                message_code="WORLD_INITIALIZED",
                location_changed=False,
                quest_stage_changed=False,
                ending_reached=None,
                details=["world_initialized"],
            ),
            allowed_choices=self._choices_for_state(state, blueprint),
            discovery_log=[],
            scene_summary=blueprint.opening_hook,
            validation_flags=[],
            source="validator",
        )

    def validate_transition(
        self,
        state: GameState,
        world_blueprint: WorldBlueprint,
        discovery_log: list[str],
        intent: Action,
        proposal_summary: str,
        proposal_patch: dict[str, object],
        proposal_choices: list[str],
        proposed_facts: list[str],
        risk_tags: list[str],
    ) -> ValidationResult:
        next_state = state.model_copy(deep=True)
        next_state.meta.turn = state.meta.turn + 1
        next_state.meta.seed = state.meta.seed
        validation_flags: list[str] = []
        self._apply_validated_patch(next_state, world_blueprint, proposal_patch, intent, validation_flags)
        allowed_choices = self._sanitize_choices(next_state, world_blueprint, proposal_choices)
        if len(allowed_choices) < 2:
            validation_flags.append("validator_regenerated_choices")
            allowed_choices = self._choices_for_state(next_state, world_blueprint)
        next_discovery = self._merge_discovery(discovery_log, proposed_facts)
        if risk_tags:
            validation_flags.extend([tag for tag in risk_tags if tag not in validation_flags])
        engine_result = self._engine_result_for(state, next_state, intent, validation_flags)
        scene_summary = proposal_summary.strip() or world_blueprint.opening_hook
        return ValidationResult(
            state=next_state,
            engine_result=engine_result,
            allowed_choices=allowed_choices,
            discovery_log=next_discovery,
            scene_summary=scene_summary,
            validation_flags=validation_flags,
            source="validator",
        )

    def _apply_validated_patch(
        self,
        state: GameState,
        world_blueprint: WorldBlueprint,
        patch: dict[str, object],
        intent: Action,
        validation_flags: list[str],
    ) -> None:
        player_patch = patch.get("player") if isinstance(patch, dict) else None
        if isinstance(player_patch, dict):
            location_id = self._normalize_location_id(world_blueprint, player_patch.get("location_id"))
            if location_id:
                if self._is_valid_move_target(world_blueprint, state.player.location_id, location_id):
                    state.player.location_id = location_id
                else:
                    validation_flags.append("invalid_location_patch")
            hp = player_patch.get("hp")
            if isinstance(hp, int):
                state.player.hp = max(1, min(100, hp))
            gold = player_patch.get("gold")
            if isinstance(gold, int):
                state.player.gold = max(0, gold)
            flags = player_patch.get("flags")
            if isinstance(flags, list):
                state.player.flags = [str(flag) for flag in flags][:16]

        quest_patch = patch.get("quests") if isinstance(patch, dict) else None
        if isinstance(quest_patch, dict):
            story_arc = quest_patch.get("story_arc")
            if isinstance(story_arc, dict):
                stage = story_arc.get("stage")
                if isinstance(stage, int):
                    state.quests.story_arc.stage = max(0, min(6, stage))

        relations_patch = patch.get("relations") if isinstance(patch, dict) else None
        if isinstance(relations_patch, dict):
            affinity = relations_patch.get("npc_affinity")
            if isinstance(affinity, dict):
                merged = deepcopy(state.relations.npc_affinity)
                for key, value in affinity.items():
                    if isinstance(value, int):
                        merged[str(key)] = max(0, min(10, value))
                state.relations.npc_affinity = merged

        self._apply_intent_defaults(state, world_blueprint, intent)

    def _apply_intent_defaults(self, state: GameState, world_blueprint: WorldBlueprint, intent: Action) -> None:
        normalized_target = self._normalize_location_id(world_blueprint, intent.target)
        if intent.action_type == ActionType.MOVE and normalized_target and self._is_valid_move_target(
            world_blueprint, state.player.location_id, normalized_target
        ):
            state.player.location_id = normalized_target
        elif intent.action_type == ActionType.INVESTIGATE:
            state.quests.story_arc.stage = min(6, state.quests.story_arc.stage + 1)
        elif intent.action_type == ActionType.TALK:
            npc_id = self._normalize_npc_id(world_blueprint, intent.target)
            if npc_id:
                state.relations.npc_affinity[npc_id] = min(10, state.relations.npc_affinity.get(npc_id, 5) + 1)
        elif intent.action_type == ActionType.USE_ITEM and "torch_lit" not in state.player.flags:
            state.player.flags.append("torch_lit")
        elif intent.action_type == ActionType.REST:
            state.player.hp = min(100, state.player.hp + 5)
        elif intent.action_type == ActionType.FLEE:
            state.player.location_id = world_blueprint.starting_location_id

    def _is_valid_move_target(self, world_blueprint: WorldBlueprint, current_location: str, target: str) -> bool:
        target = self._normalize_location_id(world_blueprint, target)
        if current_location == target:
            return True
        current = self._world_location(world_blueprint, current_location)
        return bool(current and target in current.connections)

    def _normalize_location_id(self, world_blueprint: WorldBlueprint, target: object) -> str | None:
        if not isinstance(target, str):
            return None
        normalized = target.strip().lower()
        for location in world_blueprint.locations:
            if normalized in {location.id.lower(), location.label.strip().lower()}:
                return location.id
        return None

    def _normalize_npc_id(self, world_blueprint: WorldBlueprint, target: object) -> str | None:
        if not isinstance(target, str):
            return None
        normalized = target.strip().lower()
        for npc in world_blueprint.npcs:
            if normalized in {npc.id.lower(), npc.label.strip().lower()}:
                return npc.id
        return None

    def _sanitize_choices(self, state: GameState, world_blueprint: WorldBlueprint, proposal_choices: list[str]) -> list[str]:
        allowed = set(self._choices_for_state(state, world_blueprint))
        choices = [choice.strip() for choice in proposal_choices if isinstance(choice, str) and choice.strip() in allowed]
        deduped: list[str] = []
        for choice in choices:
            if choice not in deduped:
                deduped.append(choice)
        return deduped[:4]

    def _merge_discovery(self, discovery_log: list[str], proposed_facts: list[str]) -> list[str]:
        merged = list(discovery_log)
        for fact in proposed_facts:
            normalized = str(fact).strip()
            if normalized and normalized not in merged:
                merged.append(normalized)
        return merged[-24:]

    def _engine_result_for(
        self,
        previous: GameState,
        next_state: GameState,
        intent: Action,
        validation_flags: list[str],
    ) -> EngineResult:
        return EngineResult(
            success=True,
            message_code=self._message_code_for(intent),
            location_changed=previous.player.location_id != next_state.player.location_id,
            quest_stage_changed=previous.quests.story_arc.stage != next_state.quests.story_arc.stage,
            ending_reached=None,
            details=[intent.action_type.value, *validation_flags][:6],
        )

    def _message_code_for(self, intent: Action) -> str:
        mapping = {
            ActionType.MOVE: "MOVE_OK",
            ActionType.TALK: "DIALOGUE_PROGRESS",
            ActionType.INVESTIGATE: "INVESTIGATE_PROGRESS",
            ActionType.REST: "REST_OK",
            ActionType.USE_ITEM: "USE_ITEM_OK",
            ActionType.FLEE: "RETREAT_OK",
        }
        return mapping.get(intent.action_type, "AGENT_CONTINUE")

    def _choices_for_state(self, state: GameState, world_blueprint: WorldBlueprint) -> list[str]:
        clue_phrase = self._clue_phrase(world_blueprint)
        choices = [f"주변을 조사해 {clue_phrase}"]
        for npc in self._current_npcs(world_blueprint, state.player.location_id)[:1]:
            choices.append(f"{npc.label}{self._topic_particle(npc.label)} 대화한다")
        current = self._world_location(world_blueprint, state.player.location_id)
        if current:
            for connection in current.connections[:2]:
                label = self._location_label(world_blueprint, connection)
                if label:
                    particle = "로" if label.endswith(("길", "문", "루")) else "으로"
                    choices.append(f"{label}{particle} 이동한다")
        if len(choices) < 3:
            choices.append("잠시 숨을 고르며 상황을 정리한다")
        return choices[:4]

    def _clue_phrase(self, world_blueprint: WorldBlueprint) -> str:
        base = world_blueprint.player_goal.strip() or world_blueprint.core_conflict.strip()
        if not base:
            return "단서를 찾는다"
        short = base[:28].rstrip(" .")
        return f"{short}의 실마리를 찾는다"

    def _world_location(self, world_blueprint: WorldBlueprint, location_id: str) -> WorldLocation | None:
        return next((location for location in world_blueprint.locations if location.id == location_id), None)

    def _current_npcs(self, world_blueprint: WorldBlueprint, location_id: str) -> list[WorldNpc]:
        return [npc for npc in world_blueprint.npcs if npc.home_location_id == location_id]

    def _location_label(self, world_blueprint: WorldBlueprint, location_id: str) -> str:
        location = self._world_location(world_blueprint, location_id)
        return location.label if location else location_id

    def _topic_particle(self, text: str) -> str:
        if not text:
            return "와"
        last = text[-1]
        if not ("\uac00" <= last <= "\ud7a3"):
            return "와"
        return "과" if (ord(last) - ord("\uac00")) % 28 else "와"
