use std::collections::BTreeMap;
use std::env;

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct MetaState {
    pub turn: u32,
    pub seed: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct PlayerState {
    pub hp: i32,
    pub gold: i32,
    pub location_id: String,
    pub inventory: BTreeMap<String, i32>,
    pub flags: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct WorldState {
    pub time: String,
    pub global_flags: Vec<String>,
    pub alert_by_region: BTreeMap<String, i32>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct QuestProgress {
    pub stage: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct QuestState {
    pub murder_case: QuestProgress,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct RelationsState {
    pub npc_affinity: BTreeMap<String, i32>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct GameState {
    pub meta: MetaState,
    pub player: PlayerState,
    pub world: WorldState,
    pub quests: QuestState,
    pub relations: RelationsState,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum ActionType {
    Move,
    Talk,
    Attack,
    Investigate,
    Rest,
    UseItem,
    Flee,
    Trade,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Action {
    pub action_type: ActionType,
    pub target: Option<String>,
    pub raw_input: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(tag = "kind", content = "value")]
pub enum Event {
    HpDelta(i32),
    GoldDelta(i32),
    AddPlayerFlag(String),
    AddGlobalFlag(String),
    QuestStageSet { quest_id: String, stage: u32 },
    AffinityDelta { npc_id: String, delta: i32 },
    MovePlayer { location_id: String },
    AddItem { item_id: String, amount: i32 },
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct EngineResult {
    pub success: bool,
    pub message_code: String,
    pub location_changed: bool,
    pub quest_stage_changed: bool,
    pub ending_reached: Option<String>,
    pub details: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct StateSummary {
    pub turn: u32,
    pub location_id: String,
    pub hp: i32,
    pub gold: i32,
    pub murder_case_stage: u32,
    pub player_flags: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct TurnResult {
    pub narrative: String,
    pub choices: Vec<String>,
    pub state: GameState,
    pub engine_result: EngineResult,
}

pub fn initial_state() -> GameState {
    let mut inventory = BTreeMap::new();
    inventory.insert("torch".to_string(), 1);

    let mut alert_by_region = BTreeMap::new();
    alert_by_region.insert("village".to_string(), 10);

    let mut npc_affinity = BTreeMap::new();
    npc_affinity.insert("aria".to_string(), 10);
    npc_affinity.insert("innkeeper".to_string(), 0);

    GameState {
        meta: MetaState { turn: 0, seed: 12345 },
        player: PlayerState {
            hp: 100,
            gold: 20,
            location_id: "village_square".to_string(),
            inventory,
            flags: Vec::new(),
        },
        world: WorldState {
            time: "night".to_string(),
            global_flags: vec!["murder_case_active".to_string()],
            alert_by_region,
        },
        quests: QuestState {
            murder_case: QuestProgress { stage: 0 },
        },
        relations: RelationsState { npc_affinity },
    }
}

impl GameState {
    pub fn summary(&self) -> StateSummary {
        StateSummary {
            turn: self.meta.turn,
            location_id: self.player.location_id.clone(),
            hp: self.player.hp,
            gold: self.player.gold,
            murder_case_stage: self.quests.murder_case.stage,
            player_flags: self.player.flags.clone(),
        }
    }

    pub fn has_flag(&self, flag: &str) -> bool {
        self.player.flags.iter().any(|value| value == flag)
            || self.world.global_flags.iter().any(|value| value == flag)
    }
}

pub fn debug_enabled() -> bool {
    matches!(
        env::var("NOVEL_GG_DEBUG").ok().as_deref(),
        Some("1") | Some("true") | Some("TRUE") | Some("yes") | Some("YES")
    )
}

pub fn debug_log(event: &str, fields: &[(&str, String)]) {
    if !debug_enabled() {
        return;
    }

    let mut line = format!("[debug] event={}", event);
    for (key, value) in fields {
        line.push(' ');
        line.push_str(key);
        line.push('=');
        line.push('"');
        line.push_str(&sanitize_log_value(value));
        line.push('"');
    }
    eprintln!("{}", line);
}

fn sanitize_log_value(value: &str) -> String {
    let mut sanitized = value.replace('\n', "\\n");
    if sanitized.len() > 240 {
        sanitized.truncate(237);
        sanitized.push_str("...");
    }
    sanitized
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn initial_state_matches_contract() {
        let state = initial_state();
        assert_eq!(state.meta.turn, 0);
        assert_eq!(state.player.location_id, "village_square");
        assert_eq!(state.quests.murder_case.stage, 0);
        assert_eq!(state.player.inventory.get("torch"), Some(&1));
    }

    #[test]
    fn game_state_round_trip_json() {
        let state = initial_state();
        let json = serde_json::to_string(&state).expect("serialize");
        let restored: GameState = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(restored, state);
    }
}
