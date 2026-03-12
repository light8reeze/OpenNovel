use content::ContentBundle;
use domain::{debug_log, Action, ActionType, EngineResult, Event, GameState};

#[derive(Debug, Clone)]
pub struct Resolution {
    pub action: Action,
    pub events: Vec<Event>,
    pub next_state: GameState,
    pub engine_result: EngineResult,
}

pub fn resolve_text_action(state: &GameState, content: &ContentBundle, input: &str) -> Resolution {
    resolve_action_input(state, content, heuristic_parse_action(input))
}

pub fn resolve_action_input(
    state: &GameState,
    content: &ContentBundle,
    action: Action,
) -> Resolution {
    let (events, engine_result) = resolve_action(state, content, &action);
    let next_state = apply_events(state.clone(), &events);
    debug_log(
        "normalized_action",
        &[
            ("turn", state.meta.turn.to_string()),
            ("action_type", format!("{:?}", action.action_type)),
            (
                "target",
                action.target.clone().unwrap_or_else(|| "-".to_string()),
            ),
            ("raw_input", action.raw_input.clone()),
            ("message_code", engine_result.message_code.clone()),
        ],
    );
    Resolution {
        action,
        events,
        next_state,
        engine_result,
    }
}

pub fn heuristic_parse_action(input: &str) -> Action {
    let normalized = input.trim().to_lowercase();
    let (action_type, target) = if contains_any(&normalized, &["회랑", "hall"]) {
        (ActionType::Move, Some("hall".to_string()))
    } else if contains_any(&normalized, &["함정방", "trap room", "trap"]) {
        (ActionType::Move, Some("trap_room".to_string()))
    } else if contains_any(&normalized, &["성소", "sanctum", "제단"]) {
        (ActionType::Move, Some("sanctum".to_string()))
    } else if contains_any(&normalized, &["입구", "entrance"]) {
        (ActionType::Move, Some("ruins_entrance".to_string()))
    } else if contains_any(
        &normalized,
        &["관리인", "안내자", "caretaker", "대화", "talk"],
    ) {
        (ActionType::Talk, Some("caretaker".to_string()))
    } else if contains_any(&normalized, &["휴식", "rest"]) {
        (ActionType::Rest, None)
    } else if contains_any(&normalized, &["횃불", "torch"]) {
        (ActionType::UseItem, Some("torch".to_string()))
    } else if contains_any(&normalized, &["도망", "후퇴", "retreat", "flee"]) {
        (ActionType::Flee, None)
    } else {
        (ActionType::Investigate, None)
    };

    Action {
        action_type,
        target,
        raw_input: input.to_string(),
    }
}

pub fn allowed_actions_for_state(state: &GameState) -> Vec<ActionType> {
    let mut actions = vec![ActionType::Investigate, ActionType::Move, ActionType::Rest];
    if state.player.location_id == "ruins_entrance" {
        actions.push(ActionType::Talk);
    }
    if state.player.inventory.get("torch").copied().unwrap_or(0) > 0 {
        actions.push(ActionType::UseItem);
    }
    if state.quests.sunken_ruins.stage >= 2 {
        actions.push(ActionType::Flee);
    }
    actions
}

pub fn visible_targets_for_state(state: &GameState) -> Vec<String> {
    let mut targets: Vec<String> = match state.player.location_id.as_str() {
        "ruins_entrance" => vec!["caretaker", "hall", "ruins_entrance"],
        "collapsed_hall" => vec!["trap_room", "ruins_entrance"],
        "trap_chamber" => vec!["sanctum", "hall"],
        "buried_sanctum" => vec!["trap_room"],
        _ => vec!["ruins_entrance"],
    }
    .into_iter()
    .map(str::to_string)
    .collect();

    if state.player.inventory.get("torch").copied().unwrap_or(0) > 0 {
        targets.push("torch".to_string());
    }
    targets
}

pub fn apply_events(mut state: GameState, events: &[Event]) -> GameState {
    for event in events {
        match event {
            Event::HpDelta(delta) => state.player.hp = (state.player.hp + delta).clamp(0, 100),
            Event::GoldDelta(delta) => state.player.gold = (state.player.gold + delta).max(0),
            Event::AddPlayerFlag(flag) => {
                if !state.player.flags.iter().any(|existing| existing == flag) {
                    state.player.flags.push(flag.clone());
                }
            }
            Event::AddGlobalFlag(flag) => {
                if !state
                    .world
                    .global_flags
                    .iter()
                    .any(|existing| existing == flag)
                {
                    state.world.global_flags.push(flag.clone());
                }
            }
            Event::QuestStageSet { quest_id, stage } => {
                if quest_id == "sunken_ruins" {
                    state.quests.sunken_ruins.stage = *stage;
                }
            }
            Event::AffinityDelta { npc_id, delta } => {
                let entry = state
                    .relations
                    .npc_affinity
                    .entry(npc_id.clone())
                    .or_insert(0);
                *entry += delta;
            }
            Event::MovePlayer { location_id } => state.player.location_id = location_id.clone(),
            Event::AddItem { item_id, amount } => {
                let entry = state.player.inventory.entry(item_id.clone()).or_insert(0);
                *entry = (*entry + amount).max(0);
            }
        }
    }
    state.meta.turn += 1;
    state
}

