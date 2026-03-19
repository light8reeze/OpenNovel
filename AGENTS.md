# AGENTS.md

## 1. 프로젝트 개요

이 프로젝트는 **OpenNovel**, AI 기반 텍스트 인터랙티브 소설 게임이다.

플레이어는 채팅 형식 UI를 통해 게임을 진행하며,
AI는 **스토리 서술과 NPC 대사**를 생성한다.

게임의 **진실 상태(Source of Truth)** 는 항상 **Core Game Engine**이 관리한다.

AI는 게임 상태를 변경하거나 판정하지 않는다.

---
# 2. 아키텍처 원칙

시스템은 다음 두 레이어로 분리된다.

```
Player Input
      ↓
Core Game Engine
      ↓
Game State Update
      ↓
LLM Narrative Generator
      ↓
UI 출력
```

## Backend

@docs/backend/BACKEND.md 문서를 참고한다.

### Core Game Engine 역할

* 게임 상태 관리
* 행동(Action) 판정
* 이벤트(Event) 처리
* 상태(State) 변경
* 퀘스트 진행 관리

### LLM 역할

* 플레이어 입력 의도 파악
* 장면 묘사
* NPC 대사 생성
* 선택지 제안

LLM은 **표현 계층(Narrative Layer)** 이다.

## Frontend

@docs/frontend/FRONTEND.md 문서를 참고한다.

### 현재 구현 상태

현재 저장소에는 다음이 구현되어 있다.

* Python `agent` 기반 단일 공식 서버
* `GET /`, `GET /health`, `POST /game/start`, `POST /game/action`, `GET /game/state` API
* 개발 모드 전용 `GET /debug/turn-log` API
* 메모리 기반 세션 관리
* deterministic core game engine
* 루트 `content/` 기반 정적 JSON 콘텐츠 로더
* Chroma 기반 retrieval
* `IntenderAgent`와 `NarratorAgent`로 분리된 LLM 계층
* 기본 템플릿 narrative 폴백
* 세션 시작 시 선택적으로 Gemini API 키를 받아 narrator를 Gemini로 실행
* 단일 서버에서 정적 frontend 서빙
* 채팅 UI + 턴 그래프 + hover 디버그 로그 UI

아직 미구현 또는 placeholder 상태인 항목은 다음과 같다.

* SQLite 기반 영속 저장소
* Memory Summary 파이프라인
* React/TypeScript 기반 frontend
* 실시간 스트리밍 응답

---

# 3. 핵심 원칙

## 3.1 게임 상태의 진실

게임의 진실은 항상 **Game State** 이다.

LLM은 다음을 수행하면 안 된다.

* 상태 변경
* 성공/실패 판정
* 퀘스트 진행 결정
* 아이템 획득 확정
* 사실 생성

LLM은 **엔진이 결정한 결과를 표현만 한다.**

---

## 3.2 상태 변경 방식

상태 변경은 항상 **Event 기반**으로 처리한다.

예:

```
HP_DELTA(-10)
GOLD_DELTA(+30)
ADD_FLAG("found_rune")
QUEST_STAGE_SET("sunken_ruins", 2)
AFFINITY_DELTA("caretaker", +2)
```

LLM은 Event를 생성하지 않는다.

---

# 4. Game State 구조

MVP에서는 단순한 상태 모델을 사용한다.

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

---

# 5. Action → Event 처리 흐름

플레이어 입력은 다음 순서로 처리된다.

```
Player Input
    ↓
Intent Parsing
    ↓
Action 결정
    ↓
Game Engine 판정
    ↓
Event 생성
    ↓
Game State 업데이트
    ↓
LLM Narrative 생성
```

---

# 6. LLM 프롬프트 구조

LLM 프롬프트는 다음 5개 섹션으로 구성한다.

```
System Rules
World / Tone Guide
Current State Summary
Resolved Outcome
Output Format
```

---

# 7. System Rules

LLM의 절대 규칙이다.

예:

* 너는 텍스트 기반 인터랙티브 소설 게임의 서술 AI다.
* 게임의 진실은 입력으로 제공된 state와 event_result이다.
* 입력에 없는 사실을 확정하지 마라.
* 상태를 변경하지 마라.
* 성공/실패 판정을 새로 하지 마라.
* 플레이어가 모르는 정보를 공개하지 마라.
* 응답은 반드시 지정된 JSON 형식을 따른다.

---

# 8. World / Tone Guide

세계관과 문체를 정의한다.

예:

