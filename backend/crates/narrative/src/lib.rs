use content::ContentBundle;
use domain::{debug_log, EngineResult, GameState};
use serde::{Deserialize, Serialize};
use std::process::Command;

const DEFAULT_GEMINI_MODEL: &str = "models/gemini-2.5-flash";

#[derive(Debug, Clone)]
pub struct GeminiConfig {
    pub api_key: String,
    pub model: String,
}

#[derive(Debug, Deserialize)]
struct GeminiResponse {
    candidates: Option<Vec<GeminiCandidate>>,
}

#[derive(Debug, Deserialize)]
struct GeminiCandidate {
    content: Option<GeminiContent>,
}

#[derive(Debug, Deserialize)]
struct GeminiContent {
    parts: Option<Vec<GeminiPart>>,
}

#[derive(Debug, Deserialize)]
struct GeminiPart {
    text: Option<String>,
}

#[derive(Debug, Serialize)]
struct GenerateContentRequest {
    contents: Vec<PromptContent>,
}

#[derive(Debug, Serialize)]
struct PromptContent {
    parts: Vec<PromptPart>,
}

#[derive(Debug, Serialize)]
struct PromptPart {
    text: String,
}

#[derive(Debug, Deserialize)]
struct NarrativeJson {
    narrative: String,
    choices: Vec<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NarrativeSource {
    ExternalAgent,
    Gemini,
    Fallback,
}

pub struct NarrativeTurn {
    pub narrative: String,
    pub choices: Vec<String>,
    pub source: NarrativeSource,
}

pub fn opening_narrative(state: &GameState, content: &ContentBundle) -> (String, Vec<String>) {
    let location = content.location_name(&state.player.location_id);
    let narrative = format!(
        "{}. 축축한 밤공기 속에서 마을 광장은 숨을 죽인 채 가라앉아 있다. 먼 곳에서 누군가 서둘러 문을 닫는 소리가 들린다.",
        location
    );
    let choices = choices_for_state(state);
    (narrative, choices)
}

pub async fn opening_narrative_with_gemini(
    state: &GameState,
    content: &ContentBundle,
    config: Option<&GeminiConfig>,
) -> NarrativeTurn {
    let fallback = opening_narrative(state, content);
    let Some(config) = config else {
        return fallback_turn(fallback);
    };

    let prompt = format!(
        "너는 텍스트 기반 인터랙티브 소설 게임의 narrative generator다.\n\
게임의 진실은 state와 engine_result뿐이다.\n\
상태를 변경하지 말고, 아래 정보만 바탕으로 JSON으로만 응답하라.\n\
JSON 형식: {{\"narrative\":\"...\",\"choices\":[\"...\",\"...\"]}}\n\
선택지는 2개 이상 4개 이하.\n\
\n\
장면 시작 정보:\n\
- location: {}\n\
- quest_stage: {}\n\
- hp: {}\n\
- gold: {}\n\
- player_flags: {:?}\n\
\n\
톤: dark fantasy mystery, concise Korean prose.",
        state.player.location_id,
        state.quests.murder_case.stage,
        state.player.hp,
        state.player.gold,
        state.player.flags,
    );

    generate_json_narrative(config, prompt, fallback, "opening_narrative").await
}

pub fn render_turn(
    state: &GameState,
    engine_result: &EngineResult,
    content: &ContentBundle,
) -> (String, Vec<String>) {
    let location = content.location_name(&state.player.location_id);
    let narrative = match engine_result.message_code.as_str() {
        "MOVE_OK" => format!("당신은 조심스럽게 {} 쪽으로 발걸음을 옮긴다.", location),
        "BLOOD_MARK_FOUND" => {
            "젖은 돌바닥 틈에서 마르다 만 핏자국이 길게 이어진다. 흔적은 창고 방향을 가리킨다.".to_string()
        }
        "BLOODY_CLOTH_FOUND" => {
            "낡은 상자 틈에서 피가 눌어붙은 천 조각이 나온다. 누군가 급히 숨긴 흔적이다.".to_string()
        }
        "ARIA_CLUE_CONFIRMED" => {
            "아리아는 천 조각을 보자 짧게 숨을 삼킨다. 그녀는 골목에서 검은 망토를 본 적이 있다고 털어놓는다.".to_string()
        }
        "SHADOW_TRACKED" => {
            "골목의 진흙 바닥에 깊은 장화 자국이 남아 있다. 흔적은 여관 뒤편으로 이어진다.".to_string()
        }
        "INNKEEPER_TESTIMONY" => {
            "여관 주인은 한참을 망설이다가, 늦은 밤 피 묻은 남자가 뒷문으로 들어왔다고 말한다.".to_string()
        }
        "GOOD_END_UNLOCKED" => {
            "엉켜 있던 진실이 마침내 하나로 모인다. 마을 사람들은 살인 사건의 진범이 드러났다는 소식에 술렁인다.".to_string()
        }
        "BAD_END_FLEE" => {
            "당신은 등을 돌린다. 사건은 미궁으로 빠지고, 마을에는 더 짙은 불신만 남는다.".to_string()
        }
        "NOTHING_FOUND" => "눈에 띄는 변화는 없다. 하지만 침묵이 오히려 불길하게 느껴진다.".to_string(),
        "NO_USEFUL_DIALOGUE" => "상대는 말을 아낀다. 지금은 더 구체적인 단서가 필요하다.".to_string(),
        "REST_OK" => "잠시 숨을 고르자 식어가던 감각이 조금 되살아난다.".to_string(),
        "TORCH_LIT" => "횃불 끝에서 불씨가 살아나며 주변의 어둠을 밀어낸다.".to_string(),
        _ if engine_result.success => "상황은 움직였지만 아직 모든 퍼즐이 맞춰진 것은 아니다.".to_string(),
        _ => "시도는 헛돌았다. 다른 접근이 필요하다.".to_string(),
    };

    (narrative, choices_for_state(state))
}

pub async fn render_turn_with_gemini(
    state: &GameState,
    engine_result: &EngineResult,
    content: &ContentBundle,
    config: Option<&GeminiConfig>,
) -> NarrativeTurn {
    let fallback = render_turn(state, engine_result, content);
    let Some(config) = config else {
        return fallback_turn(fallback);
    };

    let prompt = format!(
        "너는 텍스트 기반 인터랙티브 소설 게임의 narrative generator다.\n\
게임의 진실은 state와 engine_result뿐이다.\n\
상태를 변경하지 말고, 아래 정보를 바탕으로 JSON으로만 응답하라.\n\
JSON 형식: {{\"narrative\":\"...\",\"choices\":[\"...\",\"...\"]}}\n\
선택지는 2개 이상 4개 이하.\n\
\n\
현재 상태:\n\
- location: {}\n\
- quest_stage: {}\n\
- hp: {}\n\
- gold: {}\n\
- player_flags: {:?}\n\
\n\
엔진 결과:\n\
- success: {}\n\
- message_code: {}\n\
- details: {:?}\n\
- ending_reached: {:?}\n\
\n\
톤: dark fantasy mystery, concise Korean prose.",
        state.player.location_id,
        state.quests.murder_case.stage,
        state.player.hp,
        state.player.gold,
        state.player.flags,
        engine_result.success,
        engine_result.message_code,
        engine_result.details,
        engine_result.ending_reached,
    );

    generate_json_narrative(config, prompt, fallback, "turn_narrative").await
}

pub fn choices_for_state(state: &GameState) -> Vec<String> {
    match state.player.location_id.as_str() {
        "village_square" => vec![
            "주변을 조사한다".to_string(),
            "창고로 이동한다".to_string(),
            "아리아와 대화한다".to_string(),
        ],
        "village_warehouse" => vec![
            "주변을 조사한다".to_string(),
            "아리아와 대화한다".to_string(),
            "광장으로 이동한다".to_string(),
        ],
        "dark_alley" => vec![
            "주변을 조사한다".to_string(),
            "여관으로 이동한다".to_string(),
            "도망친다".to_string(),
        ],
        "crooked_tavern" => vec![
            "아리아와 대화한다".to_string(),
            "주변을 조사한다".to_string(),
            "광장으로 이동한다".to_string(),
        ],
        _ => vec![
            "주변을 조사한다".to_string(),
            "광장으로 이동한다".to_string(),
        ],
    }
}

async fn generate_json_narrative(
    config: &GeminiConfig,
    prompt: String,
    fallback: (String, Vec<String>),
    kind: &str,
) -> NarrativeTurn {
    let fallback_turn = fallback_turn(fallback);
    debug_log(
        "gemini_narrative_request",
        &[
            ("kind", kind.to_string()),
            ("model", normalize_model(&config.model)),
            ("prompt_chars", prompt.chars().count().to_string()),
        ],
    );
    match request_gemini(config, prompt).await {
        Ok(parsed) if !parsed.narrative.trim().is_empty() && parsed.choices.len() >= 2 => {
            let mut choices = parsed.choices;
            choices.truncate(4);
            NarrativeTurn {
                narrative: parsed.narrative,
                choices,
                source: NarrativeSource::Gemini,
            }
        }
        Ok(_) => fallback_turn,
        Err(error) => {
            debug_log(
                "gemini_narrative_fallback",
                &[
                    ("kind", kind.to_string()),
                    ("reason", error),
                    ("model", normalize_model(&config.model)),
                ],
            );
            fallback_turn
        }
    }
}

async fn request_gemini(config: &GeminiConfig, prompt: String) -> Result<NarrativeJson, String> {
    let url = format!(
        "https://generativelanguage.googleapis.com/v1beta/{}:generateContent",
        normalize_model(&config.model)
    );
    let payload = serde_json::to_string(&GenerateContentRequest {
        contents: vec![PromptContent {
            parts: vec![PromptPart { text: prompt }],
        }],
    })
    .map_err(|error| format!("gemini payload serialize failed: {}", error))?;
    let output = Command::new("curl")
        .arg("-sS")
        .arg("-X")
        .arg("POST")
        .arg(url)
        .arg("-H")
        .arg(format!("x-goog-api-key: {}", config.api_key))
        .arg("-H")
        .arg("Content-Type: application/json")
        .arg("-d")
        .arg(payload)
        .output()
        .map_err(|error| format!("gemini curl spawn failed: {}", error))?;

    if !output.status.success() {
        return Err(format!(
            "gemini curl failed: {}",
            String::from_utf8_lossy(&output.stderr)
        ));
    }

    let body: GeminiResponse = serde_json::from_slice(&output.stdout)
        .map_err(|error| format!("gemini response parse failed: {}", error))?;
    let text = body
        .candidates
        .and_then(|mut candidates| candidates.drain(..).next())
        .and_then(|candidate| candidate.content)
        .and_then(|content| content.parts)
        .map(|parts| {
            parts
                .into_iter()
                .filter_map(|part| part.text)
                .collect::<Vec<_>>()
                .join("")
        })
        .ok_or_else(|| "gemini response missing text".to_string())?;
    parse_narrative_json(&text)
}

fn parse_narrative_json(raw: &str) -> Result<NarrativeJson, String> {
    let trimmed = raw.trim();
    if let Ok(parsed) = serde_json::from_str::<NarrativeJson>(trimmed) {
        return Ok(parsed);
    }

    let start = trimmed
        .find('{')
        .ok_or_else(|| "no json object start".to_string())?;
    let end = trimmed
        .rfind('}')
        .ok_or_else(|| "no json object end".to_string())?;
    serde_json::from_str(&trimmed[start..=end]).map_err(|error| error.to_string())
}

fn normalize_model(model: &str) -> String {
    let model = model.trim();
    if model.is_empty() {
        DEFAULT_GEMINI_MODEL.to_string()
    } else if model.starts_with("models/") {
        model.to_string()
    } else {
        format!("models/{}", model)
    }
}

fn fallback_turn(fallback: (String, Vec<String>)) -> NarrativeTurn {
    NarrativeTurn {
        narrative: fallback.0,
        choices: fallback.1,
        source: NarrativeSource::Fallback,
    }
}