fn resolve_action(
    state: &GameState,
    content: &ContentBundle,
    action: &Action,
) -> (Vec<Event>, EngineResult) {
    match action.action_type {
        ActionType::Move => resolve_move(state, content, action.target.as_deref()),
        ActionType::Talk => resolve_talk(state),
        ActionType::Investigate => resolve_investigate(state),
        ActionType::Rest => (
            vec![Event::HpDelta(10)],
            result(true, "REST_OK", false, false, None, vec!["hp_recovered"]),
        ),
        ActionType::UseItem => resolve_use_item(state, action.target.as_deref()),
        ActionType::Flee => resolve_flee(state),
        _ => (
            Vec::new(),
            result(
                false,
                "ACTION_NOT_SUPPORTED",
                false,
                false,
                None,
                vec!["unsupported"],
            ),
        ),
    }
}

fn resolve_move(
    state: &GameState,
    content: &ContentBundle,
    target: Option<&str>,
) -> (Vec<Event>, EngineResult) {
    let target = match target {
        Some(target) => target,
        None => {
            return (
                Vec::new(),
                result(
                    false,
                    "MOVE_TARGET_MISSING",
                    false,
                    false,
                    None,
                    vec!["move_target_missing"],
                ),
            )
        }
    };

    let mapped_target = match target {
        "hall" => "collapsed_hall",
        "trap_room" => "trap_chamber",
        "sanctum" => "buried_sanctum",
        other => other,
    };

    let current = content
        .locations
        .iter()
        .find(|location| location.id == state.player.location_id);
    if let Some(current) = current {
        if current
            .connections
            .iter()
            .any(|connection| connection == mapped_target)
        {
            return (
                vec![Event::MovePlayer {
                    location_id: mapped_target.to_string(),
                }],
                result(true, "MOVE_OK", true, false, None, vec![mapped_target]),
            );
        }
    }

    (
        Vec::new(),
        result(
            false,
            "MOVE_BLOCKED",
            false,
            false,
            None,
            vec![mapped_target],
        ),
    )
}

fn resolve_talk(state: &GameState) -> (Vec<Event>, EngineResult) {
    if state.player.location_id != "ruins_entrance" {
        return (
            Vec::new(),
            result(false, "NO_NPC_TO_TALK", false, false, None, vec!["no_npc"]),
        );
    }

    if !state.has_flag("met_caretaker") {
        (
            vec![
                Event::AddPlayerFlag("met_caretaker".to_string()),
                Event::AffinityDelta {
                    npc_id: "caretaker".to_string(),
                    delta: 2,
                },
            ],
            result(
                true,
                "CARETAKER_BRIEFING",
                false,
                false,
                None,
                vec!["caretaker", "briefing"],
            ),
        )
    } else {
        (
            Vec::new(),
            result(
                true,
                "CARETAKER_WARNING",
                false,
                false,
                None,
                vec!["caretaker", "warning"],
            ),
        )
    }
}

fn resolve_investigate(state: &GameState) -> (Vec<Event>, EngineResult) {
    let stage = state.quests.sunken_ruins.stage;
    match state.player.location_id.as_str() {
        "ruins_entrance" if stage == 0 => (
            vec![
                Event::AddPlayerFlag("found_entrance_rune".to_string()),
                Event::QuestStageSet {
                    quest_id: "sunken_ruins".to_string(),
                    stage: 1,
                },
            ],
            result(true, "RUNE_FOUND", false, true, None, vec!["entrance_rune"]),
        ),
        "collapsed_hall" if stage <= 1 => (
            vec![
                Event::AddPlayerFlag("hall_mapped".to_string()),
                Event::QuestStageSet {
                    quest_id: "sunken_ruins".to_string(),
                    stage: 2,
                },
            ],
            result(
                true,
                "PASSAGE_OPENED",
                false,
                true,
                None,
                vec!["hall_route"],
            ),
        ),
        "trap_chamber" if stage <= 2 => (
            vec![
                Event::AddPlayerFlag("trap_pattern_known".to_string()),
                Event::QuestStageSet {
                    quest_id: "sunken_ruins".to_string(),
                    stage: 3,
                },
            ],
            result(
                true,
                "TRAP_REVEALED",
                false,
                true,
                None,
                vec!["trap_pattern"],
            ),
        ),
        "buried_sanctum" if stage == 3 => (
            vec![
                Event::AddPlayerFlag("altar_unsealed".to_string()),
                Event::QuestStageSet {
                    quest_id: "sunken_ruins".to_string(),
                    stage: 4,
                },
            ],
            result(true, "SEAL_BROKEN", false, true, None, vec!["altar"]),
        ),
        "buried_sanctum" if stage == 4 => (
            vec![
                Event::AddPlayerFlag("took_relic".to_string()),
                Event::QuestStageSet {
                    quest_id: "sunken_ruins".to_string(),
                    stage: 5,
                },
                Event::GoldDelta(35),
            ],
            result(true, "RELIC_SECURED", false, true, None, vec!["relic"]),
        ),
        "ruins_entrance" if stage >= 5 && state.has_flag("took_relic") => (
            vec![
                Event::AddPlayerFlag("returned_with_relic".to_string()),
                Event::QuestStageSet {
                    quest_id: "sunken_ruins".to_string(),
                    stage: 6,
                },
            ],
            result(
                true,
                "RELIC_RECOVERED",
                false,
                true,
                Some("relic_recovered".to_string()),
                vec!["ending_good"],
            ),
        ),
        _ => (
            Vec::new(),
            result(
                false,
                "NOTHING_FOUND",
                false,
                false,
                None,
                vec!["empty_search"],
            ),
        ),
    }
}

