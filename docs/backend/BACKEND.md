# AGENTS.md

AI Novel Player Backend — Codex Development Guide

## 1. Project Overview

이 프로젝트는 **AI 기반 인터랙티브 소설 플레이 서비스**이다.

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
                         |
                REST / WebSocket
                         |
+------------------------------------------------+
|                Backend API                     |
|                                                |
|  +-------------+    +----------------------+   |
|  | Session     |    | Game Engine          |   |
|  | Manager     |--->| State Transition     |   |
|  +-------------+    +----------------------+   |
|          |                    |                |
|          |                    v                |
|          |           +-------------------+     |
|          |           | Narrative Engine  |     |
|          |           | (LLM Adapter)     |     |
|          |           +-------------------+     |
|          |                    |                |
|          v                    v                |
|      Persistence        Prompt Builder         |
|      (DB / Storage)                            |
+------------------------------------------------+
```

---

# 3. Technology Stack

초기 MVP 기준

### Language

추천

```
Go or Rust
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
Action Parser
     |
Rule Engine
     |
State Update
     |
Narrative Generation
```

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

---

# 8. API Design

## Create Session

```
POST /session
```

response

```
{
  session_id
}
```

---

## Send Player Action

```
POST /action
```

request

```
{
  session_id
  action
}
```

flow

```
action
→ game engine
→ state update
→ narrative generation
→ response
```

response

```
{
  narrative
  updated_state
}
```

---

## Get Session State

```
GET /session/{id}
```

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