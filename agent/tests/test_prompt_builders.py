from app.prompts.intent_builder import build_intent_prompts
from app.game.models import GameState, MetaState, ObjectiveState, PlayerState, QuestProgress, QuestState, RelationsState, WorldState
from app.prompts.narrative_builder import build_narrative_prompts
from app.prompts.state_manager import build_state_manager_prompts
from app.retrieval.schemas import RetrievalContext, RetrievalHit
from app.schemas.common import Action, ActionType, EngineResult, SceneContext, StateSummary
from app.schemas.intent import IntentValidationRequest
from app.schemas.multi_agent import StoryTransitionProposalRequest, WorldBlueprint, WorldLocation, WorldNpc
from app.schemas.narrative import NarrativeRequest


def test_narrative_prompt_uses_story_arc_and_world_context() -> None:
    request = NarrativeRequest(
        state_summary=StateSummary(
            turn=3,
            location_id="fog_alley",
            hp=52,
            gold=15,
            story_arc_stage=2,
            player_flags=["found_glove"],
        ),
        scene_context=SceneContext(
            location_name="안개 골목",
            npcs_in_scene=["항구 경비"],
            visible_targets=["밀수 창고", "종탑 광장"],
        ),
        engine_result=EngineResult(
            success=True,
            message_code="INVESTIGATE_PROGRESS",
            location_changed=False,
            quest_stage_changed=True,
            ending_reached=None,
            details=["found_smuggling_mark"],
        ),
        progress_kind="investigate",
        allowed_choices=["주변을 조사한다", "항구 경비와 대화한다", "밀수 창고로 이동한다"],
        world_title="잿빛 항구 도시",
        world_summary="비와 안개가 뒤섞인 항구 도시에서 실종 사건과 검은 거래가 얽혀 있다.",
        world_tone="음울하고 조용한 추적극",
        opening_hook="버려진 부두에서 피 묻은 장갑이 발견된다.",
    )
    retrieval = RetrievalContext(
        used=True,
        query="fog alley",
        hits=[RetrievalHit(id="narrator-city", text="항구 도시는 젖은 돌바닥과 낮은 목소리의 긴장으로 유지된다.", metadata={})],
    )

    system_prompt, user_prompt = build_narrative_prompts("turn", request, retrieval)

    assert "validator가 확정한 결과" in system_prompt
    assert "잿빛 항구 도시" in user_prompt
    assert "progress_kind: investigate" in user_prompt
    assert "story_arc_stage: 2" in user_prompt
    assert "안개 골목" in user_prompt
    assert "밀수 창고" in user_prompt
    assert "세계관에 없는 던전 상투어를 임의로 끌어오지 마라." in system_prompt


def test_opening_narrative_prompt_uses_opening_hook() -> None:
    request = NarrativeRequest(
        state_summary=StateSummary(
            turn=0,
            location_id="harbor_dock",
            hp=100,
            gold=15,
            story_arc_stage=0,
            player_flags=[],
        ),
        scene_context=SceneContext(
            location_name="젖은 부두",
            npcs_in_scene=["항구 경비"],
            visible_targets=["안개 골목", "항구 경비", "횃불"],
        ),
        progress_kind="opening",
        allowed_choices=["주변을 조사한다", "항구 경비와 대화한다", "안개 골목으로 이동한다"],
        world_title="잿빛 항구 도시",
        world_summary="비와 안개가 뒤섞인 항구 도시에서 실종 사건과 검은 거래가 얽혀 있다.",
        world_tone="음울하고 조용한 추적극",
        opening_hook="새벽 직전, 젖은 부두 끝에 버려진 장갑이 놓여 있다.",
    )

    _, user_prompt = build_narrative_prompts("opening", request, RetrievalContext())

    assert "opening_hook: 새벽 직전, 젖은 부두 끝에 버려진 장갑이 놓여 있다." in user_prompt
    assert "story_arc_stage: 0" in user_prompt
    assert "젖은 부두" in user_prompt


