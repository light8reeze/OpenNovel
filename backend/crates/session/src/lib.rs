use std::{
    collections::HashMap,
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
    sync::{Arc, Mutex},
    time::{SystemTime, UNIX_EPOCH},
};

use content::ContentBundle;
use domain::{initial_state, GameState, TurnResult};
use engine::resolve_text_action;
use narrative::{opening_narrative, render_turn};
#[derive(Clone)]
pub struct GameSessionService {
    content_root: PathBuf,
    sessions: Arc<Mutex<HashMap<String, GameState>>>,
}

impl GameSessionService {
    pub fn new(content_root: impl AsRef<Path>) -> Self {
        Self {
            content_root: content_root.as_ref().to_path_buf(),
            sessions: Arc::new(Mutex::new(HashMap::new())),
        }
    }

    pub fn start_game(&self) -> Result<(String, TurnResult), String> {
        let session_id = next_session_id();
        let state = initial_state();
        let content = self.content()?;
        let (narrative, choices) = opening_narrative(&state, &content);
        let turn = TurnResult {
            narrative,
            choices,
            state: state.clone(),
            engine_result: domain::EngineResult {
                success: true,
                message_code: "GAME_STARTED".to_string(),
                location_changed: false,
                quest_stage_changed: false,
                ending_reached: None,
                details: vec!["session_started".to_string()],
            },
        };

        self.sessions
            .lock()
            .map_err(|_| "session lock poisoned".to_string())?
            .insert(session_id.clone(), state);

        Ok((session_id, turn))
    }

    pub fn apply_input(&self, session_id: &str, input: &str) -> Result<TurnResult, String> {
        let content = self.content()?;
        let mut sessions = self
            .sessions
            .lock()
            .map_err(|_| "session lock poisoned".to_string())?;
        let state = sessions
            .get(session_id)
            .cloned()
            .ok_or_else(|| "session not found".to_string())?;

        let resolution = resolve_text_action(&state, &content, input);
        let (narrative, choices) = render_turn(&resolution.next_state, &resolution.engine_result, &content);
        let turn = TurnResult {
            narrative,
            choices,
            state: resolution.next_state.clone(),
            engine_result: resolution.engine_result,
        };

        sessions.insert(session_id.to_string(), resolution.next_state);
        Ok(turn)
    }

    pub fn get_state(&self, session_id: &str) -> Result<GameState, String> {
        self.sessions
            .lock()
            .map_err(|_| "session lock poisoned".to_string())?
            .get(session_id)
            .cloned()
            .ok_or_else(|| "session not found".to_string())
    }

    pub fn demo_script(&self) -> Result<Vec<TurnResult>, String> {
        let (session_id, start) = self.start_game()?;
        let mut turns = vec![start];
        for input in [
            "주변을 조사한다",
            "창고로 이동한다",
            "주변을 조사한다",
            "아리아와 대화한다",
            "골목으로 이동한다",
            "주변을 조사한다",
            "여관으로 이동한다",
            "아리아와 대화한다",
            "주변을 조사한다",
        ] {
            turns.push(self.apply_input(&session_id, input)?);
        }
        Ok(turns)
    }

    fn content(&self) -> Result<ContentBundle, String> {
        ContentBundle::load_from_disk(&self.content_root)
    }
}

fn next_session_id() -> String {
    static COUNTER: AtomicU64 = AtomicU64::new(1);
    let sequence = COUNTER.fetch_add(1, Ordering::Relaxed);
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis())
        .unwrap_or_default();
    format!("session-{}-{}", timestamp, sequence)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn session_can_progress_multiple_turns() {
        let service = GameSessionService::new(repo_content_root());
        let (session_id, _) = service.start_game().expect("game start");
        let turn = service
            .apply_input(&session_id, "주변을 조사한다")
            .expect("first turn");
        assert_eq!(turn.state.quests.murder_case.stage, 1);
        let loaded = service.get_state(&session_id).expect("state");
        assert_eq!(loaded.meta.turn, 1);
    }

    fn repo_content_root() -> std::path::PathBuf {
        std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../../content")
            .canonicalize()
            .expect("repo content dir")
    }
}
