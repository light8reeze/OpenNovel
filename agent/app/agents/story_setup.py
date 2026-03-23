from __future__ import annotations

import json
import re

from app.config import RoleModelSettings
from app.schemas.story_setup import StorySetup, StorySetupGenerationResponse
from app.services.file_logger import log_llm_error
from app.services.llm_client import BaseLlmClient, LlmError


FALLBACK_STORY_SETUPS: list[StorySetup] = [
    StorySetup(
        id="sunken_ruins",
        title="가라앉은 폐허",
        world_summary="오래전 봉인된 지하 유적이 밤의 안개 속에서 다시 모습을 드러냈다. 무너진 석문, 젖은 돌계단, 희미한 룬의 잔광이 탐험가를 아래로 이끈다.",
        tone="고요하지만 위협적인 다크 판타지 탐험",
        player_goal="폐허의 깊은 곳까지 내려가 유적의 비밀과 잠든 유물을 손에 넣는다.",
        opening_hook="입구의 석문이 조금 열리며 오래 잠든 공기와 함께 희미한 빛이 새어 나온다.",
        style_guardrails=["과장된 영웅담보다 긴장과 탐색을 우선한다", "짧고 선명한 감각 묘사를 사용한다"],
    ),
    StorySetup(
        id="city_investigation",
        title="잿빛 항구 도시",
        world_summary="비와 안개가 뒤섞인 항구 도시의 뒷골목에서는 밀수와 실종 소문이 엉켜 있다. 가스등 아래에서 사람들은 진실보다 살아남는 쪽을 먼저 택한다.",
        tone="음울하고 조용한 추적극",
        player_goal="도시의 어두운 골목을 따라가 사라진 인물과 숨겨진 거래의 실체를 밝혀낸다.",
        opening_hook="새벽 직전, 젖은 부두 끝에 버려진 짐짝 사이로 누군가의 피 묻은 장갑이 발견된다.",
        style_guardrails=["현대 수사극보다 느린 추적과 의심을 강조한다", "모든 인물은 약간의 비밀을 가진 듯 말한다"],
    ),
    StorySetup(
        id="frontier_survival",
        title="황야의 경계지",
        world_summary="문명과 황야가 맞닿은 변경에서는 길 하나를 벗어나는 순간 생존이 문제로 바뀐다. 모래폭풍, 버려진 초소, 낡은 신호불이 유일한 이정표다.",
        tone="거칠고 절제된 생존 모험",
        player_goal="메마른 변경을 건너 목적지까지 살아서 도달하고, 길 위에 남겨진 오래된 신호의 의미를 파악한다.",
        opening_hook="해가 저물 무렵, 마지막 초소의 망루에서 오래 꺼져 있던 신호불이 홀로 다시 켜진다.",
        style_guardrails=["과도한 낭만화 없이 생존 압박을 유지한다", "풍경은 넓게, 감정은 절제해서 묘사한다"],
    ),
]


class StorySetupAgent:
    def __init__(self, settings: RoleModelSettings, llm_client: BaseLlmClient):
        self.settings = settings
        self.llm_client = llm_client

    def generate(self) -> list[StorySetup]:
        system_prompt = "\n".join(
            [
                "You design session-start presets for a Korean interactive fiction game.",
                "Return valid JSON only.",
                "Generate exactly three distinct presets.",
                "Each preset must be immediately playable as an opening scenario.",
                "Avoid modern meta jokes, internet slang, and generic fantasy filler.",
                "Keep all text in Korean.",
                "Each preset must include id, title, world_summary, tone, player_goal, opening_hook, style_guardrails.",
                "IDs must be short lowercase snake_case strings.",
            ]
        )
        user_prompt = json.dumps(
            {
                "request": "Generate three distinct session-start presets.",
                "shape": {
                    "presets": [
                        {
                            "id": "snake_case",
                            "title": "string",
                            "world_summary": "string",
                            "tone": "string",
                            "player_goal": "string",
                            "opening_hook": "string",
                            "style_guardrails": ["string", "string"],
                        }
                    ]
                },
                "requirements": [
                    "The three presets must feel noticeably different in world, tone, and player goal.",
                    "All presets must support immediate opening scene generation.",
                    "Prefer dark fantasy, mystery, or frontier adventure tones over comedy.",
                    "Each style_guardrails list should contain 2 concise items.",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        result = self.llm_client.generate_json(
            schema_name="story_setup_generation",
            schema_model=StorySetupGenerationResponse,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        response = StorySetupGenerationResponse.model_validate(result.payload)
        presets = [self._normalize_setup(setup) for setup in response.presets[:3]]
        if len(presets) != 3:
            raise LlmError(f"expected 3 presets, got {len(presets)}")
        return presets

    def generate_with_fallback(self) -> tuple[list[StorySetup], str]:
        try:
            return self.generate(), "llm"
        except Exception as error:
            log_llm_error(
                role="story_setup_agent",
                provider=self.settings.provider,
                model=self.settings.model,
                stage="fallback",
                error=str(error),
                extra={"fallback_count": len(FALLBACK_STORY_SETUPS)},
            )
            return list(FALLBACK_STORY_SETUPS), "fallback"

    def _normalize_setup(self, setup: StorySetup) -> StorySetup:
        setup_id = _slugify_setup_id(setup.id or setup.title)
        guardrails = [item.strip() for item in setup.style_guardrails if item.strip()][:3]
        if len(guardrails) < 2:
            guardrails = ["설정의 일관성을 유지한다", "과장된 장르 혼합을 피한다"]
        return StorySetup(
            id=setup_id,
            title=setup.title.strip(),
            world_summary=setup.world_summary.strip(),
            tone=setup.tone.strip(),
            player_goal=setup.player_goal.strip(),
            opening_hook=setup.opening_hook.strip(),
            style_guardrails=guardrails,
        )


def _slugify_setup_id(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return normalized or "story_setup"