fn resolve_use_item(state: &GameState, target: Option<&str>) -> (Vec<Event>, EngineResult) {
    if target == Some("torch") && state.player.inventory.get("torch").copied().unwrap_or(0) > 0 {
        (
            vec![Event::AddPlayerFlag("torch_lit".to_string())],
            result(true, "TORCH_LIT", false, false, None, vec!["torch"]),
        )
    } else {
        (
            Vec::new(),
            result(
                false,
                "ITEM_NOT_AVAILABLE",
                false,
                false,
                None,
                vec!["missing_item"],
            ),
        )
    }
}

fn resolve_flee(state: &GameState) -> (Vec<Event>, EngineResult) {
    let ending = if state.has_flag("took_relic") {
        "retreated_alive"
    } else if state.player.location_id == "buried_sanctum" && state.quests.sunken_ruins.stage >= 4 {
        "greed_awakened"
    } else {
        "retreated_alive"
    };

    (
        vec![
            Event::AddPlayerFlag("retreated_from_ruins".to_string()),
            Event::QuestStageSet {
                quest_id: "sunken_ruins".to_string(),
                stage: 99,
            },
        ],
        result(
            true,
            if ending == "greed_awakened" {
                "CURSE_TRIGGERED"
            } else {
                "RETREAT_END"
            },
            false,
            true,
            Some(ending.to_string()),
            vec!["retreat"],
        ),
    )
}

fn result(
    success: bool,
    message_code: &str,
    location_changed: bool,
    quest_stage_changed: bool,
    ending_reached: Option<String>,
    details: Vec<&str>,
) -> EngineResult {
    EngineResult {
        success,
        message_code: message_code.to_string(),
        location_changed,
        quest_stage_changed,
        ending_reached,
        details: details.into_iter().map(str::to_string).collect(),
    }
}

fn contains_any(haystack: &str, needles: &[&str]) -> bool {
    needles.iter().any(|needle| haystack.contains(needle))
}

#[cfg(test)]
mod tests {
    use super::*;
    use domain::initial_state;

    #[test]
    fn reducer_clamps_hp() {
        let state = initial_state();
        let next = apply_events(state, &[Event::HpDelta(-300)]);
        assert_eq!(next.player.hp, 0);
    }

    #[test]
    fn engine_is_deterministic_for_same_input() {
        let state = initial_state();
        let content = ContentBundle::load_from_disk(repo_content_root()).expect("content");
        let left = resolve_text_action(&state, &content, "주변을 조사한다");
        let right = resolve_text_action(&state, &content, "주변을 조사한다");
        assert_eq!(left.engine_result, right.engine_result);
        assert_eq!(left.next_state, right.next_state);
    }

    #[test]
    fn relic_can_be_recovered() {
        let content = ContentBundle::load_from_disk(repo_content_root()).expect("content");
        let mut state = initial_state();
        let steps = [
            "주변을 조사한다",
            "회랑으로 이동한다",
            "주변을 조사한다",
            "함정방으로 이동한다",
            "주변을 조사한다",
            "성소로 이동한다",
            "주변을 조사한다",
            "주변을 조사한다",
            "함정방으로 이동한다",
            "회랑으로 이동한다",
            "입구로 이동한다",
            "주변을 조사한다",
        ];

        for step in steps {
            state = resolve_text_action(&state, &content, step).next_state;
        }

        assert_eq!(state.quests.sunken_ruins.stage, 6);
        assert!(state
            .player
            .flags
            .iter()
            .any(|flag| flag == "returned_with_relic"));
    }

    fn repo_content_root() -> std::path::PathBuf {
        std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../../content")
            .canonicalize()
            .expect("repo content dir")
    }
}
