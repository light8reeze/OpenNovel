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

- [agent/app/runtime.py](/Users/light8reeze/Documents/Projects/OpenNovel/agent/app/runtime.py)
  - runtime 조립
  - story setup preset 생성
  - Chroma / retrieval 초기화
- [agent/app/game/service.py](/Users/light8reeze/Documents/Projects/OpenNovel/agent/app/game/service.py)
  - 세션 시작, 턴 진행, 상태 조회
  - in-memory 세션 저장
- [agent/app/services/validator.py](/Users/light8reeze/Documents/Projects/OpenNovel/agent/app/services/validator.py)
  - theme rule 적용
  - objective / victory 판정
  - cumulative style scoring
- [agent/app/agents/story_setup.py](/Users/light8reeze/Documents/Projects/OpenNovel/agent/app/agents/story_setup.py)
  - startup preset 생성
- [agent/app/agents/intender.py](/Users/light8reeze/Documents/Projects/OpenNovel/agent/app/agents/intender.py)
  - 플레이어 입력을 action으로 정규화
- [agent/app/agents/narrator.py](/Users/light8reeze/Documents/Projects/OpenNovel/agent/app/agents/narrator.py)
  - validator 결과를 바탕으로 narrative / choices 렌더링
- [agent/app/agents/state_manager.py](/Users/light8reeze/Documents/Projects/OpenNovel/agent/app/agents/state_manager.py)
  - 상태 패치와 scene summary 초안 제안
- [agent/app/services/file_logger.py](/Users/light8reeze/Documents/Projects/OpenNovel/agent/app/services/file_logger.py)
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
    "flags": []
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
- `engineResult`도 실제 deterministic engine 결과가 아니라 compatibility metadata로 사용된다.

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

## 8. Current Limitations

아직 없는 것:
- SQLite / persistent DB
- streaming response
- memory summary pipeline
- React/TypeScript frontend
- rule validator 중심의 multi-agent runtime

즉 `main`의 현재 backend는 `StoryAgent` 중심 single-runtime 구조다.
