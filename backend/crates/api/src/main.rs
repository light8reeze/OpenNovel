use std::{env, net::SocketAddr, sync::Arc};

use axum::{
    extract::{Query, State},
    http::StatusCode,
    response::{Html, IntoResponse},
    routing::{get, post},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use session::{GameSessionService, StartOptions};

#[derive(Clone)]
struct AppState {
    service: Arc<GameSessionService>,
}

#[derive(Debug, Deserialize)]
struct ActionRequest {
    #[serde(rename = "sessionId")]
    session_id: String,
    #[serde(rename = "inputText")]
    input_text: Option<String>,
    #[serde(rename = "choiceText")]
    choice_text: Option<String>,
}

#[derive(Debug, Deserialize)]
struct StateQuery {
    #[serde(rename = "sessionId")]
    session_id: String,
}

#[derive(Debug, Serialize)]
struct StartResponse {
    #[serde(rename = "sessionId")]
    session_id: String,
    narrative: String,
    choices: Vec<String>,
    state: domain::GameState,
}

#[derive(Debug, Deserialize, Default)]
struct StartRequest {
    #[serde(rename = "geminiApiKey")]
    gemini_api_key: Option<String>,
    #[serde(rename = "geminiModel")]
    gemini_model: Option<String>,
}

#[derive(Debug, Serialize)]
struct ActionResponse {
    narrative: String,
    choices: Vec<String>,
    #[serde(rename = "engineResult")]
    engine_result: domain::EngineResult,
    state: domain::GameState,
}

#[tokio::main]
async fn main() {
    let service = Arc::new(GameSessionService::new(repo_content_root()));

    if env::args().any(|arg| arg == "--demo") {
        run_demo(service).await;
        return;
    }

    let app = Router::new()
        .route("/", get(index))
        .route("/frontend/app.js", get(frontend_script))
        .route("/frontend/styles.css", get(frontend_styles))
        .route("/game/start", post(start_game))
        .route("/game/action", post(apply_action))
        .route("/game/state", get(get_state))
        .with_state(AppState { service });

    let address = SocketAddr::from(([127, 0, 0, 1], 3000));
    println!("listening on http://{}", address);
    axum::Server::bind(&address)
        .serve(app.into_make_service())
        .await
        .expect("serve app");
}

async fn run_demo(service: Arc<GameSessionService>) {
    let turns = service.demo_script().await.expect("run demo");
    for (index, turn) in turns.iter().enumerate() {
        println!(
            "[turn {}] code={} stage={} narrative={}",
            index,
            turn.engine_result.message_code,
            turn.state.quests.murder_case.stage,
            turn.narrative
        );
    }
}

async fn index() -> Html<&'static str> {
    Html(include_str!("../../../../frontend/index.html"))
}

async fn frontend_script() -> impl IntoResponse {
    (
        [(
            axum::http::header::CONTENT_TYPE,
            "application/javascript; charset=utf-8",
        )],
        include_str!("../../../../frontend/app.js"),
    )
}

async fn frontend_styles() -> impl IntoResponse {
    (
        [(axum::http::header::CONTENT_TYPE, "text/css; charset=utf-8")],
        include_str!("../../../../frontend/styles.css"),
    )
}

async fn start_game(
    State(state): State<AppState>,
    payload: Option<Json<StartRequest>>,
) -> Result<Json<StartResponse>, ApiError> {
    let payload = payload.map(|value| value.0).unwrap_or_default();
    let api_key = payload
        .gemini_api_key
        .or_else(|| env::var("GEMINI_API_KEY").ok());
    let model = payload
        .gemini_model
        .or_else(|| env::var("GEMINI_MODEL").ok());
    let (session_id, turn) = state
        .service
        .start_game(StartOptions {
            gemini_api_key: api_key,
            gemini_model: model,
        })
        .await
        .map_err(ApiError::internal)?;
    Ok(Json(StartResponse {
        session_id,
        narrative: turn.narrative,
        choices: turn.choices,
        state: turn.state,
    }))
}

async fn apply_action(
    State(state): State<AppState>,
    Json(payload): Json<ActionRequest>,
) -> Result<Json<ActionResponse>, ApiError> {
    let input = match (&payload.input_text, &payload.choice_text) {
        (Some(_), Some(_)) => {
            return Err(ApiError::bad_request(
                "inputText and choiceText cannot both be set",
            ))
        }
        (Some(input), None) => input,
        (None, Some(choice)) => choice,
        (None, None) => {
            return Err(ApiError::bad_request(
                "one of inputText or choiceText is required",
            ))
        }
    };

    let turn = state
        .service
        .apply_input(&payload.session_id, input)
        .await
        .map_err(ApiError::from_session)?;
    Ok(Json(ActionResponse {
        narrative: turn.narrative,
        choices: turn.choices,
        engine_result: turn.engine_result,
        state: turn.state,
    }))
}

async fn get_state(
    State(state): State<AppState>,
    Query(query): Query<StateQuery>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let game_state = state
        .service
        .get_state(&query.session_id)
        .map_err(ApiError::from_session)?;
    Ok(Json(serde_json::json!({ "state": game_state })))
}

struct ApiError {
    status: StatusCode,
    message: String,
}

impl ApiError {
    fn bad_request(message: &str) -> Self {
        Self {
            status: StatusCode::BAD_REQUEST,
            message: message.to_string(),
        }
    }

    fn internal(message: String) -> Self {
        Self {
            status: StatusCode::INTERNAL_SERVER_ERROR,
            message,
        }
    }

    fn from_session(message: String) -> Self {
        if message == "session not found" {
            Self {
                status: StatusCode::NOT_FOUND,
                message,
            }
        } else {
            Self::internal(message)
        }
    }
}

impl IntoResponse for ApiError {
    fn into_response(self) -> axum::response::Response {
        let body = Json(serde_json::json!({ "error": self.message }));
        (self.status, body).into_response()
    }
}

fn repo_content_root() -> std::path::PathBuf {
    std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../../content")
        .canonicalize()
        .expect("repo content dir")
}
