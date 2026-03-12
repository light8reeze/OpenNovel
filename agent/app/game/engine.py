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
    if _contains_any(normalized, ["회랑", "hall"]):
        action_type, target = ActionType.MOVE, "hall"
    elif _contains_any(normalized, ["함정방", "함정", "trap room", "trap"]):
        action_type, target = ActionType.MOVE, "trap_room"
    elif _contains_any(normalized, ["성소", "제단", "sanctum", "altar"]):
        action_type, target = ActionType.MOVE, "sanctum"
    elif _contains_any(normalized, ["입구", "entrance"]):
        action_type, target = ActionType.MOVE, "ruins_entrance"
    elif _contains_any(normalized, ["관리인", "안내자", "caretaker", "대화", "talk"]):
        action_type, target = ActionType.TALK, "caretaker"
    elif _contains_any(normalized, ["휴식", "rest"]):
        action_type, target = ActionType.REST, None
    elif _contains_any(normalized, ["횃불", "torch"]):
        action_type, target = ActionType.USE_ITEM, "torch"
    elif _contains_any(normalized, ["도망", "후퇴", "retreat", "flee"]):
        action_type, target = ActionType.FLEE, None
    else:
        action_type, target = ActionType.INVESTIGATE, None
    return Action(action_type=action_type, target=target, raw_input=input_text)


def allowed_actions_for_state(state: GameState) -> list[ActionType]:
    actions = [ActionType.INVESTIGATE, ActionType.MOVE]
    if state.player.location_id == "ruins_entrance":
        actions.append(ActionType.TALK)
    if state.player.inventory.get("torch", 0) > 0:
        actions.append(ActionType.USE_ITEM)
    if state.quests.sunken_ruins.stage >= 2:
        actions.append(ActionType.FLEE)
    actions.append(ActionType.REST)
    return actions


def visible_targets_for_state(state: GameState) -> list[str]:
    if state.player.location_id == "ruins_entrance":
        targets = ["caretaker", "hall", "ruins_entrance"]
    elif state.player.location_id == "collapsed_hall":
        targets = ["trap_room", "ruins_entrance"]
    elif state.player.location_id == "trap_chamber":
        targets = ["sanctum", "hall"]
    elif state.player.location_id == "buried_sanctum":
        targets = ["trap_room"]
    else:
        targets = ["ruins_entrance"]
    if state.player.inventory.get("torch", 0) > 0:
        targets.append("torch")
    return targets


def choices_for_state(state: GameState) -> list[str]:
    if state.player.location_id == "ruins_entrance":
        return ["주변을 조사한다", "관리인과 대화한다", "회랑으로 이동한다"]
    if state.player.location_id == "collapsed_hall":
        return ["주변을 조사한다", "함정방으로 이동한다", "입구로 돌아간다"]
    if state.player.location_id == "trap_chamber":
        return ["주변을 조사한다", "성소로 이동한다", "회랑으로 돌아간다"]
    if state.player.location_id == "buried_sanctum":
        return ["주변을 조사한다", "함정방으로 이동한다", "후퇴한다"]
    return ["주변을 조사한다", "입구로 돌아간다"]


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
            if payload.get("quest_id") == "sunken_ruins":
                next_state.quests.sunken_ruins.stage = int(payload["stage"])
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
        "hall": "collapsed_hall",
        "trap_room": "trap_chamber",
        "sanctum": "buried_sanctum",
    }.get(target, target)
    current = next((location for location in content.locations if location.id == state.player.location_id), None)
    if current and mapped_target in current.connections:
        return [Event("move_player", mapped_target)], _result(True, "MOVE_OK", True, False, None, [mapped_target])
    return [], _result(False, "MOVE_BLOCKED", False, False, None, [mapped_target])


