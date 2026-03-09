use content::ContentBundle;
use domain::{EngineResult, GameState};

pub fn opening_narrative(state: &GameState, content: &ContentBundle) -> (String, Vec<String>) {
    let location = content.location_name(&state.player.location_id);
    let narrative = format!(
        "{}. 축축한 밤공기 속에서 마을 광장은 숨을 죽인 채 가라앉아 있다. 먼 곳에서 누군가 서둘러 문을 닫는 소리가 들린다.",
        location
    );
    let choices = choices_for_state(state);
    (narrative, choices)
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
        _ => vec!["주변을 조사한다".to_string(), "광장으로 이동한다".to_string()],
    }
}
