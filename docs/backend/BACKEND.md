OpenNovel Backend — Codex Development Guide

## 1. Project Overview

이 프로젝트는 **OpenNovel**, AI 기반 인터랙티브 소설 플레이 서비스이다.

플레이어는 채팅 인터페이스를 통해 소설 속 주인공이 되어 행동을 선택하며,
LLM은 게임 마스터(GM) 역할을 수행하여 세계 상태와 스토리를 생성한다.

### Core Concept

```
Player Input → Game Engine → World State Update → LLM Narrative → Response
```

핵심 구성 요소

1. **Game Engine**

   * 세계 상태 관리
   * 행동 결과 계산
   * 룰 기반 로직

2. **LLM Story Generator**

   * 현재 상태 기반 스토리 생성
   * 플레이어 행동을 narrative로 변환

3. **Session Manager**

   * 플레이어 진행 상태 관리
   * 저장 / 로딩

---
# 2. Backend Architecture

## High-Level Architecture

```
                +------------------+
                |   Frontend UI    |
                |  (Chat Interface)|
                +--------+---------+
                         |
                       REST
                         |
+--------------------------------------------------+
|              Agent FastAPI Service               |
|                                                  |
|  +------------------+   +----------------------+ |
|  | Game Session     |-->| Deterministic Engine | |
|  | Service          |   | State Transition     | |
|  +------------------+   +----------------------+ |
|           |                         |            |
|           |                         v            |
|           |              +--------------------+ |
|           |              | IntenderAgent      | |
|           |              | NarratorAgent      | |
|           |              +--------------------+ |
|           |                         |            |
|           v                         v            |
|      In-memory store         Prompt / Retrieval |
|      Static frontend         LLM adapters       |
+--------------------------------------------------+
```

## 현재 구현된 구조

현재 공식 backend 런타임은 Python `agent` 서비스다.

```
agent/
  app/
    api/
    agents/
    game/
    prompts/
    retrieval/
    schemas/
    services/
  tests/
```

현재 Rust workspace는 reference implementation으로 저장소에 남아 있다.

```
backend/
  Cargo.toml
  crates/
    api/
    content/
    domain/
    engine/
    narrative/
    session/
    storage/
```

현재 `agent/app`의 주요 책임은 다음과 같다.

* `game/models.py`: `GameState`, `Event`, `TurnResult`, API request/response 모델 정의
* `game/engine.py`: 입력 해석, 허용 액션 계산, 이벤트 생성, 상태 전이, 선택지 계산
* `game/service.py`: 세션 오케스트레이션, in-memory 저장, `/game/*` 흐름 제어
* `agents/intender.py`: 플레이어 입력을 action candidate로 정규화
* `agents/narrator.py`: engine result를 narrative JSON으로 생성
* `services/fallback_renderer.py`: 템플릿 narrative 폴백
* `api/routes.py`: FastAPI 엔드포인트와 정적 frontend 서빙

클래스 기준 상세 아키텍처는 `docs/backend/AGENT_ARCHITECTURE.md`를 참고한다.

Rust `backend/`의 주요 crate 책임은 reference parity와 회귀 검증 관점에서 유지된다.

* `domain`: 원본 `GameState`, `Action`, `Event`, `EngineResult`, `TurnResult` 정의
* `content`: 원본 JSON 로드 및 검증
* `engine`: 원본 deterministic rule implementation
* `narrative`: 원본 템플릿/Gemini narrative 구현
* `session`: 원본 세션 오케스트레이션
* `api`: 원본 axum 서버
* `storage`: placeholder trait

---

# 3. Technology Stack

초기 MVP 기준

### Language

추천

```
Go or Rust
```

현재 구현 선택

```
Python (official runtime) + Rust (reference backend)
```

이유

* lightweight backend
* concurrency support
* low latency
* simple deployment

### API

```
REST + WebSocket
```

현재 구현 선택

```
REST only
```

WebSocket 사용 이유

* 채팅형 인터페이스
* 실시간 narrative streaming

---

### Database

MVP

```
PostgreSQL
or
SQLite
```

현재 구현 상태

```
아직 미구현
현재는 in-memory session store 사용
```

데이터 종류

```
player_sessions
story_state
character_state
world_state
action_history
```

---

### Cache (Optional)

```
Redis
```

용도

```
session state
LLM prompt cache
```

---

# 4. Project Structure

예상 디렉토리 구조

```
backend/

cmd/
    server/

internal/

    api/
        handlers
        router

    engine/
        game_engine
        rule_engine
        state_machine

    narrative/
        prompt_builder
        llm_adapter

    session/
        session_manager

    model/
        player
        world
        story

    repository/
        database

    config/
        env

pkg/
    utils

scripts/
```

현재 구현된 실제 구조는 상단의 `현재 구현된 구조` 섹션을 따른다.

---

# 5. Core Data Model

## Session

```
Session
{
  session_id
  player_id
  story_id
  current_state
  created_at
}
```

---

## World State

```
WorldState
{
  location
  npc_states
  event_flags
  environment
}
```

---

## Character State

```
Character
{
  hp
  inventory
  abilities
  status_effects
}
```

---

## Player Action

```
Action
{
  action_type
  parameters
}
```

