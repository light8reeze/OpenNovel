# AGENTS.md

## 프로젝트 개요

OpenNovel은 AI 기반 텍스트 인터랙티브 소설 게임이다.  
현재 `main`의 공식 런타임은 Python `agent` 서버이며, 플레이어 입력과 최신 상태 snapshot을 바탕으로 `StoryAgent`가 다음 장면을 생성한다.

핵심 흐름:

```text
Player Input
  -> StoryAgent
  -> Narrative / Choices / Snapshot
  -> Session Update
  -> UI
```

## 현재 아키텍처

주요 문서:
- Backend: [docs/backend/BACKEND.md](/Users/light8reeze/Documents/Projects/OpenNovel/docs/backend/BACKEND.md)
- Frontend: [docs/frontend/FRONTEND.md](/Users/light8reeze/Documents/Projects/OpenNovel/docs/frontend/FRONTEND.md)

현재 구현 요소:
- Python `agent` 기반 단일 서버
- startup 시 `StorySetupAgent`가 생성하거나 fallback으로 채우는 3개의 story setup preset
- `StoryAgent` 중심의 agent-owned story progression
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

`StoryAgent`는 다음을 생성한다.
- narrative
- choices
- compatibility state
- compatibility engine result

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
    "flags": []
  },
  "world": {
    "time": "night",
    "global_flags": ["sunken_ruins_open"],
    "alert_by_region": {
      "ruins": 6
    }
  },
  "quests": {
    "sunken_ruins": {
      "stage": 0
    }
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
  -> StoryAgent.advance()
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
  -> StoryAgent.start()
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

### Story Prompt

역할:
- 플레이어 입력 해석
- 장면 진행
- narrative 생성
- choice 생성
- state snapshot 생성

입력:
- current state
- recent history
- selected story setup
- player input

출력:
- `narrative`
- `choices`
- `state`
- `engineResult`

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

1. 현재 `main`에서는 `StoryAgent`가 진행과 표현을 함께 소유한다.
2. 세션 히스토리와 최신 snapshot이 진실이다.
3. direct compatibility endpoint는 `IntenderAgent`, `NarratorAgent`로 유지한다.
4. LLM 출력은 구조화 JSON을 우선한다.
5. 실패 시 template / heuristic fallback이 존재한다.
