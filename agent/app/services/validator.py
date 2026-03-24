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
        self._add_flag(state, f"visited:{state.player.location_id}")
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
            progress_kind="opening",
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
        progress_kind = self._apply_validated_patch(next_state, world_blueprint, proposal_patch, intent, validation_flags)
        allowed_choices = self._sanitize_choices(next_state, world_blueprint, proposal_choices)
        if len(allowed_choices) < 2:
            validation_flags.append("validator_regenerated_choices")
            allowed_choices = self._choices_for_state(next_state, world_blueprint)
        next_discovery = self._merge_discovery(discovery_log, proposed_facts)
        if risk_tags:
            validation_flags.extend([tag for tag in risk_tags if tag not in validation_flags])
        engine_result = self._engine_result_for(state, next_state, intent, progress_kind, validation_flags)
        scene_summary = proposal_summary.strip() or self._default_scene_summary(state, next_state, world_blueprint, intent, progress_kind)
        return ValidationResult(
            state=next_state,
            engine_result=engine_result,
            allowed_choices=allowed_choices,
            discovery_log=next_discovery,
            scene_summary=scene_summary,
            progress_kind=progress_kind,
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
    ) -> str:
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
                merged_flags = list(state.player.flags)
                for flag in flags:
                    normalized = str(flag)
                    if normalized not in merged_flags:
                        merged_flags.append(normalized)
                state.player.flags = merged_flags[-32:]

        quest_patch = patch.get("quests") if isinstance(patch, dict) else None
        if isinstance(quest_patch, dict):
            story_arc = quest_patch.get("story_arc")
            if isinstance(story_arc, dict):
                stage = story_arc.get("stage")
                if isinstance(stage, int):
                    validation_flags.append("validator_ignored_stage_patch")

        relations_patch = patch.get("relations") if isinstance(patch, dict) else None
        if isinstance(relations_patch, dict):
            affinity = relations_patch.get("npc_affinity")
            if isinstance(affinity, dict):
                merged = deepcopy(state.relations.npc_affinity)
                for key, value in affinity.items():
                    if isinstance(value, int):
                        merged[str(key)] = max(0, min(10, value))
                state.relations.npc_affinity = merged

        return self._apply_intent_defaults(state, world_blueprint, intent, validation_flags)

    def _apply_intent_defaults(
        self,
        state: GameState,
        world_blueprint: WorldBlueprint,
        intent: Action,
        validation_flags: list[str],
    ) -> str:
        normalized_target = self._normalize_location_id(world_blueprint, intent.target)
        if intent.action_type == ActionType.MOVE and normalized_target and self._is_valid_move_target(
            world_blueprint, state.player.location_id, normalized_target
        ):
            is_new_location = not self._has_flag(state, f"visited:{normalized_target}")
            state.player.location_id = normalized_target
            self._add_flag(state, f"visited:{normalized_target}")
            if is_new_location:
                state.quests.story_arc.stage = min(6, state.quests.story_arc.stage + 1)
                return "move"
            return "reposition"
        elif intent.action_type == ActionType.INVESTIGATE:
            location = self._world_location(world_blueprint, state.player.location_id)
            if location:
                hook_index = self._next_unseen_hook_index(state, location)
                if hook_index is not None:
                    self._add_flag(state, f"hook:{location.id}:{hook_index}")
                    state.quests.story_arc.stage = min(6, state.quests.story_arc.stage + 1)
                    return "investigate"
            validation_flags.append("area_exhausted")
            return "stalled"
        elif intent.action_type == ActionType.TALK:
            npc_id = self._normalize_npc_id(world_blueprint, intent.target) or self._current_npc_id(world_blueprint, state.player.location_id)
            if npc_id:
                first_meaningful_talk = not self._has_flag(state, f"talked:{npc_id}")
                if first_meaningful_talk:
                    self._add_flag(state, f"talked:{npc_id}")
                    state.quests.story_arc.stage = min(6, state.quests.story_arc.stage + 1)
                state.relations.npc_affinity[npc_id] = min(10, state.relations.npc_affinity.get(npc_id, 5) + 1)
                return "talk" if first_meaningful_talk else "stalled"
            validation_flags.append("no_dialogue_target")
            return "stalled"
        elif intent.action_type == ActionType.USE_ITEM and "torch_lit" not in state.player.flags:
            state.player.flags.append("torch_lit")
            return "use_item"
        elif intent.action_type == ActionType.REST:
            previous_hp = state.player.hp
            state.player.hp = min(100, state.player.hp + 5)
            return "rest" if state.player.hp > previous_hp else "stalled"
        elif intent.action_type == ActionType.FLEE:
            state.player.location_id = world_blueprint.starting_location_id
            return "reposition"
        validation_flags.append("no_progress_applied")
        return "stalled"

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
        progress_kind: str,
        validation_flags: list[str],
    ) -> EngineResult:
        return EngineResult(
            success=True,
            message_code=self._message_code_for(intent),
            location_changed=previous.player.location_id != next_state.player.location_id,
            quest_stage_changed=previous.quests.story_arc.stage != next_state.quests.story_arc.stage,
            ending_reached=None,
            details=[intent.action_type.value, f"progress:{progress_kind}", *validation_flags][:6],
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
        choices: list[str] = []
        location = self._world_location(world_blueprint, state.player.location_id)
        location_label = self._location_label(world_blueprint, state.player.location_id)
        hook = self._next_hook_label(state, location)
        if hook:
            choices.append(f"{location_label}에서 {hook}{self._object_particle(hook)} 조사한다")
        else:
            choices.append(f"{location_label} 주변을 다시 살피며 놓친 흔적이 없는지 확인한다")
        for npc in self._current_npcs(world_blueprint, state.player.location_id)[:1]:
            verb = "대화한다"
            if not self._has_flag(state, f"talked:{npc.id}") and npc.interaction_hint:
                verb = "대화해 속내를 떠본다"
            choices.append(f"{npc.label}{self._topic_particle(npc.label)} {verb}")
        current = self._world_location(world_blueprint, state.player.location_id)
        if current:
            for connection in current.connections[:2]:
                label = self._location_label(world_blueprint, connection)
                if label:
                    particle = self._direction_particle(label)
                    choices.append(f"{label}{particle} 이동한다")
        if "torch" in state.player.inventory and "torch_lit" not in state.player.flags:
            choices.append("횃불을 들어 주변을 더 자세히 살핀다")
        if state.player.hp < 90 or state.quests.story_arc.stage >= 2:
            choices.append("잠시 숨을 고르며 상황을 정리한다")
        deduped: list[str] = []
        for choice in choices:
            normalized = choice.strip()
            if normalized and normalized not in deduped:
                deduped.append(normalized)
        return deduped[:4]

    def _world_location(self, world_blueprint: WorldBlueprint, location_id: str) -> WorldLocation | None:
        return next((location for location in world_blueprint.locations if location.id == location_id), None)

    def _current_npcs(self, world_blueprint: WorldBlueprint, location_id: str) -> list[WorldNpc]:
        return [npc for npc in world_blueprint.npcs if npc.home_location_id == location_id]

    def _current_npc_id(self, world_blueprint: WorldBlueprint, location_id: str) -> str | None:
        npcs = self._current_npcs(world_blueprint, location_id)
        return npcs[0].id if npcs else None

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

    def _object_particle(self, text: str) -> str:
        if not text:
            return "를"
        last = text[-1]
        if not ("\uac00" <= last <= "\ud7a3"):
            return "를"
        return "을" if (ord(last) - ord("\uac00")) % 28 else "를"

    def _direction_particle(self, text: str) -> str:
        if not text:
            return "로"
        last = text[-1]
        if not ("\uac00" <= last <= "\ud7a3"):
            return "로"
        jong = (ord(last) - ord("\uac00")) % 28
        return "으로" if jong not in (0, 8) else "로"

    def _has_flag(self, state: GameState, flag: str) -> bool:
        return flag in state.player.flags

    def _add_flag(self, state: GameState, flag: str) -> None:
        if flag not in state.player.flags:
            state.player.flags.append(flag)
            state.player.flags = state.player.flags[-32:]

    def _next_unseen_hook_index(self, state: GameState, location: WorldLocation | None) -> int | None:
        if not location:
            return None
        for index, _hook in enumerate(location.investigation_hooks):
            if not self._has_flag(state, f"hook:{location.id}:{index}"):
                return index
        return None

    def _next_hook_label(self, state: GameState, location: WorldLocation | None) -> str | None:
        index = self._next_unseen_hook_index(state, location)
        if location and index is not None and index < len(location.investigation_hooks):
            return location.investigation_hooks[index]
        return None

    def _default_scene_summary(
        self,
        previous: GameState,
        next_state: GameState,
        world_blueprint: WorldBlueprint,
        intent: Action,
        progress_kind: str,
    ) -> str:
        current_label = self._location_label(world_blueprint, next_state.player.location_id)
        if intent.action_type == ActionType.MOVE:
            if progress_kind == "move":
                return f"{current_label}에 처음 발을 들이며 새로운 압박과 기회가 선명해진다."
            return f"{current_label} 쪽으로 위치를 다시 잡으며 다음 움직임을 가늠한다."
        if intent.action_type == ActionType.INVESTIGATE:
            if progress_kind == "investigate":
                return f"{current_label}에서 새로운 단서가 드러나며 상황이 한 걸음 전진한다."
            return f"{current_label}에서는 이미 살핀 흔적이 반복되어, 다른 접근이 필요해 보인다."
        if intent.action_type == ActionType.TALK:
            if progress_kind == "talk":
                return "짧은 대화가 지나가며 관계와 정보의 결이 조금 더 또렷해진다."
            return "대화는 이어졌지만, 이미 알려진 경고를 다시 확인하는 수준에 그친다."
        if intent.action_type == ActionType.REST:
            return "잠시 숨을 고르며 지금까지의 단서와 위험을 정리한다."
        if intent.action_type == ActionType.USE_ITEM:
            return "손에 쥔 도구를 활용하자 놓치고 있던 질감과 흔적이 눈에 들어온다."
        return world_blueprint.opening_hook
