use std::{
    collections::HashMap,
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
    sync::{Arc, Mutex},
    time::{SystemTime, UNIX_EPOCH},
};

use content::ContentBundle;
use domain::{debug_log, initial_state, GameState, TurnResult};
use engine::resolve_text_action;
use narrative::{
    opening_narrative_with_gemini, render_turn_with_gemini, GeminiConfig, NarrativeTurn,
};

#[derive(Clone)]
struct SessionRecord {
    state: GameState,
    gemini: Option<GeminiConfig>,
}

#[derive(Clone, Default)]
pub struct StartOptions {
    pub gemini_api_key: Option<String>,
    pub gemini_model: Option<String>,
}

#[derive(Clone)]
pub struct GameSessionService {
    content_root: PathBuf,
    sessions: Arc<Mutex<HashMap<String, SessionRecord>>>,
}

impl GameSessionService {
    pub fn new(content_root: impl AsRef<Path>) -> Self {
        Self {
            content_root: content_root.as_ref().to_path_buf(),
            sessions: Arc::new(Mutex::new(HashMap::new())),
        }
    }

    pub async fn start_game(&self, options: StartOptions) -> Result<(String, TurnResult), String> {
        let session_id = next_session_id();
        let state = initial_state();
        let content = self.content()?;
        let gemini = build_gemini_config(options);
        debug_log(
            "session_started",
            &[
                ("session_id", session_id.clone()),
                ("llm_enabled", gemini.is_some().to_string()),
                (
                    "gemini_model",
                    gemini
                        .as_ref()
                        .map(|config| config.model.clone())
                        .unwrap_or_else(|| "-".to_string()),
                ),
            ],
        );
        let generated = opening_narrative_with_gemini(&state, &content, gemini.as_ref()).await;
        log_narrative(&session_id, &generated);
        let turn = TurnResult {
            narrative: generated.narrative,
            choices: generated.choices,
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
            .insert(
                session_id.clone(),
                SessionRecord {
                    state,
                    gemini,
                },
            );

        Ok((session_id, turn))
    }

    pub async fn apply_input(&self, session_id: &str, input: &str) -> Result<TurnResult, String> {
        let content = self.content()?;
        debug_log(
            "user_input",
            &[
                ("session_id", session_id.to_string()),
                ("raw_input", input.to_string()),
            ],
        );
        let session = {
            let sessions = self
                .sessions
                .lock()
                .map_err(|_| "session lock poisoned".to_string())?;
            sessions
                .get(session_id)
                .cloned()
                .ok_or_else(|| "session not found".to_string())?
        };
        let state = session.state;

        let resolution = resolve_text_action(&state, &content, input);
        let generated = render_turn_with_gemini(
            &resolution.next_state,
            &resolution.engine_result,
            &content,
            session.gemini.as_ref(),
        )
        .await;
        log_narrative(session_id, &generated);
        let turn = TurnResult {
            narrative: generated.narrative,
            choices: generated.choices,
            state: resolution.next_state.clone(),
            engine_result: resolution.engine_result,
        };

        self.sessions
            .lock()
            .map_err(|_| "session lock poisoned".to_string())?
            .insert(
            session_id.to_string(),
            SessionRecord {
                state: resolution.next_state,
                gemini: session.gemini,
            },
        );
        Ok(turn)
    }

    pub fn get_state(&self, session_id: &str) -> Result<GameState, String> {
        self.sessions
            .lock()
            .map_err(|_| "session lock poisoned".to_string())?
            .get(session_id)
            .map(|session| session.state.clone())
            .ok_or_else(|| "session not found".to_string())
    }

    pub async fn demo_script(&self) -> Result<Vec<TurnResult>, String> {
        let (session_id, start) = self.start_game(StartOptions::default()).await?;
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
            turns.push(self.apply_input(&session_id, input).await?);
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

fn build_gemini_config(options: StartOptions) -> Option<GeminiConfig> {
    let api_key = options
        .gemini_api_key
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())?;
    let model = options
        .gemini_model
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| "models/gemini-2.5-flash".to_string());
    Some(GeminiConfig { api_key, model })
}

fn log_narrative(session_id: &str, generated: &NarrativeTurn) {
    debug_log(
        "narrative_generated",
        &[
            ("session_id", session_id.to_string()),
            ("source", format!("{:?}", generated.source)),
            ("choices", generated.choices.join(" | ")),
            ("narrative", generated.narrative.clone()),
        ],
    );
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn session_can_progress_multiple_turns() {
        let service = GameSessionService::new(repo_content_root());
        let (session_id, _) = service
            .start_game(StartOptions::default())
            .await
            .expect("game start");
        let turn = service
            .apply_input(&session_id, "주변을 조사한다")
            .await
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
