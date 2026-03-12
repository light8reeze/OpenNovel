from __future__ import annotations

from app.game.models import ContentBundle, Event, GameState, Resolution
from app.schemas.common import Action, ActionType, EngineResult


def resolve_text_action(state: GameState, content: ContentBundle, input_text: str) -> Resolution:
    return resolve_action_input(state, content, heuristic_parse_action(input_text))


def resolve_action_input(state: GameState, content: ContentBundle, action: Action) -> Resolution:
    events, engine_result = _resolve_action(state, content, action)
    next_state = apply_events(state, events)
    return Resolution(
        action=action,
        events=events,
        next_state=next_state,
        engine_result=engine_result,
    )


def heuristic_parse_action(input_text: str) -> Action:
    normalized = input_text.strip().lower()
    if _contains_any(normalized, ["창고", "warehouse"]):
        action_type, target = ActionType.MOVE, "warehouse"
    elif _contains_any(normalized, ["골목", "alley"]):
        action_type, target = ActionType.MOVE, "alley"
    elif _contains_any(normalized, ["여관", "tavern", "inn"]):
        action_type, target = ActionType.MOVE, "tavern"
    elif _contains_any(normalized, ["광장", "square"]):
        action_type, target = ActionType.MOVE, "village_square"
    elif _contains_any(normalized, ["아리아", "aria", "대화", "talk"]):
        action_type, target = ActionType.TALK, "aria"
    elif _contains_any(normalized, ["휴식", "rest"]):
        action_type, target = ActionType.REST, None
    elif _contains_any(normalized, ["횃불", "torch"]):
        action_type, target = ActionType.USE_ITEM, "torch"
    elif _contains_any(normalized, ["도망", "flee"]):
        action_type, target = ActionType.FLEE, None
    else:
        action_type, target = ActionType.INVESTIGATE, None
    return Action(action_type=action_type, target=target, raw_input=input_text)


def allowed_actions_for_state(state: GameState) -> list[ActionType]:
    actions = [ActionType.INVESTIGATE, ActionType.MOVE]
    if state.player.location_id in {"village_square", "village_warehouse", "crooked_tavern"}:
        actions.append(ActionType.TALK)
    if state.player.inventory.get("torch", 0) > 0:
        actions.append(ActionType.USE_ITEM)
    if state.player.location_id == "dark_alley" or state.quests.murder_case.stage >= 4:
        actions.append(ActionType.FLEE)
    actions.append(ActionType.REST)
    return actions


def visible_targets_for_state(state: GameState) -> list[str]:
    if state.player.location_id == "village_square":
        targets = ["warehouse", "aria", "village_square"]
    elif state.player.location_id == "village_warehouse":
        targets = ["aria", "village_square"]
    elif state.player.location_id == "dark_alley":
        targets = ["tavern", "dark_alley"]
    elif state.player.location_id == "crooked_tavern":
        targets = ["aria", "innkeeper", "village_square"]
    else:
        targets = ["village_square"]
    if state.player.inventory.get("torch", 0) > 0:
        targets.append("torch")
    return targets


def choices_for_state(state: GameState) -> list[str]:
    if state.player.location_id == "village_square":
        return ["주변을 조사한다", "창고로 이동한다", "아리아와 대화한다"]
    if state.player.location_id == "village_warehouse":
        return ["주변을 조사한다", "아리아와 대화한다", "광장으로 이동한다"]
    if state.player.location_id == "dark_alley":
        return ["주변을 조사한다", "여관으로 이동한다", "도망친다"]
    if state.player.location_id == "crooked_tavern":
        return ["아리아와 대화한다", "주변을 조사한다", "광장으로 이동한다"]
    return ["주변을 조사한다", "광장으로 이동한다"]


def apply_events(state: GameState, events: list[Event]) -> GameState:
    next_state = state.model_copy(deep=True)
    for event in events:
        if event.kind == "hp_delta":
            next_state.player.hp = max(0, min(100, next_state.player.hp + int(event.value)))
        elif event.kind == "gold_delta":
            next_state.player.gold = max(0, next_state.player.gold + int(event.value))
        elif event.kind == "add_player_flag":
            if event.value not in next_state.player.flags:
                next_state.player.flags.append(str(event.value))
        elif event.kind == "add_global_flag":
            if event.value not in next_state.world.global_flags:
                next_state.world.global_flags.append(str(event.value))
        elif event.kind == "quest_stage_set":
            payload = dict(event.value or {})
            if payload.get("quest_id") == "murder_case":
                next_state.quests.murder_case.stage = int(payload["stage"])
        elif event.kind == "affinity_delta":
            payload = dict(event.value or {})
            npc_id = str(payload["npc_id"])
            next_state.relations.npc_affinity[npc_id] = next_state.relations.npc_affinity.get(npc_id, 0) + int(
                payload["delta"]
            )
        elif event.kind == "move_player":
            next_state.player.location_id = str(event.value)
        elif event.kind == "add_item":
            payload = dict(event.value or {})
            item_id = str(payload["item_id"])
            amount = int(payload["amount"])
            next_state.player.inventory[item_id] = max(0, next_state.player.inventory.get(item_id, 0) + amount)
    next_state.meta.turn += 1
    return next_state