def _resolve_talk(state: GameState) -> tuple[list[Event], EngineResult]:
    if state.player.location_id == "ruins_entrance":
        if not state.has_flag("met_caretaker"):
            return [
                Event("add_player_flag", "met_caretaker"),
                Event("affinity_delta", {"npc_id": "caretaker", "delta": 2}),
            ], _result(True, "CARETAKER_BRIEFING", False, False, None, ["caretaker"])
        return [], _result(True, "CARETAKER_WARNING", False, False, None, ["caretaker"])
    return [], _result(False, "NO_NPC_TO_TALK", False, False, None, ["no_npc"])


def _resolve_investigate(state: GameState) -> tuple[list[Event], EngineResult]:
    stage = state.quests.sunken_ruins.stage
    if state.player.location_id == "ruins_entrance" and stage == 0:
        return [
            Event("add_player_flag", "found_rune"),
            Event("quest_stage_set", {"quest_id": "sunken_ruins", "stage": 1}),
        ], _result(True, "RUNE_FOUND", False, True, None, ["rune"])
    if state.player.location_id == "collapsed_hall" and stage <= 1:
        return [
            Event("add_player_flag", "opened_passage"),
            Event("quest_stage_set", {"quest_id": "sunken_ruins", "stage": 2}),
        ], _result(True, "PASSAGE_OPENED", False, True, None, ["passage"])
    if state.player.location_id == "trap_chamber" and stage <= 2:
        return [
            Event("add_player_flag", "trap_pattern_known"),
            Event("quest_stage_set", {"quest_id": "sunken_ruins", "stage": 3}),
        ], _result(True, "TRAP_REVEALED", False, True, None, ["trap_pattern"])
    if state.player.location_id == "buried_sanctum" and stage == 3:
        return [
            Event("add_player_flag", "seal_broken"),
            Event("quest_stage_set", {"quest_id": "sunken_ruins", "stage": 4}),
        ], _result(True, "SEAL_BROKEN", False, True, None, ["seal"])
    if state.player.location_id == "buried_sanctum" and stage == 4:
        return [
            Event("add_player_flag", "took_relic"),
            Event("quest_stage_set", {"quest_id": "sunken_ruins", "stage": 5}),
            Event("gold_delta", 35),
        ], _result(True, "RELIC_SECURED", False, True, None, ["relic"])
    if state.player.location_id == "ruins_entrance" and stage >= 5 and state.has_flag("took_relic"):
        return [
            Event("add_player_flag", "returned_with_relic"),
            Event("quest_stage_set", {"quest_id": "sunken_ruins", "stage": 6}),
        ], _result(True, "RELIC_RECOVERED", False, True, "relic_recovered", ["ending_good"])
    return [], _result(False, "NOTHING_FOUND", False, False, None, ["empty_search"])


def _resolve_use_item(state: GameState, target: str | None) -> tuple[list[Event], EngineResult]:
    if target == "torch" and state.player.inventory.get("torch", 0) > 0:
        return [Event("add_player_flag", "torch_lit")], _result(True, "TORCH_LIT", False, False, None, ["torch"])
    return [], _result(False, "ITEM_NOT_AVAILABLE", False, False, None, ["missing_item"])


def _resolve_flee(state: GameState) -> tuple[list[Event], EngineResult]:
    if state.player.location_id == "buried_sanctum" and state.quests.sunken_ruins.stage >= 4 and not state.has_flag("took_relic"):
        return [
            Event("add_player_flag", "curse_marked"),
            Event("quest_stage_set", {"quest_id": "sunken_ruins", "stage": 99}),
        ], _result(True, "CURSE_TRIGGERED", False, True, "greed_awakened", ["ending_curse"])
    if state.quests.sunken_ruins.stage >= 2:
        return [
            Event("add_player_flag", "retreated_alive"),
            Event("quest_stage_set", {"quest_id": "sunken_ruins", "stage": 99}),
        ], _result(True, "RETREAT_END", False, True, "retreated_alive", ["ending_retreat"])
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
