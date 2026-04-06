# AGENTS.md

## 프로젝트 개요

OpenNovel은 AI 기반 텍스트 인터랙티브 소설 게임이다.  
현재 `main`의 공식 런타임은 Python `agent` 서버이며, 플레이어 입력은 intent 해석, 상태 제안, deterministic validation, narrative 렌더링 단계를 거쳐 처리된다.

핵심 흐름:

```text
Player Input
  -> IntenderAgent
  -> StoryStateManagerAgent
  -> RuleValidator
  -> NarratorAgent
  -> Narrative / Choices / Snapshot
  -> Session Update
  -> UI
```

## 현재 아키텍처

주요 문서:
- Backend: [docs/backend/BACKEND.md](./docs/backend/BACKEND.md)
- Frontend: [docs/frontend/FRONTEND.md](./docs/frontend/FRONTEND.md)

현재 구현 요소:
- Python `agent` 기반 단일 서버
- startup 시 `StorySetupAgent`가 생성하거나 fallback으로 채우는 3개의 story setup preset
- `GameSessionService` 중심의 세션 오케스트레이션
- `WorldBuilderAgent` 기반 world blueprint 생성
- `RuleValidator` 기반 theme/objective/style 판정
- **Phase 1**: StateManager victory condition awareness, ending narrative fixes, prompt optimization (22% token reduction)
- **Phase 2-A**: Diegetic feedback - 플레이어 스타일이 narrative 톤과 NPC 반응에 반영
- **Phase 2-B**: NPC autonomous actions - NPC가 조건 기반으로 자율 행동 (affinity, turn, trigger)
- direct compatibility endpoint용 `IntenderAgent`, `NarratorAgent`
- Chroma 기반 retrieval
- in-memory 세션 저장
- 정적 frontend 서빙
- 채팅 UI + 턴 그래프 + hover debug 로그 UI

아직 미구현:
- SQLite 기반 영속 저장소
- memory summary 파이프라인
- React/TypeScript frontend
- streaming 응답

## 게임 상태의 진실

현재 진실은 세션 히스토리와 최신 `GameState` snapshot이다.

서버가 관리하는 세션 단위 데이터:
- `session_id`
- `turn`
- `history`
- `state`
- `current choices`
- `story_setup`
- `world_blueprint`
- `discovery_log`

LLM 계층은 다음을 제안하거나 표현한다.
- intent action
- scene summary / state patch proposal
- narrative
- surfaced choices

상태 전이의 진실은 `RuleValidator`가 확정한다.

## 현재 상태 구조

`main` 기준 예시:

```json
{
  "meta": {
    "turn": 0,
    "seed": 12345
  },
  "player": {
    "hp": 100,
    "gold": 15,
    "location_id": "ruins_entrance",
    "inventory": {
      "torch": 1
    },
    "flags": [],
    "style_scores": {
      "cautious": 5,
      "curious": 3
    },
    "style_tags": ["cautious", "curious"]
  },
  "world": {
    "time": "night",
    "global_flags": ["sunken_ruins_open"],
    "alert_by_region": {
      "ruins": 6
    },
    "theme_id": "sunken_ruins",
    "theme_rules": ["..."]
  },
  "quests": {
    "story_arc": {
      "stage": 0
    }
  },
  "objective": {
    "status": "in_progress",
    "victory_path": null
  },
  "relations": {
    "npc_affinity": {
      "caretaker": 5
    }
  }
}
```

주의:
- 현재 `main`은 여전히 compatibility state에 `sunken_ruins`, `caretaker`, `ruins_entrance` 같은 값이 남아 있다.
- 이 값은 프론트와 direct endpoint 호환을 위해 사용된다.

## 턴 처리 흐름

현재 `/game/*` 경로:

```text
Player Input
  -> GameSessionService
  -> IntenderAgent.handle()
  -> StoryStateManagerAgent.propose()
  -> RuleValidator.validate_transition()
  -> NarratorAgent.render_turn()
  -> TurnResult(narrative, choices, state, engineResult)
  -> Session Update
```

세션 시작:

```text
Startup
  -> StorySetupAgent
  -> preset 3개 생성 또는 fallback

POST /game/start
  -> story setup 선택
  -> WorldBuilderAgent.build()
  -> theme pack 적용
  -> RuleValidator.initialize_world()
  -> NarratorAgent.render_opening()
  -> opening narrative / state 생성
```

## 프롬프트 구조

현재 프롬프트는 대략 다음 블록으로 구성된다.

```text
System Rules
World / Tone Guide
Current State Summary
Story Context
Output Format
```

### State Proposal Prompt

역할:
- 현재 state와 intent를 바탕으로 다음 장면 요약과 상태 패치 초안을 제안
- 최종 판정은 하지 않음

