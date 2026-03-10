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
    let action = parse_action(input);
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

pub fn apply_events(mut state: GameState, events: &[Event]) -> GameState {
    for event in events {
        match event {
            Event::HpDelta(delta) => {
                state.player.hp = (state.player.hp + delta).clamp(0, 100);
            }
            Event::GoldDelta(delta) => {
                state.player.gold = (state.player.gold + delta).max(0);
            }
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
                if quest_id == "murder_case" {
                    state.quests.murder_case.stage = *stage;
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
            Event::MovePlayer { location_id } => {
                state.player.location_id = location_id.clone();
            }
            Event::AddItem { item_id, amount } => {
                let entry = state.player.inventory.entry(item_id.clone()).or_insert(0);
                *entry = (*entry + amount).max(0);
            }
        }
    }

    state.meta.turn += 1;
    state
}

fn parse_action(input: &str) -> Action {
    let normalized = input.trim().to_lowercase();
    let (action_type, target) = if contains_any(&normalized, &["창고", "warehouse"]) {
        (ActionType::Move, Some("warehouse".to_string()))
    } else if contains_any(&normalized, &["골목", "alley"]) {
        (ActionType::Move, Some("alley".to_string()))
    } else if contains_any(&normalized, &["여관", "tavern", "inn"]) {
        (ActionType::Move, Some("tavern".to_string()))
    } else if contains_any(&normalized, &["광장", "square"]) {
        (ActionType::Move, Some("village_square".to_string()))
    } else if contains_any(&normalized, &["아리아", "aria", "대화", "talk"]) {
        (ActionType::Talk, Some("aria".to_string()))
    } else if contains_any(&normalized, &["휴식", "rest"]) {
        (ActionType::Rest, None)
    } else if contains_any(&normalized, &["횃불", "torch"]) {
        (ActionType::UseItem, Some("torch".to_string()))
    } else if contains_any(&normalized, &["도망", "flee"]) {
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
        "warehouse" => "village_warehouse",
        "alley" => "dark_alley",
        "tavern" => "crooked_tavern",
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
    let stage = state.quests.murder_case.stage;
    match state.player.location_id.as_str() {
        "village_square" | "village_warehouse" => {
            if stage < 3 && state.has_flag("found_bloody_cloth") {
                (
                    vec![
                        Event::AddPlayerFlag("met_aria".to_string()),
                        Event::AffinityDelta {
                            npc_id: "aria".to_string(),
                            delta: 5,
                        },
                        Event::QuestStageSet {
                            quest_id: "murder_case".to_string(),
                            stage: 3,
                        },
                    ],
                    result(
                        true,
                        "ARIA_CLUE_CONFIRMED",
                        false,
                        true,
                        None,
                        vec!["aria", "quest_advanced"],
                    ),
                )
            } else {
                (
                    vec![Event::AddPlayerFlag("met_aria".to_string())],
                    result(true, "ARIA_SMALL_TALK", false, false, None, vec!["aria"]),
                )
            }
        }
        "crooked_tavern" => {
            if stage >= 4 {
                (
                    vec![
                        Event::AddPlayerFlag("innkeeper_testimony".to_string()),
                        Event::QuestStageSet {
                            quest_id: "murder_case".to_string(),
                            stage: 5,
                        },
                    ],
                    result(
                        true,
                        "INNKEEPER_TESTIMONY",
                        false,
                        true,
                        None,
                        vec!["innkeeper", "quest_advanced"],
                    ),
                )
            } else {
                (
                    Vec::new(),
                    result(
                        false,
                        "NO_USEFUL_DIALOGUE",
                        false,
                        false,
                        None,
                        vec!["innkeeper"],
                    ),
                )
            }
        }
        _ => (
            Vec::new(),
            result(false, "NO_NPC_TO_TALK", false, false, None, vec!["no_npc"]),
        ),
    }
}

fn resolve_investigate(state: &GameState) -> (Vec<Event>, EngineResult) {
    let stage = state.quests.murder_case.stage;
    match state.player.location_id.as_str() {
        "village_square" if stage == 0 => (
            vec![
                Event::AddPlayerFlag("found_blood_mark".to_string()),
                Event::QuestStageSet {
                    quest_id: "murder_case".to_string(),
                    stage: 1,
                },
            ],
            result(
                true,
                "BLOOD_MARK_FOUND",
                false,
                true,
                None,
                vec!["blood_mark"],
            ),
        ),
        "village_warehouse" if stage <= 2 => (
            vec![
                Event::AddPlayerFlag("found_bloody_cloth".to_string()),
                Event::QuestStageSet {
                    quest_id: "murder_case".to_string(),
                    stage: 2,
                },
            ],
            result(
                true,
                "BLOODY_CLOTH_FOUND",
                false,
                stage != 2,
                None,
                vec!["bloody_cloth"],
            ),
        ),
        "dark_alley" if stage >= 3 && stage < 4 => (
            vec![
                Event::AddPlayerFlag("saw_shadow_in_alley".to_string()),
                Event::QuestStageSet {
                    quest_id: "murder_case".to_string(),
                    stage: 4,
                },
            ],
            result(
                true,
                "SHADOW_TRACKED",
                false,
                true,
                None,
                vec!["shadow", "quest_advanced"],
            ),
        ),
        "crooked_tavern" if stage >= 5 => (
            vec![
                Event::AddPlayerFlag("case_closed".to_string()),
                Event::QuestStageSet {
                    quest_id: "murder_case".to_string(),
                    stage: 6,
                },
                Event::GoldDelta(30),
            ],
            result(
                true,
                "GOOD_END_UNLOCKED",
                false,
                true,
                Some("truth_revealed".to_string()),
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
    if state.quests.murder_case.stage >= 4 {
        (
            vec![
                Event::AddPlayerFlag("coward_ending".to_string()),
                Event::QuestStageSet {
                    quest_id: "murder_case".to_string(),
                    stage: 99,
                },
            ],
            result(
                true,
                "BAD_END_FLEE",
                false,
                true,
                Some("cowardice".to_string()),
                vec!["ending_bad"],
            ),
        )
    } else {
        (
            Vec::new(),
            result(
                false,
                "FLEE_TOO_EARLY",
                false,
                false,
                None,
                vec!["flee_blocked"],
            ),
        )
    }
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
    fn murder_case_can_reach_good_ending() {
        let content = ContentBundle::load_from_disk(repo_content_root()).expect("content");
        let mut state = initial_state();
        let steps = [
            "주변을 조사한다",
            "창고로 이동한다",
            "주변을 조사한다",
            "아리아와 대화한다",
            "골목으로 이동한다",
            "주변을 조사한다",
            "여관으로 이동한다",
            "아리아와 대화한다",
            "주변을 조사한다",
        ];

        for step in steps {
            state = resolve_text_action(&state, &content, step).next_state;
        }

        assert_eq!(state.quests.murder_case.stage, 6);
        assert!(state.player.flags.iter().any(|flag| flag == "case_closed"));
    }

    fn repo_content_root() -> std::path::PathBuf {
        std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../../content")
            .canonicalize()
            .expect("repo content dir")
    }
}
