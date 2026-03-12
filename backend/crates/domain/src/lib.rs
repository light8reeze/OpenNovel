use std::collections::BTreeMap;
use std::{
    env,
    fs::{self, OpenOptions},
    io::Write,
    path::PathBuf,
    time::{SystemTime, UNIX_EPOCH},
};

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
    pub sunken_ruins: QuestProgress,
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
pub struct SceneContext {
    pub location_name: String,
    pub npcs_in_scene: Vec<String>,
    pub visible_targets: Vec<String>,
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
    pub sunken_ruins_stage: u32,
    pub player_flags: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct IntentValidationRequest {
    pub player_input: String,
    pub allowed_actions: Vec<ActionType>,
    pub state_summary: StateSummary,
    pub scene_context: SceneContext,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct IntentValidationResponse {
    pub action: Action,
    pub confidence: f32,
    pub validation_flags: Vec<String>,
    pub source: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct NarrativeRequest {
    pub state_summary: StateSummary,
    pub scene_context: SceneContext,
    pub engine_result: Option<EngineResult>,
    pub allowed_choices: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct NarrativeResponse {
    pub narrative: String,
    pub choices: Vec<String>,
    pub source: String,
    pub used_fallback: bool,
    pub safety_flags: Vec<String>,
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
    alert_by_region.insert("ruins".to_string(), 6);

    let mut npc_affinity = BTreeMap::new();
    npc_affinity.insert("caretaker".to_string(), 5);

    GameState {
        meta: MetaState {
            turn: 0,
            seed: 12345,
        },
        player: PlayerState {
            hp: 100,
            gold: 15,
            location_id: "ruins_entrance".to_string(),
            inventory,
            flags: Vec::new(),
        },
        world: WorldState {
            time: "night".to_string(),
            global_flags: vec!["sunken_ruins_open".to_string()],
            alert_by_region,
        },
        quests: QuestState {
            sunken_ruins: QuestProgress { stage: 0 },
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
            sunken_ruins_stage: self.quests.sunken_ruins.stage,
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

pub fn append_json_log(file_name: &str, payload: &serde_json::Value) {
    let log_dir = backend_log_dir();
    if fs::create_dir_all(&log_dir).is_err() {
        return;
    }

    let mut line = payload.clone();
    if let serde_json::Value::Object(ref mut map) = line {
        map.entry("ts".to_string())
            .or_insert_with(|| serde_json::Value::String(log_timestamp()));
        map.entry("ts_unix_ms".to_string())
            .or_insert_with(|| serde_json::Value::Number(log_timestamp_unix_ms().into()));
        map.entry("service".to_string())
            .or_insert_with(|| serde_json::Value::String("backend".to_string()));
    }

    append_json_line(&log_dir.join(file_name), &line);
    append_json_line(&combined_log_path(), &line);
}

fn sanitize_log_value(value: &str) -> String {
    let mut sanitized = value.replace('\n', "\\n");
    if sanitized.len() > 240 {
        sanitized.truncate(237);
        sanitized.push_str("...");
    }
    sanitized
}

fn backend_log_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .join("log")
        .join("backend")
}

fn combined_log_path() -> PathBuf {
    let run_id = env::var("OPENNOVEL_RUN_ID").unwrap_or_else(|_| "manual".to_string());
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .join("log")
        .join("combined")
        .join(format!("run-{}.jsonl", run_id))
}

fn log_timestamp() -> String {
    let Ok(duration) = SystemTime::now().duration_since(UNIX_EPOCH) else {
        return "0".to_string();
    };
    duration.as_secs().to_string()
}

fn log_timestamp_unix_ms() -> u64 {
    let Ok(duration) = SystemTime::now().duration_since(UNIX_EPOCH) else {
        return 0;
    };
    duration.as_millis() as u64
}

fn append_json_line(path: &PathBuf, payload: &serde_json::Value) {
    if let Some(parent) = path.parent() {
        if fs::create_dir_all(parent).is_err() {
            return;
        }
    }

    let Ok(mut file) = OpenOptions::new().create(true).append(true).open(path) else {
        return;
    };

    if serde_json::to_writer(&mut file, payload).is_err() {
        return;
    }
    let _ = file.write_all(b"\n");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn initial_state_matches_contract() {
        let state = initial_state();
        assert_eq!(state.meta.turn, 0);
        assert_eq!(state.player.location_id, "ruins_entrance");
        assert_eq!(state.quests.sunken_ruins.stage, 0);
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