def _resolve_action(state: GameState, content: ContentBundle, action: Action) -> tuple[list[Event], EngineResult]:
    if action.action_type == ActionType.MOVE:
        return _resolve_move(state, content, action.target)
    if action.action_type == ActionType.TALK:
        return _resolve_talk(state)
    if action.action_type == ActionType.INVESTIGATE:
        return _resolve_investigate(state)
    if action.action_type == ActionType.REST:
        return [Event("hp_delta", 10)], _result(True, "REST_OK", False, False, None, ["hp_recovered"])
    if action.action_type == ActionType.USE_ITEM:
        return _resolve_use_item(state, action.target)
    if action.action_type == ActionType.FLEE:
        return _resolve_flee(state)
    return [], _result(False, "ACTION_NOT_SUPPORTED", False, False, None, ["unsupported"])


def _resolve_move(state: GameState, content: ContentBundle, target: str | None) -> tuple[list[Event], EngineResult]:
    if target is None:
        return [], _result(False, "MOVE_TARGET_MISSING", False, False, None, ["move_target_missing"])
    mapped_target = {
        "warehouse": "village_warehouse",
        "alley": "dark_alley",
        "tavern": "crooked_tavern",
    }.get(target, target)
    current = next((location for location in content.locations if location.id == state.player.location_id), None)
    if current and mapped_target in current.connections:
        return [Event("move_player", mapped_target)], _result(True, "MOVE_OK", True, False, None, [mapped_target])
    return [], _result(False, "MOVE_BLOCKED", False, False, None, [mapped_target])


def _resolve_talk(state: GameState) -> tuple[list[Event], EngineResult]:
    stage = state.quests.murder_case.stage
    if state.player.location_id in {"village_square", "village_warehouse"}:
        if stage < 3 and state.has_flag("found_bloody_cloth"):
            return [
                Event("add_player_flag", "met_aria"),
                Event("affinity_delta", {"npc_id": "aria", "delta": 5}),
                Event("quest_stage_set", {"quest_id": "murder_case", "stage": 3}),
            ], _result(True, "ARIA_CLUE_CONFIRMED", False, True, None, ["aria", "quest_advanced"])
        return [Event("add_player_flag", "met_aria")], _result(True, "ARIA_SMALL_TALK", False, False, None, ["aria"])
    if state.player.location_id == "crooked_tavern":
        if stage >= 4:
            return [
                Event("add_player_flag", "innkeeper_testimony"),
                Event("quest_stage_set", {"quest_id": "murder_case", "stage": 5}),
            ], _result(True, "INNKEEPER_TESTIMONY", False, True, None, ["innkeeper", "quest_advanced"])
        return [], _result(False, "NO_USEFUL_DIALOGUE", False, False, None, ["innkeeper"])
    return [], _result(False, "NO_NPC_TO_TALK", False, False, None, ["no_npc"])


def _resolve_investigate(state: GameState) -> tuple[list[Event], EngineResult]:
    stage = state.quests.murder_case.stage
    if state.player.location_id == "village_square" and stage == 0:
        return [
            Event("add_player_flag", "found_blood_mark"),
            Event("quest_stage_set", {"quest_id": "murder_case", "stage": 1}),
        ], _result(True, "BLOOD_MARK_FOUND", False, True, None, ["blood_mark"])
    if state.player.location_id == "village_warehouse" and stage <= 2:
        return [
            Event("add_player_flag", "found_bloody_cloth"),
            Event("quest_stage_set", {"quest_id": "murder_case", "stage": 2}),
        ], _result(True, "BLOODY_CLOTH_FOUND", False, stage != 2, None, ["bloody_cloth"])
    if state.player.location_id == "dark_alley" and 3 <= stage < 4:
        return [
            Event("add_player_flag", "saw_shadow_in_alley"),
            Event("quest_stage_set", {"quest_id": "murder_case", "stage": 4}),
        ], _result(True, "SHADOW_TRACKED", False, True, None, ["shadow", "quest_advanced"])
    if state.player.location_id == "crooked_tavern" and stage >= 5:
        return [
            Event("add_player_flag", "case_closed"),
            Event("quest_stage_set", {"quest_id": "murder_case", "stage": 6}),
            Event("gold_delta", 30),
        ], _result(True, "GOOD_END_UNLOCKED", False, True, "truth_revealed", ["ending_good"])
    return [], _result(False, "NOTHING_FOUND", False, False, None, ["empty_search"])


def _resolve_use_item(state: GameState, target: str | None) -> tuple[list[Event], EngineResult]:
    if target == "torch" and state.player.inventory.get("torch", 0) > 0:
        return [Event("add_player_flag", "torch_lit")], _result(True, "TORCH_LIT", False, False, None, ["torch"])
    return [], _result(False, "ITEM_NOT_AVAILABLE", False, False, None, ["missing_item"])


def _resolve_flee(state: GameState) -> tuple[list[Event], EngineResult]:
    if state.quests.murder_case.stage >= 4:
        return [
            Event("add_player_flag", "coward_ending"),
            Event("quest_stage_set", {"quest_id": "murder_case", "stage": 99}),
        ], _result(True, "BAD_END_FLEE", False, True, "cowardice", ["ending_bad"])
    return [], _result(False, "FLEE_TOO_EARLY", False, False, None, ["flee_blocked"])


def _result(
    success: bool,
    message_code: str,
    location_changed: bool,
    quest_stage_changed: bool,
    ending_reached: str | None,
    details: list[str],
) -> EngineResult:
    return EngineResult(
        success=success,
        message_code=message_code,
        location_changed=location_changed,
        quest_stage_changed=quest_stage_changed,
        ending_reached=ending_reached,
        details=details,
    )


def _contains_any(haystack: str, needles: list[str]) -> bool:
    return any(needle in haystack for needle in needles)
