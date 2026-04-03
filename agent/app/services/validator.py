from __future__ import annotations

from copy import deepcopy
import re

from app.game.models import ContentBundle, GameState, ThemePack, ThemeVictoryPath, initial_state
from app.schemas.common import Action, ActionType, EngineResult
from app.schemas.multi_agent import NpcEvent, ValidationResult, WorldBlueprint, WorldLocation, WorldNpc


class RuleValidator:
    STYLE_SCORE_DELTAS: dict[ActionType, dict[str, int]] = {
        ActionType.MOVE: {"cautious": 1},
        ActionType.TALK: {"diplomatic": 2},
        ActionType.INVESTIGATE: {"curious": 2},
        ActionType.REST: {"cautious": 1},
        ActionType.USE_ITEM: {"decisive": 1},
        ActionType.FLEE: {"cautious": 1},
    }

    def __init__(self, content: ContentBundle):
        self.content = content

    def initialize_world(self, blueprint: WorldBlueprint, *, seed: int) -> ValidationResult:
        state = initial_state(seed=seed)
        state.player.location_id = self._normalize_location_id(blueprint, blueprint.starting_location_id) or blueprint.starting_location_id
        self._add_flag(state, f"visited:{state.player.location_id}")
        if blueprint.world_summary:
            state.world.global_flags.append(f"world:{blueprint.id}")
        if blueprint.theme_id:
            state.world.theme_id = blueprint.theme_id
            state.world.theme_rules = list(blueprint.theme_rules)
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
        progress_kind = self._apply_validated_patch(state, next_state, world_blueprint, proposal_patch, intent, validation_flags)
        self._apply_theme_pressure(next_state, world_blueprint, intent)
        self._apply_style_scoring(next_state, world_blueprint, intent)
        npc_events = self._check_npc_events(next_state, world_blueprint, "turn_start")
        if intent.action_type == ActionType.MOVE and state.player.location_id != next_state.player.location_id:
            npc_events.extend(self._check_npc_events(next_state, world_blueprint, "player_enters"))
        completed_victory = self._evaluate_objective(next_state, world_blueprint, intent, progress_kind)
        allowed_choices = self._sanitize_choices(next_state, world_blueprint, proposal_choices)
        if len(allowed_choices) < 2:
            validation_flags.append("validator_regenerated_choices")
            allowed_choices = self._choices_for_state(next_state, world_blueprint)
        if completed_victory:
            allowed_choices = []
            validation_flags.append("ending_reached_no_choices")
        next_discovery = self._merge_discovery(discovery_log, proposed_facts)
        if risk_tags:
            validation_flags.extend([tag for tag in risk_tags if tag not in validation_flags])
        engine_result = self._engine_result_for(
            state,
            next_state,
            intent,
            progress_kind,
            validation_flags,
            completed_victory,
            npc_events,
        )
        scene_summary = self._validated_scene_summary(
            previous=state,
            next_state=next_state,
            world_blueprint=world_blueprint,
            intent=intent,
            progress_kind=progress_kind,
            proposal_summary=proposal_summary,
        )
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
        previous_state: GameState,
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
                if intent.action_type == ActionType.MOVE:
                    validation_flags.append("validator_ignored_move_patch")
                elif self._is_valid_move_target(world_blueprint, state.player.location_id, location_id):
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

        return self._apply_intent_defaults(previous_state, state, world_blueprint, intent, validation_flags)

    def _apply_intent_defaults(
        self,
        previous_state: GameState,
        state: GameState,
        world_blueprint: WorldBlueprint,
        intent: Action,
        validation_flags: list[str],
    ) -> str:
        normalized_target = self._normalize_location_id(world_blueprint, intent.target)
        if intent.action_type == ActionType.MOVE and normalized_target and self._is_valid_move_target(
            world_blueprint, previous_state.player.location_id, normalized_target
        ):
            is_new_location = not self._has_flag(previous_state, f"visited:{normalized_target}")
            state.player.location_id = normalized_target
            self._add_flag(state, f"visited:{normalized_target}")
            if is_new_location:
                state.quests.story_arc.stage = min(6, state.quests.story_arc.stage + 1)
                return "move"
            return "reposition"
        elif intent.action_type == ActionType.INVESTIGATE:
            location = self._world_location(world_blueprint, state.player.location_id)
            if location:
                hook_index = self._next_unseen_hook_index(previous_state, location)
                if hook_index is not None:
                    self._add_flag(state, f"hook:{location.id}:{hook_index}")
                    state.quests.story_arc.stage = min(6, state.quests.story_arc.stage + 1)
                    return "investigate"
                if self._advance_finale_progress(state, world_blueprint, ActionType.INVESTIGATE):
                    return "investigate"
            validation_flags.append("area_exhausted")
            return "stalled"
        elif intent.action_type == ActionType.TALK:
            npc_id = self._normalize_npc_id(world_blueprint, intent.target) or self._current_npc_id(world_blueprint, state.player.location_id)
            if npc_id:
                first_meaningful_talk = not self._has_flag(previous_state, f"talked:{npc_id}")
                if first_meaningful_talk:
                    self._add_flag(state, f"talked:{npc_id}")
                    state.quests.story_arc.stage = min(6, state.quests.story_arc.stage + 1)
                state.relations.npc_affinity[npc_id] = min(10, state.relations.npc_affinity.get(npc_id, 5) + 1)
                return "talk" if first_meaningful_talk else "stalled"
            if self._available_victory_path(state, world_blueprint, ActionType.TALK) is not None:
                return "talk"
            validation_flags.append("no_dialogue_target")
            return "stalled"
        elif intent.action_type == ActionType.USE_ITEM:
            if "torch_lit" not in previous_state.player.flags:
                self._add_flag(state, "torch_lit")
                return "use_item"
            if self._available_victory_path(state, world_blueprint, ActionType.USE_ITEM) is not None:
                return "use_item"
            validation_flags.append("item_use_exhausted")
            return "stalled"
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
        return deduped[:6]

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
        completed_victory: ThemeVictoryPath | None,
        npc_events: list[NpcEvent],
    ) -> EngineResult:
        npc_event_details = [
            f"npc_event:{event.npc_id}:{event.action}:{event.message}"
            for event in npc_events
        ]
        if completed_victory is not None:
            details = [
                intent.action_type.value,
                f"progress:{progress_kind}",
                f"victory:{completed_victory.id}",
                *npc_event_details,
                *completed_victory.details,
                *validation_flags,
            ]
            return EngineResult(
                success=True,
                message_code="OBJECTIVE_COMPLETED",
                location_changed=previous.player.location_id != next_state.player.location_id,
                quest_stage_changed=previous.quests.story_arc.stage != next_state.quests.story_arc.stage,
                ending_reached=completed_victory.id,
                details=details,
            )
        return EngineResult(
            success=True,
            message_code=self._message_code_for(intent),
            location_changed=previous.player.location_id != next_state.player.location_id,
            quest_stage_changed=previous.quests.story_arc.stage != next_state.quests.story_arc.stage,
            ending_reached=None,
            details=[
                intent.action_type.value,
                f"progress:{progress_kind}",
                f"objective:{next_state.objective.status}",
                *npc_event_details,
                *validation_flags,
            ],
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
        return self._generate_choices(state, world_blueprint)

    def _generate_choices(self, state: GameState, world_blueprint: WorldBlueprint) -> list[str]:
        choices: list[str] = []
        repeat_talk_choices: list[str] = []
        location = self._world_location(world_blueprint, state.player.location_id)
        location_label = self._location_label(world_blueprint, state.player.location_id)
        investigate_victory = self._available_victory_path(state, world_blueprint, ActionType.INVESTIGATE)
        hook = self._next_hook_label(state, location)
        if hook:
            choices.append(self._investigate_choice(location_label, hook))
        elif investigate_victory is not None:
            choices.append(f"{location_label}의 핵심 흔적을 끝까지 추적한다")
        elif self._can_advance_finale_progress(state, world_blueprint, ActionType.INVESTIGATE):
            choices.append(f"{location_label}의 남은 기척을 끝까지 더듬어 본다")
        else:
            choices.append(f"{location_label} 주변을 다시 살피며 놓친 흔적이 없는지 확인한다")
        for npc in self._current_npcs(world_blueprint, state.player.location_id)[:1]:
            choices.extend(self._style_affinity_choices(state, npc))
            verb = "대화한다"
            talk_choice = f"{npc.label}{self._topic_particle(npc.label)} {verb}"
            if not self._has_flag(state, f"talked:{npc.id}") and npc.interaction_hint:
                verb = "대화해 속내를 떠본다"
                talk_choice = f"{npc.label}{self._topic_particle(npc.label)} {verb}"
                choices.append(talk_choice)
            else:
                repeat_talk_choices.append(talk_choice)
        if not self._current_npcs(world_blueprint, state.player.location_id) and self._available_victory_path(
            state, world_blueprint, ActionType.TALK
        ):
            choices.append("이곳에 남은 기운과 대화해 본다")
        theme_use_item_choice = self._theme_use_item_choice(state, world_blueprint)
        if theme_use_item_choice:
            choices.append(theme_use_item_choice)
        current = self._world_location(world_blueprint, state.player.location_id)
        if current:
            for connection in self._prioritized_connections(state, world_blueprint, current):
                label = self._location_label(world_blueprint, connection)
                if label:
                    particle = self._direction_particle(label)
                    choices.append(f"{label}{particle} 이동한다")
        choices.extend(repeat_talk_choices)
        if "torch" in state.player.inventory and "torch_lit" not in state.player.flags:
            choices.append("횃불을 들어 주변을 더 자세히 살핀다")
        if state.player.hp < 90 or state.quests.story_arc.stage >= 2:
            choices.append("잠시 숨을 고르며 상황을 정리한다")
        deduped: list[str] = []
        for choice in choices:
            normalized = choice.strip()
            if normalized and normalized not in deduped:
                deduped.append(normalized)
        return deduped[:6]

    def _style_affinity_choices(self, state: GameState, npc: WorldNpc) -> list[str]:
        affinity = state.relations.npc_affinity.get(npc.id, 5)
        if affinity < 7:
            return []
        topic_particle = self._topic_particle(npc.label)
        style_choice_templates = {
            "cautious": f"{npc.label}의 반응을 살피며 조심스럽게 속내를 확인한다",
            "diplomatic": f"{npc.label}{topic_particle} 이해관계를 조율하며 협조를 끌어낸다",
            "curious": f"{npc.label}에게 숨겨 둔 사정을 더 깊게 캐묻는다",
            "decisive": f"{npc.label}에게 지금 당장 결단을 내려 달라고 요구한다",
            "pious": f"{npc.label}{topic_particle} 금기와 맹세의 의미를 엄숙하게 확인한다",
        }
        style_priority = ["diplomatic", "curious", "cautious", "decisive", "pious"]
        return [style_choice_templates[tag] for tag in style_priority if tag in state.player.style_tags]

    def _world_location(self, world_blueprint: WorldBlueprint, location_id: str) -> WorldLocation | None:
        return next((location for location in world_blueprint.locations if location.id == location_id), None)

    def _current_npcs(self, world_blueprint: WorldBlueprint, location_id: str) -> list[WorldNpc]:
        return [npc for npc in world_blueprint.npcs if npc.home_location_id == location_id]

    def _current_npc_id(self, world_blueprint: WorldBlueprint, location_id: str) -> str | None:
        npcs = self._current_npcs(world_blueprint, location_id)
        return npcs[0].id if npcs else None

    def _check_npc_events(self, state: GameState, world_blueprint: WorldBlueprint, trigger: str) -> list[NpcEvent]:
        events: list[NpcEvent] = []
        for npc in world_blueprint.npcs:
            if trigger == "player_enters" and npc.home_location_id != state.player.location_id:
                continue
            for behavior in npc.behaviors:
                if not self._matches_npc_trigger(behavior.trigger, trigger):
                    continue
                if not self._evaluate_npc_condition(behavior.condition, state, npc):
                    continue
                if self._npc_event_on_cooldown(state, npc.id, behavior.action, behavior.cooldown_turns):
                    continue
                events.append(
                    NpcEvent(
                        npc_id=npc.id,
                        npc_label=npc.label,
                        action=behavior.action,
                        message=behavior.message,
                    )
                )
                self._record_npc_event(state, npc.id, behavior.action)
        return events

    def _matches_npc_trigger(self, behavior_trigger: str, active_trigger: str) -> bool:
        normalized = behavior_trigger.strip().lower()
        if normalized == active_trigger:
            return True
        return active_trigger == "turn_start" and normalized == "affinity_threshold"

    def _evaluate_npc_condition(self, condition: str, state: GameState, npc: WorldNpc) -> bool:
        normalized = condition.strip()
        if not normalized:
            return True
        match = re.fullmatch(r"(affinity|turn)\s*(>=|==|<|<=|>)\s*(-?\d+)", normalized)
        if not match:
            return False
        field, operator, raw_value = match.groups()
        expected = int(raw_value)
        current = state.relations.npc_affinity.get(npc.id, 5) if field == "affinity" else state.meta.turn
        if operator == ">=":
            return current >= expected
        if operator == "==":
            return current == expected
        if operator == "<":
            return current < expected
        if operator == "<=":
            return current <= expected
        return current > expected

    def _npc_event_on_cooldown(self, state: GameState, npc_id: str, action: str, cooldown_turns: int) -> bool:
        if cooldown_turns <= 0:
            return False
        prefix = f"npc_cooldown:{npc_id}:{action}:"
        last_turn = -1
        for flag in state.player.flags:
            if flag.startswith(prefix):
                _, _, _, raw_turn = flag.split(":", 3)
                if raw_turn.isdigit():
                    last_turn = max(last_turn, int(raw_turn))
        if last_turn < 0:
            return False
        return state.meta.turn - last_turn <= cooldown_turns

    def _record_npc_event(self, state: GameState, npc_id: str, action: str) -> None:
        self._add_flag(state, f"npc_cooldown:{npc_id}:{action}:{state.meta.turn}")

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

    def _investigate_choice(self, location_label: str, hook: str) -> str:
        normalized_hook = hook.strip()
        if normalized_hook.startswith(location_label):
            return f"{normalized_hook}{self._object_particle(normalized_hook)} 조사한다"
        return f"{location_label}에서 {normalized_hook}{self._object_particle(normalized_hook)} 조사한다"

    def _validated_scene_summary(
        self,
        previous: GameState,
        next_state: GameState,
        world_blueprint: WorldBlueprint,
        intent: Action,
        progress_kind: str,
        proposal_summary: str,
    ) -> str:
        default_summary = self._default_scene_summary(previous, next_state, world_blueprint, intent, progress_kind)
        if intent.action_type == ActionType.MOVE or previous.player.location_id != next_state.player.location_id:
            return default_summary
        summary = proposal_summary.strip()
        return summary or default_summary

    def _apply_theme_pressure(self, state: GameState, world_blueprint: WorldBlueprint, intent: Action) -> None:
        theme_pack = self._theme_pack(state.world.theme_id)
        if theme_pack is None or intent.action_type.value not in theme_pack.alert_actions:
            return
        region_id = world_blueprint.id[:24]
        current_alert = state.world.alert_by_region.get(region_id, 0)
        state.world.alert_by_region[region_id] = min(10, current_alert + 1)

    def _apply_style_scoring(self, state: GameState, world_blueprint: WorldBlueprint, intent: Action) -> None:
        deltas = dict(self.STYLE_SCORE_DELTAS.get(intent.action_type, {}))
        theme_pack = self._theme_pack(state.world.theme_id)
        if theme_pack is not None:
            for style, value in theme_pack.style_bias.get(intent.action_type.value, {}).items():
                if isinstance(value, int):
                    deltas[style] = deltas.get(style, 0) + value
        if not deltas:
            return
        next_scores = dict(state.player.style_scores)
        for style, value in deltas.items():
            next_scores[style] = max(0, next_scores.get(style, 0) + value)
        state.player.style_scores = next_scores
        state.player.style_tags = sorted([style for style, score in next_scores.items() if score >= 3])

    def _evaluate_objective(
        self,
        state: GameState,
        world_blueprint: WorldBlueprint,
        intent: Action,
        progress_kind: str,
    ) -> ThemeVictoryPath | None:
        if state.objective.status == "completed":
            return None
        theme_pack = self._theme_pack(state.world.theme_id)
        if theme_pack is None:
            return None
        required_progress = {
            ActionType.INVESTIGATE: "investigate",
            ActionType.TALK: "talk",
            ActionType.USE_ITEM: "use_item",
        }.get(intent.action_type)
        if required_progress is not None and progress_kind != required_progress:
            return None
        current_index = self._location_index(world_blueprint, state.player.location_id)
        for victory_path in theme_pack.victory_paths:
            if not self._matches_victory_path(state, world_blueprint, victory_path, intent.action_type, current_index):
                continue
            state.objective.status = "completed"
            state.objective.victory_path = victory_path.id
            return victory_path
        return None

    def _available_victory_path(
        self,
        state: GameState,
        world_blueprint: WorldBlueprint,
        action_type: ActionType,
    ) -> ThemeVictoryPath | None:
        theme_pack = self._theme_pack(state.world.theme_id)
        if theme_pack is None or state.objective.status == "completed":
            return None
        current_index = self._location_index(world_blueprint, state.player.location_id)
        for victory_path in theme_pack.victory_paths:
            if self._matches_victory_path(state, world_blueprint, victory_path, action_type, current_index):
                return victory_path
        return None

    def _matches_victory_path(
        self,
        state: GameState,
        world_blueprint: WorldBlueprint,
        victory_path: ThemeVictoryPath,
        action_type: ActionType,
        current_index: int,
    ) -> bool:
        if victory_path.required_action != action_type.value:
            return False
        if state.quests.story_arc.stage < victory_path.min_stage:
            return False
        required_index = self._resolve_required_location_index(world_blueprint, victory_path.required_location_index)
        return current_index == required_index

    def _can_advance_finale_progress(
        self,
        state: GameState,
        world_blueprint: WorldBlueprint,
        action_type: ActionType,
    ) -> bool:
        theme_pack = self._theme_pack(state.world.theme_id)
        if theme_pack is None or state.objective.status == "completed":
            return False
        current_index = self._location_index(world_blueprint, state.player.location_id)
        for victory_path in theme_pack.victory_paths:
            if victory_path.required_action != action_type.value:
                continue
            required_index = self._resolve_required_location_index(world_blueprint, victory_path.required_location_index)
            if current_index == required_index and state.quests.story_arc.stage < victory_path.min_stage:
                return True
        return False

    def _advance_finale_progress(
        self,
        state: GameState,
        world_blueprint: WorldBlueprint,
        action_type: ActionType,
    ) -> bool:
        if not self._can_advance_finale_progress(state, world_blueprint, action_type):
            return False
        state.quests.story_arc.stage = min(6, state.quests.story_arc.stage + 1)
        self._add_flag(state, f"finale_progress:{state.player.location_id}:{action_type.value.lower()}:{state.quests.story_arc.stage}")
        return True

    def _prioritized_connections(
        self,
        state: GameState,
        world_blueprint: WorldBlueprint,
        location: WorldLocation,
    ) -> list[str]:
        climax_index = self._climax_location_index(world_blueprint)
        final_location_id = world_blueprint.locations[climax_index].id if world_blueprint.locations else None
        ranked = sorted(
            location.connections,
            key=lambda connection: (
                0 if connection == final_location_id else 1,
                0 if not self._has_flag(state, f"visited:{connection}") else 1,
                self._location_index(world_blueprint, connection),
            ),
        )
        deduped: list[str] = []
        for connection in ranked:
            if connection not in deduped:
                deduped.append(connection)
        return deduped

    def _theme_use_item_choice(self, state: GameState, world_blueprint: WorldBlueprint) -> str | None:
        victory_path = self._available_victory_path(state, world_blueprint, ActionType.USE_ITEM)
        if victory_path is None:
            return None
        location_label = self._location_label(world_blueprint, state.player.location_id)
        return f"{location_label}에서 {victory_path.label}{self._object_particle(victory_path.label)} 시도한다"

    def _theme_pack(self, theme_id: str | None) -> ThemePack | None:
        if not theme_id:
            return None
        for theme_pack in self.content.theme_packs:
            if theme_pack.id == theme_id:
                return theme_pack
        return None

    def _location_index(self, world_blueprint: WorldBlueprint, location_id: str) -> int:
        for index, location in enumerate(world_blueprint.locations):
            if location.id == location_id:
                return index
        return -1

    def _resolve_required_location_index(self, world_blueprint: WorldBlueprint, required_index: int) -> int:
        if required_index >= 0:
            return required_index
        if required_index == -1:
            return self._climax_location_index(world_blueprint)
        return max(0, len(world_blueprint.locations) + required_index)

    def _climax_location_index(self, world_blueprint: WorldBlueprint) -> int:
        if not world_blueprint.locations:
            return 0
        highest_danger = max(location.danger_level for location in world_blueprint.locations)
        for index in range(len(world_blueprint.locations) - 1, -1, -1):
            if world_blueprint.locations[index].danger_level == highest_danger:
                return index
        return max(0, len(world_blueprint.locations) - 1)