* 장르: 다크 판타지 던전 탐험
* 분위기: 오래 잠든 폐허와 봉인의 긴장감
* 문체: 간결하지만 몰입감 있는 묘사
* 과도한 시적 표현 금지

---

# 9. Current State Summary

현재 장면에 필요한 상태만 전달한다.

예:

```
현재 위치: collapsed hall
시간: night

HP: 80
Gold: 20

Quest: sunken_ruins stage=2

Flags:
- found_rune
- opened_passage

NPC affinity:
caretaker = 7
```

---

# 10. Resolved Outcome

Game Engine이 판정한 결과이다.

예:

```
Player action: 성소의 제단을 조사한다
Normalized action: INVESTIGATE

Result:
success: true
message_code: SEAL_BROKEN
hp_delta: 0
gold_delta: 0
quest_stage_changed: true
```

LLM은 이 결과를 기반으로 **묘사만 생성한다.**

---

# 11. Output Format

LLM 출력은 JSON 형식으로 제한한다.

예:

```json
{
  "narrative": "갈라진 제단 표면을 따라 희미한 빛이 번지더니 오래 잠들어 있던 봉인이 마침내 금을 내기 시작한다.",
  "choices": [
    "주변을 더 조사한다",
    "함정방으로 이동한다",
    "후퇴한다"
  ]
}
```

---

# 12. LLM 프롬프트 종류

프로젝트에서는 다음 3개의 프롬프트를 사용한다.

## 12.1 Narrative Prompt

역할

* 장면 묘사
* NPC 대사 생성
* 선택지 생성

입력

* Scene context
* Game state 요약
* Engine result

출력

```
narrative
choices
```

---

## 12.2 Intent Parsing Prompt

플레이어 자연어 입력을 **Action 타입**으로 변환한다.

예:

| 입력        | Action      |
| --------- | ----------- |
| 주변을 살펴본다  | INVESTIGATE |
| 관리인과 대화한다 | TALK        |
| 회랑으로 이동한다 | MOVE        |
| 유적에서 후퇴한다 | FLEE        |

---

## 12.3 Memory Summary Prompt

턴이 길어질 때 최근 사건을 요약한다.

목적

* 토큰 절약
* 스토리 일관성 유지

예

```
최근 사건 요약:
- 플레이어는 관리인에게 유적의 경고를 들었다
- 입구 문양에서 봉인 흔적을 확인했다
- 함정방에서 바닥 장치의 패턴을 파악했다
```

---

# 12.4 현재 구현된 LLM 연동 방식

현재 구현에서는 Python `agent`가 LLM 연동의 진입점이다.

* `IntenderAgent`가 플레이어 입력을 action candidate로 정규화한다.
* `NarratorAgent`가 opening/turn narrative JSON 생성을 시도한다.
* 세션 시작 시 `geminiApiKey`를 입력받을 수 있다.
* API 키가 있으면 해당 세션의 narrator가 Gemini API를 사용해 narrative JSON 생성을 시도한다.
* 실패하면 agent 내부 템플릿 narrative로 폴백한다.
* 엔진 판정과 상태 전이는 항상 deterministic game engine이 수행한다.

즉 현재도 다음 원칙은 유지된다.

* LLM은 상태를 바꾸지 않는다.
* LLM은 성공/실패 판정을 하지 않는다.
* `state`, `engineResult`가 진실이다.

---

# 13. UI 구조

MVP UI의 주 인터랙션은 **채팅 기반 인터페이스**다.
현재 구현은 여기에 `턴 그래프`와 `hover 디버그 로그` 패널을 보조적으로 추가한 형태다.

구조

```
Story Log
   ↓
Choice Buttons
   ↓
Player Input
```

예

```
어두운 골목에서 비명 소리가 들린다.

[1] 소리가 난 곳으로 간다
[2] 주변을 조사한다
[3] 도망친다
```

---

# 14. MVP 범위

MVP는 다음 범위로 제한한다.

* 플레이 시간: 30~45분
* 엔딩: 2~3개
* NPC: 3~5명
* Quest: 1개
* Action: 8개 이하

Action 예

```
move
talk
attack
investigate
rest
use_item
flee
trade
```

---

# 15. 핵심 설계 원칙 요약

1. **Game Engine이 게임을 운영한다**
2. **LLM은 표현만 담당한다**
3. **상태 변경은 Event 기반**
4. **LLM 출력은 구조화(JSON)**
5. **프롬프트는 역할별로 분리**