예시

```
"attack goblin"
"open door"
"talk npc"
```

---

# 6. Game Engine

Game Engine은 **LLM과 독립적인 deterministic logic layer**이다.

목적

```
LLM hallucination 방지
게임 룰 안정성
상태 일관성 유지
```

---

## State Transition Flow

```
Player Input
     |
Intent Validation / Heuristic Parse
     |
Rule Engine
     |
State Update
     |
Narrative Generation
```

현재 구현에서는 `agent.app.game.engine`과 `agent.app.game.service`가 다음을 수행한다.

* `IntenderAgent`로 플레이어 입력을 action candidate로 정규화
* validation 실패 시 heuristic parser로 fallback
* `Event` 목록 생성
* `apply_events`로 `next_state` 계산
* `EngineResult` 반환

즉 LLM이 실패해도 deterministic loop는 계속 동작한다.

---

# 7. LLM Narrative Engine

LLM은 **스토리 생성 전용 역할**만 수행한다.

LLM은 다음 정보를 입력받는다

```
World State
Character State
Player Action
Recent Story Context
```

---

## Prompt Template

Example

```
You are a game master narrating an interactive story.

World State:
{world_state}

Player State:
{character_state}

Player Action:
{action}

Narrate the outcome in immersive storytelling style.
```

## 현재 구현 상태

현재 narrative 계층은 두 가지 경로를 가진다.

1. 기본 템플릿 narrative
2. LLM 기반 narrative JSON 생성

LLM 연동 방식

* `POST /game/start` 요청에서 `geminiApiKey`와 선택적 `geminiModel`을 받을 수 있다.
* 세션이 시작될 때 API 키를 세션 narrator 설정에 저장한다.
* 이후 turn마다 `state`와 `engineResult` 기반 prompt를 만들어 narrator를 호출한다.
* Gemini 또는 기타 provider 응답은 반드시 JSON으로 파싱한다.
* 호출 실패 또는 파싱 실패 시 템플릿 narrative로 폴백한다.

중요:

* Gemini는 `narrative`와 `choices`만 생성한다.
* 상태 전이, 퀘스트 진행, 판정은 전부 `engine`이 수행한다.

---

# 8. API Design

## 현재 구현된 API

현재 실제 구현 엔드포인트는 다음과 같다.

### `GET /`

정적 frontend shell을 반환한다.

### `GET /frontend/app.js`

정적 frontend 스크립트를 반환한다.

### `GET /frontend/styles.css`

정적 frontend 스타일시트를 반환한다.

### `POST /game/start`

request body (optional)

```json
{
  "geminiApiKey": "AIza...",
  "geminiModel": "gemini-2.5-flash"
}
```

response

```json
{
  "sessionId": "...",
  "narrative": "...",
  "choices": ["..."],
  "state": { }
}
```

### `POST /game/action`

request

```json
{
  "sessionId": "...",
  "inputText": "주변을 조사한다"
}
```

또는

```json
{
  "sessionId": "...",
  "choiceText": "창고로 이동한다"
}
```

response

```json
{
  "narrative": "...",
  "choices": ["..."],
  "engineResult": { },
  "state": { }
}
```

### `GET /game/state?sessionId=...`

response

```json
{
  "state": { }
}
```

### 내부 보조 API

다음 엔드포인트는 agent 내부 LLM 계층을 직접 검증할 때 사용한다.

* `GET /health`
* `POST /intent/validate`
* `POST /narrative/opening`
* `POST /narrative/turn`

---

# 9. State Persistence

저장해야 하는 데이터

```
player progress
world state
character state
story history
```

story history는 다음 목적에 사용

```
LLM context
replay
save/load
```

---

# 10. Coding Guidelines

### Architecture

```
domain logic must not depend on LLM
engine must be deterministic
API layer must be thin
```

---

### Engine Rules

```
No LLM inside engine
No DB access inside engine
Pure logic only
```

---

### LLM Adapter

LLM provider abstraction

```
OpenAI
Local LLM
Anthropic
```

interface

```
GenerateNarrative(context) -> text
```

현재 구현은 provider abstraction 대신 Gemini 전용 최소 연동을 먼저 넣은 상태다.

향후 정리 방향

* provider trait 분리
* Gemini/OpenAI 등 provider 교체 가능 구조화
* intent / narrative / memory summary 분리

---

# 11. Development Commands

example

```
make run
make test
make lint
```

---

# 12. Testing Strategy

테스트 레벨

### Unit Test

```
game engine
state transition
rules
```

---

### Integration Test

```
API endpoints
session lifecycle
```

---

### Simulation Test

```
LLM mock
story progression test
```

---

# 13. Future Architecture

MVP 이후 확장

```
multi player session
procedural world generation
vector memory for long story
AI NPC agents
```

---

# 14. Non-goals (MVP)

MVP에서 제외

```
MMORPG
complex economy system
real-time combat
```

---

# 15. Design Principles

핵심 철학

```
LLM handles narrative
Engine handles logic
State is source of truth
```

---

## Codex Agent Instructions

When generating code:

1. Do not mix engine logic with LLM logic.
2. Follow the project directory structure.
3. Prefer simple deterministic systems.
4. Avoid unnecessary abstractions.
