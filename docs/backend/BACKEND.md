OpenNovel Backend Guide

## 1. Overview

현재 `main`의 공식 backend는 Python `agent` 서비스다.  
플레이어 입력은 `GameSessionService`를 거쳐 intent 해석, 상태 제안, deterministic rule validation, narrative 렌더링 단계를 순서대로 통과한다.

핵심 흐름:

```text
Player Input
  -> GameSessionService
  -> IntenderAgent
  -> StoryStateManagerAgent
  -> RuleValidator
  -> NarratorAgent
  -> TurnResult
  -> Session Update
  -> JSON Response
```

서버 startup 시에는 `StorySetupAgent`가 세션 시작용 preset 3개를 생성하려 시도하고, 실패하면 fallback preset을 사용한다.

## 2. Runtime Architecture

현재 `agent/app`의 실제 책임:

- [agent/app/runtime.py](../../agent/app/runtime.py)
  - runtime 조립
  - story setup preset 생성
  - Chroma / retrieval 초기화
- [agent/app/game/service.py](../../agent/app/game/service.py)
  - 세션 시작, 턴 진행, 상태 조회
  - in-memory 세션 저장
- [agent/app/services/validator.py](../../agent/app/services/validator.py)
  - theme rule 적용
  - objective / victory 판정
  - cumulative style scoring
- [agent/app/agents/story_setup.py](../../agent/app/agents/story_setup.py)
  - startup preset 생성
- [agent/app/agents/intender.py](../../agent/app/agents/intender.py)
  - 플레이어 입력을 action으로 정규화
- [agent/app/agents/narrator.py](../../agent/app/agents/narrator.py)
  - validator 결과를 바탕으로 narrative / choices 렌더링
- [agent/app/agents/state_manager.py](../../agent/app/agents/state_manager.py)
  - 상태 패치와 scene summary 초안 제안
- [agent/app/services/file_logger.py](../../agent/app/services/file_logger.py)
  - JSONL 로그와 debug turn bundle 집계

추상 구조:

```text
Frontend
  -> FastAPI routes
  -> AgentRuntime
  -> GameSessionService
  -> Intender / State Manager / RuleValidator / Narrator
  -> LLM + deterministic validation
```

## 3. Session Model

현재 세션은 메모리 기반이다.

저장되는 값:
- `session_id`
- `state`
- `history`
- `choices`
- `story_setup`
- per-session runtime agents

영속 저장소는 아직 없다.

## 4. State Model

`main` 기준 compatibility state 예시:

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
- `main`에서는 이 state가 아직 던전 기반 compatibility 의미를 가진다.
- `engineResult`는 이제 validator가 확정한 진행 결과를 요약하는 compatibility 응답이다.

## 5. API

현재 공식 API:

- `GET /`
- `GET /health`
- `GET /story-setups`
- `POST /game/start`
- `POST /game/action`
- `GET /game/state`

개발/호환 API:

- `GET /debug/turn-log`
- `POST /intent/validate`
- `POST /narrative/opening`
- `POST /narrative/turn`

### `GET /story-setups`

startup 시 생성된 preset 3개를 반환한다.

### `POST /game/start`

요청 예시:

```json
{
  "storySetupId": "sunken_ruins",
  "geminiApiKey": "AIza...",
  "geminiModel": "gemini-2.5-flash"
}
```

응답 예시:

```json
{
  "sessionId": "session-...",
  "narrative": "....",
  "choices": ["..."],
  "state": {},
  "storySetupId": "sunken_ruins"
}
```

### `POST /game/action`

입력은 자유 입력과 choice 입력 둘 다 지원한다.

```json
{
  "sessionId": "session-...",
  "inputText": "주변을 조사한다"
}
```

또는

```json
{
  "sessionId": "session-...",
  "choiceText": "회랑으로 이동한다"
}
```

### `GET /game/state`

현재 세션의 최신 compatibility state를 반환한다.

## 6. LLM Layers

현재 역할 분리:

- `StorySetupAgent`
  - startup preset 생성
- `WorldBuilderAgent`
  - preset을 world blueprint로 확장
- `IntenderAgent`
  - 입력을 action으로 정규화
- `StoryStateManagerAgent`
  - 상태 패치 / discovery / scene summary 초안 제안
- `RuleValidator`
  - state truth, theme rules, style scoring, objective/victory 판정
- `NarratorAgent`
  - 검증된 결과를 장면으로 표현

지원 provider:
- `mock`
- `gemini`
- `openai_compatible`

## 7. Retrieval and Logging

Retrieval:
- Chroma 사용
- startup 시 auto-index 가능
- `intender`, `narrator` 두 collection 사용

로그:
- `log/agent/backend-requests.jsonl`
- `log/agent/intent-results.jsonl`
- `log/agent/narrative-results.jsonl`
- `log/agent/game-results.jsonl`
- `log/agent/llm-errors.jsonl`
- `log/combined/run-*.jsonl`

`GET /debug/turn-log`는 이 로그를 묶어서 turn 단위 bundle로 반환한다.

## 8. Phase 2 Features (v1.0.0.0+)

### Phase 2-A: Diegetic Feedback

**구현됨** (`feature/mvp-2nd-expand`)

플레이어의 누적 스타일(`style_tags`)이 narrative 톤과 NPC 반응에 반영됩니다:

- **Player Style Reflection**:
  - `style_scores`: 액션별 점수 누적
  - `style_tags`: 점수 ≥3인 스타일만 태그화
  - Narrator 프롬프트에 Player Style 섹션 추가
  - Theme별 `style_narrative_hints` 제공

- **NPC Affinity + Style 조합**:
  - affinity ≥7 + diplomatic → "비밀 정보 요청" 선택지
  - affinity ≥7 + curious → "숨겨진 장소 문의" 선택지

### Phase 2-B: NPC Autonomous Actions

**구현됨** (`feature/mvp-2nd-expand`)

NPC가 조건 기반으로 자율 행동:

- **NpcBehavior 시스템**:
  - `trigger`: "turn_start", "player_enters", "affinity_threshold"
  - `condition`: "affinity >= 7", "turn >= 3"
  - `action`: 자율 행동 타입
  - `cooldown_turns`: 재발동 방지

- **Validator Integration**:
  - `_check_npc_events()`: 조건 평가 및 이벤트 발생
  - `engine_result.details`에 `npc_event:*` 추가

- **Narrator Integration**:
  - NPC Events 섹션으로 자율 행동 서술 반영

**콘텐츠**: 7 themes × 3 NPCs × 2 behaviors = 42개

## 9. Current Limitations

아직 없는 것:
- SQLite / persistent DB
- streaming response
- memory summary pipeline
- React/TypeScript frontend
- meta world memory (beyond MVP)
- multiple objective types (beyond MVP)

즉 현재 backend는 validator-backed multi-agent runtime + diegetic feedback + NPC autonomy를 가진 Phase 2 MVP 구조다.