def test_narrative_prompt_removes_duplicate_scene_fields() -> None:
    request = NarrativeRequest(
        state_summary=StateSummary(
            turn=4,
            location_id="fog_alley",
            hp=48,
            gold=22,
            story_arc_stage=3,
            player_flags=["found_glove"],
            style_tags=["grim"],
            objective_status="in_progress",
            victory_path="recovered",
        ),
        scene_context=SceneContext(
            location_name="안개 골목",
            npcs_in_scene=["항구 경비"],
            visible_targets=["밀수 창고"],
        ),
        allowed_choices=["주변을 조사한다", "항구 경비와 대화한다"],
        world_title="잿빛 항구 도시",
        world_summary="비와 안개가 뒤섞인 항구 도시에서 실종 사건과 검은 거래가 얽혀 있다.",
        world_tone="음울하고 조용한 추적극",
        player_goal="실종 사건의 단서를 찾는다.",
    )

    _, user_prompt = build_narrative_prompts("turn", request, RetrievalContext())

    assert "player_goal: 실종 사건의 단서를 찾는다." in user_prompt
    assert "style_tags:" not in user_prompt
    assert "objective_status:" not in user_prompt
    assert "victory_path:" not in user_prompt
    assert "current_goal:" not in user_prompt


def test_state_manager_prompt_uses_lightweight_world_blueprint_and_shorter_logs() -> None:
    request = StoryTransitionProposalRequest(
        state=GameState(
            meta=MetaState(turn=7, seed=12345),
            player=PlayerState(hp=100, gold=15, location_id="fog_alley"),
            world=WorldState(time="night", theme_id="harbor_mystery"),
            quests=QuestState(story_arc=QuestProgress(stage=2)),
            objective=ObjectiveState(),
            relations=RelationsState(),
        ),
        world_blueprint=WorldBlueprint(
            id="harbor_city",
            title="잿빛 항구 도시",
            world_summary="긴 설명은 프롬프트에서 제외한다.",
            tone="음울하고 조용한 추적극",
            core_conflict="실종 사건과 검은 거래의 연결고리를 밝혀야 한다.",
            player_goal="실종 사건의 단서를 찾는다.",
            opening_hook="새벽 부두에서 이상한 흔적이 발견된다.",
            locations=[
                WorldLocation(
                    id="fog_alley",
                    label="안개 골목",
                    connections=["smuggler_warehouse", "bell_tower"],
                    investigation_hooks=["젖은 발자국", "긁힌 벽면"],
                ),
                WorldLocation(
                    id="smuggler_warehouse",
                    label="밀수 창고",
                    connections=["fog_alley"],
                ),
            ],
            npcs=[
                WorldNpc(
                    id="harbor_guard",
                    label="항구 경비",
                    home_location_id="fog_alley",
                    role="guard",
                    interaction_hint="주저하지만 알고 있다.",
                )
            ],
            hidden_truths=["이 값은 제외되어야 한다."],
            theme_id="harbor_mystery",
            theme_rules=["이 값도 제외되어야 한다."],
        ),
        discovery_log=[f"fact-{index}" for index in range(8)],
        history=[],
        intent=Action(
            action_type=ActionType.INVESTIGATE,
            target="fog_alley",
            raw_input="주변을 살펴본다",
        ),
    )

    _, user_prompt = build_state_manager_prompts(request)

    assert '"discovery_log": [' in user_prompt
    assert '"fact-3"' in user_prompt
    assert '"fact-7"' in user_prompt
    assert '"fact-2"' not in user_prompt
    assert '"recent_history"' not in user_prompt
    assert '"world_summary"' not in user_prompt
    assert '"player_goal"' not in user_prompt
    assert '"opening_hook"' not in user_prompt
    assert '"hidden_truths"' not in user_prompt
    assert '"current_location_hooks": [' in user_prompt
    assert '"젖은 발자국"' in user_prompt
    assert '"항구 경비"' in user_prompt


def test_intent_prompt_uses_story_arc_stage_and_target_labels() -> None:
    request = IntentValidationRequest(
        player_input="항구 경비에게 다시 묻는다",
        allowed_actions=[ActionType.TALK, ActionType.INVESTIGATE],
        state_summary=StateSummary(
            turn=1,
            location_id="harbor_dock",
            hp=100,
            gold=15,
            story_arc_stage=0,
            player_flags=[],
        ),
        scene_context=SceneContext(
            location_name="젖은 부두",
            npcs_in_scene=["항구 경비"],
            visible_targets=["안개 골목", "항구 경비", "횃불"],
        ),
    )
    retrieval = RetrievalContext(
        used=True,
        query="harbor guard",
        hits=[RetrievalHit(id="intent-guard", text="항구 경비는 정보와 경고를 동시에 주는 인물이다.", metadata={})],
    )

    system_prompt, user_prompt = build_intent_prompts(request, retrieval)

    assert "story_arc_stage: 0" in user_prompt
    assert "안개 골목, 항구 경비, 횃불" in user_prompt
    assert "target은 visible_targets 또는 npcs_in_scene에 있는 표현만 사용한다." in user_prompt
    assert "validator가 수행한다" in user_prompt
