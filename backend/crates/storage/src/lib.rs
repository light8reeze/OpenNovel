use domain::GameState;

#[derive(Debug, Clone)]
pub struct StoredTurn {
    pub session_id: String,
    pub state: GameState,
    pub memory_summary: Option<String>,
}

pub trait SessionStore {
    fn save(&self, turn: StoredTurn) -> Result<(), String>;
    fn load(&self, session_id: &str) -> Result<Option<GameState>, String>;
}