### Intent Parsing Prompt

`/intent/validate` direct endpoint용 compatibility prompt다.

예:
- `주변을 살펴본다` -> `INVESTIGATE`
- `관리인과 대화한다` -> `TALK`
- `회랑으로 이동한다` -> `MOVE`

### Narrative Prompt

`/narrative/opening`, `/narrative/turn` direct endpoint용 compatibility prompt다.

역할:
- state + engine result를 바탕으로 장면 서술
- allowed choices 기반 choice 구성

## 현재 API

- `GET /`
- `GET /health`
- `GET /story-setups`
- `POST /game/start`
- `POST /game/action`
- `GET /game/state`
- `GET /debug/turn-log`
- `POST /intent/validate`
- `POST /narrative/opening`
- `POST /narrative/turn`

## 현재 UI

기본 상호작용은 채팅 기반이다.

```text
Story Log
  -> Choice Buttons
  -> Player Input
```

보조 UI:
- turn graph
- turn detail panel
- debug hover panel

## 핵심 설계 원칙

1. 현재 `main`에서는 `GameSessionService`가 턴 흐름을 오케스트레이션하고, `RuleValidator`가 상태의 진실을 소유한다.
2. 세션 히스토리와 최신 snapshot이 진실이다.
3. direct compatibility endpoint는 `IntenderAgent`, `NarratorAgent`로 유지한다.
4. LLM 출력은 구조화 JSON을 우선한다.
5. 실패 시 template / heuristic fallback이 존재한다.

## Phase 2: Diegetic Feedback & NPC Autonomy

### Phase 2-A: Diegetic Feedback for Player Style

**목표**: 플레이어의 누적 스타일(`style_tags`)을 서사에 반영하여 행동 패턴이 narrative 톤과 NPC 반응에 영향을 줌

**구현 내용**:
- `style_scores`: 액션별 점수 누적 (cautious +1, diplomatic +2, curious +2 등)
- `style_tags`: 점수 ≥3인 스타일만 태그로 저장
- Narrator 프롬프트에 **Player Style 섹션** 추가:
  - `accumulated_tags`를 명시적으로 전달
  - theme별 `style_narrative_hints`를 주입
- NPC Affinity + Style 조합 선택지:
  - affinity ≥7 + diplomatic → "비밀 정보 요청" 특별 선택지
  - affinity ≥7 + curious → "숨겨진 장소 문의" 특별 선택지

**변경 파일**:
- `agent/app/prompts/narrative_builder.py`: `_player_style_section()`, `_theme_style_hints_section()`
- `agent/app/services/validator.py`: affinity + style 조합 로직
- `content/theme_packs.json`: 모든 theme에 `style_narrative_hints` 추가

### Phase 2-B: NPC Autonomous Actions

**목표**: NPC가 플레이어 행동과 무관하게 자율적으로 행동/반응하는 시스템

**구현 내용**:
- `NpcBehavior` 모델:
  - `trigger`: "turn_start", "player_enters", "affinity_threshold"
  - `condition`: "affinity >= 7", "turn >= 3", "affinity < 5"
  - `action`: "greet_with_warning", "reveal_secret", "block_path", "offer_item", "express_distrust"
  - `cooldown_turns`: 재발동 방지
  - `message`: Narrator가 참고할 힌트

- `WorldNpc` 확장:
  - `personality`: "cautious_helper", "suspicious", "greedy", "protective"
  - `behaviors`: NpcBehavior 리스트

- `RuleValidator._check_npc_events()`:
  - 현재 위치 NPC의 behaviors 체크
  - condition 평가 (affinity, turn)
  - cooldown 관리 (state flags)
  - `engine_result.details`에 `npc_event:{npc_id}:{action}` 추가

- Narrator 프롬프트에 **NPC Events 섹션** 추가:
  - NPC 자율 행동을 서술에 자연스럽게 포함
  - "플레이어의 행동 결과와 별개로 일어난 것처럼 묘사"

**콘텐츠**:
- 7 themes × 3 NPCs × 2 behaviors = 42개 behaviors
- 예: cursed_cathedral의 "문지기 사제"
  - turn==0일 때 "greet_with_warning"
  - affinity>=7일 때 "reveal_secret_path" (쿨다운 99턴)

**변경 파일**:
- `agent/app/schemas/multi_agent.py`: `NpcBehavior`, `NpcEvent`, `WorldNpc` 확장
- `agent/app/services/validator.py`: `_check_npc_events()`, condition 평가
- `agent/app/prompts/narrative_builder.py`: `_npc_event_section()`
- `agent/app/agents/world_builder.py`: behaviors 보존
- `content/theme_packs.json`: 42 behaviors 데이터
