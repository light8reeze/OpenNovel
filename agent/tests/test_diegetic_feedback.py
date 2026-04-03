from __future__ import annotations

from app.game.models import ContentBundle, RelationsState, initial_state
from app.prompts.narrative_builder import build_narrative_prompts
from app.retrieval.schemas import RetrievalContext
from app.schemas.common import SceneContext, StateSummary
from app.schemas.multi_agent import WorldBlueprint, WorldLocation, WorldNpc
from app.schemas.narrative import NarrativeRequest
from app.services.validator import RuleValidator


def _narrative_request(*, style_tags: list[str], theme_id: str | None) -> NarrativeRequest:
    return NarrativeRequest(
        state_summary=StateSummary(
            turn=4,
            location_id="ruins_entrance",
            hp=84,
            gold=15,
            story_arc_stage=2,
            player_flags=["visited:ruins_entrance"],
            style_tags=style_tags,
            theme_id=theme_id,
        ),
        scene_context=SceneContext(
            location_name="침수 유적 입구",
            npcs_in_scene=["관리인"],
            visible_targets=["침수 회랑", "관리인"],
        ),
        allowed_choices=["관리인과 대화한다", "침수 회랑으로 이동한다"],
        world_title="깊은 물의 성소",
        world_summary="물에 잠긴 유적에서 오래된 맹세가 다시 떠오른다.",
        world_tone="축축하고 불길한 탐사",
        player_goal="유적의 핵심으로 들어갈 길을 연다.",
    )


def _validator_with_content() -> RuleValidator:
    content = ContentBundle.model_validate(
        {
            "locations": [],
            "npcs": [],
            "story_arc": {"id": "story", "title": "story", "stages": [], "endings": []},
            "theme_packs": [
                {
                    "id": "sunken_ruins",
                    "title_prefix": "침수 유적",
                    "summary_prefix": "물 아래서 봉인이 흔들린다.",
                    "tone": "축축하고 음산한 탐사",
                    "opening_hook": "봉인이 흔들린다.",
                    "style_narrative_hints": {
                        "diplomatic": "관리인과의 대화는 협상처럼 흐르게 한다.",
                    },
                }
            ],
        }
    )
    return RuleValidator(content)


def _blueprint() -> WorldBlueprint:
    return WorldBlueprint(
        id="sunken_ruins_world",
        title="침수 유적",
        world_summary="젖은 돌 아래 봉인이 흔들린다.",
        tone="축축한 긴장",
        core_conflict="깊은 곳의 봉인을 다룬다.",
        player_goal="핵심 성소에 도달한다.",
        opening_hook="젖은 계단 아래서 물소리가 울린다.",
        starting_location_id="ruins_entrance",
        theme_id="sunken_ruins",
        locations=[
            WorldLocation(id="ruins_entrance", label="침수 유적 입구", connections=["flooded_hall"], danger_level=1),
            WorldLocation(id="flooded_hall", label="침수 회랑", connections=["ruins_entrance"], danger_level=2),
        ],
        npcs=[
            WorldNpc(
                id="caretaker",
                label="관리인",
                home_location_id="ruins_entrance",
                role="caretaker",
                interaction_hint="봉인의 규칙을 안다.",
            )
        ],
    )


def test_narrator_prompt_includes_player_style_section_when_tags_exist() -> None:
    _, user_prompt = build_narrative_prompts(
        "turn",
        _narrative_request(style_tags=["curious", "diplomatic"], theme_id="sunken_ruins"),
        RetrievalContext(),
    )

    assert "Player Style:" in user_prompt
    assert "accumulated_tags: curious, diplomatic" in user_prompt


def test_narrator_prompt_omits_player_style_section_without_tags() -> None:
    _, user_prompt = build_narrative_prompts(
        "turn",
        _narrative_request(style_tags=[], theme_id="sunken_ruins"),
        RetrievalContext(),
    )

    assert "Player Style:" not in user_prompt
    assert "Theme Style Hints:" not in user_prompt


def test_narrator_prompt_injects_theme_style_hints_for_matching_tags() -> None:
    _, user_prompt = build_narrative_prompts(
        "turn",
        _narrative_request(style_tags=["diplomatic", "cautious"], theme_id="sunken_ruins"),
        RetrievalContext(),
    )

    assert "Theme Style Hints:" in user_prompt
    assert "- diplomatic:" in user_prompt
    assert "- cautious:" in user_prompt


def test_generate_choices_adds_diplomatic_special_choice_for_high_affinity() -> None:
    validator = _validator_with_content()
    blueprint = _blueprint()
    state = initial_state(seed=7)
    state.player.location_id = "ruins_entrance"
    state.player.style_tags = ["diplomatic"]
    state.relations = RelationsState(npc_affinity={"caretaker": 8})
    state.world.theme_id = "sunken_ruins"

    choices = validator._choices_for_state(state, blueprint)

    assert choices[0] == "침수 유적 입구 주변을 다시 살피며 놓친 흔적이 없는지 확인한다"
    assert choices[1] == "관리인과 이해관계를 조율하며 협조를 끌어낸다"


def test_generate_choices_skips_special_choice_when_affinity_is_low() -> None:
    validator = _validator_with_content()
    blueprint = _blueprint()
    state = initial_state(seed=7)
    state.player.location_id = "ruins_entrance"
    state.player.style_tags = ["diplomatic"]
    state.relations = RelationsState(npc_affinity={"caretaker": 6})
    state.world.theme_id = "sunken_ruins"

    choices = validator._choices_for_state(state, blueprint)

    assert "관리인과 이해관계를 조율하며 협조를 끌어낸다" not in choices
