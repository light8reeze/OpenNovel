# Agent Prompt Structure

이 문서는 현재 `agent` 서비스가 사용하는 프롬프트 구조를 정리한다.

기준 코드:

- `agent/app/prompts/system_rules.py`
- `agent/app/prompts/intent_builder.py`
- `agent/app/prompts/narrative_builder.py`

현재 agent는 역할별로 두 종류의 프롬프트를 사용한다.

- `IntenderAgent`
  - 플레이어 자연어 입력을 `Action` 후보로 정규화
- `StoryStateManagerAgent`
  - 다음 턴의 scene summary, state patch, choice 후보를 제안
- `NarratorAgent`
  - validator가 확정한 결과를 바탕으로 장면 서술과 선택지를 생성

## 1. 공통 System Rules

두 프롬프트 모두 같은 공통 system rules를 앞에 붙인다.

핵심 규칙:

- 진실은 입력으로 받은 `state summary`, `engine result`, `allowed actions`, `allowed choices`뿐이다.
- 상태를 변경하지 않는다.
- 성공/실패 판정을 새로 하지 않는다.
- 퀘스트 진행을 결정하지 않는다.
- 플레이어가 모르는 정보를 확정하지 않는다.
- 반드시 JSON으로만 응답한다.

이 레이어는 agent 전체의 guardrail이다.

## 2. Intender Prompt

구현 위치:

- `agent/app/prompts/intent_builder.py`

### 목적

- 플레이어 입력을 가장 적절한 `action_type`과 `target`으로 정규화한다.
- backend가 주는 `allowed_actions`와 `visible_targets`를 벗어나지 않도록 유도한다.
- 최종 판정 권한은 backend에 남긴다.

### 구조

`system_prompt`

- 공통 `SYSTEM_RULES`
- 역할 설명
  - 플레이어 입력을 action type으로 정규화하는 역할
  - 최종 판정 권한은 backend에 있음
- 출력 JSON 형식 설명

출력 shape:

```json
{
  "action": {
    "action_type": "MOVE|TALK|ATTACK|INVESTIGATE|REST|USE_ITEM|FLEE|TRADE",
    "target": "string|null",
    "raw_input": "원문"
  },
  "confidence": 0.0,
  "validation_flags": ["..."],
  "source": "llm"
}
```

`user_prompt`

- `player_input`
- `allowed_actions`
- `Current State`
  - `turn`
  - `location_id`
  - `hp`
  - `gold`
  - `story_arc_stage`
  - `player_flags`
- `Scene Context`
  - `location_name`
  - `npcs_in_scene`
  - `visible_targets`
- `retrieval context`
- 규칙
  - `allowed_actions` 밖의 action 금지
  - `visible_targets` 밖의 target 금지
  - 모호하면 `INVESTIGATE`
  - retrieval은 힌트일 뿐 상태보다 우선하지 않음
  - 이동 target은 현재 backend vocabulary만 사용

### 현재 target vocabulary

현재 target vocabulary는 scene context에서 서버가 노출한 값들이다.

- 현재 location의 연결된 장소 label
- 현재 location의 NPC label
- 테마별 victory path label
- `횃불`

## 3. Narrator Prompt

구현 위치:

- `agent/app/prompts/narrative_builder.py`

### 목적

- validator가 이미 확정한 결과를 장면 서술로 표현한다.
- 허용된 choice 목록 안에서만 선택지를 출력한다.
- 분위기와 NPC 화법을 retrieval context로 보강한다.

### 구조

`system_prompt`

- 공통 `SYSTEM_RULES`
- 역할 설명
  - validator가 확정한 결과를 바탕으로 장면 묘사와 선택지를 JSON으로 출력
- 출력 JSON 형식 설명

출력 shape:

```json
{
  "narrative": "string",
  "choices": ["string", "string"],
  "source": "llm",
  "used_fallback": false,
  "safety_flags": []
}
```

`user_prompt`

- `Kind`
  - `opening` 또는 `turn`
- `Current State Summary`
  - `turn`
  - `location_id`
  - `hp`
  - `gold`
  - `story_arc_stage`
  - `theme_id`
  - `style_tags`
  - `objective_status`
  - `victory_path`
  - `player_flags`
- `Scene Context`
  - `location_name`
  - `npcs_in_scene`
  - `visible_targets`
- `retrieval context`
- `Resolved outcome`
  - `success`
  - `message_code`
  - `location_changed`
  - `quest_stage_changed`
  - `ending_reached`
  - `details`
- `Allowed choices`
- 규칙
  - `allowed_choices` 밖의 선택지 생성 금지
  - 한국어 출력
- 분위기는 현재 world blueprint와 theme state를 따른다
  - 과장된 시적 표현 금지
  - choice는 2개 이상 4개 이하
  - retrieval은 장면/말투 참고용

### opening 과 turn 차이

- `opening`
  - engine result가 없고, `장면 시작이다. 아직 engine result는 없다.` 블록을 사용
- `turn`
  - 실제 `engine_result`가 포함되며 `Resolved outcome` 블록을 채운다

## 4. Retrieval Context 사용 방식

Intender와 Narrator 모두 prompt에 retrieval block을 삽입한다.

현재 retrieval source:

- `agent/content/intender_docs/`
  - 위치 별칭
  - 행동 힌트
- `agent/content/narrator_docs/`
  - 위치 분위기
  - NPC voice
  - 퀘스트 stage guide

retrieval context는 prompt 안에서 참고 자료 역할만 한다.

- 입력 상태와 충돌하면 안 된다.
- backend validator vocabulary를 덮어쓰면 안 된다.
- narrator는 player-visible 문서만 사용한다.

## 5. Prompt 이후 검증

Prompt만으로 안전성을 보장하지 않고, role 객체가 후처리 검증을 수행한다.

### Intender 검증

구현 위치:

- `agent/app/agents/intender.py`

검증 항목:

- `action_type`이 `allowed_actions` 안에 있는지
- `target`이 `visible_targets` 안에 있는지

위반 시:

- `INVESTIGATE`로 낮추거나
- `target_not_visible`, `action_not_allowed` 플래그 추가
- confidence 하향

### Narrator 검증

구현 위치:

- `agent/app/agents/narrator.py`

검증 항목:

- choice가 `allowed_choices` 안에 있는지
- choice 개수가 2개 이상인지
- narrative 본문이 비어 있지 않은지

위반 시:

- template fallback으로 교체

## 6. Fallback Prompt 전략

LLM 실패 시 두 역할 모두 fallback을 사용한다.

- `IntenderAgent`
  - heuristic intent parser 사용
- `NarratorAgent`
  - template narrative 사용

구현 위치:

- `agent/app/agents/intender.py`
- `agent/app/services/fallback_renderer.py`

즉 현재 구조는:

`prompt -> model -> schema parse -> runtime validation -> fallback if needed`

## 7. 현재 프롬프트 설계 요약

현재 프롬프트 설계는 다음 원칙을 따른다.

1. backend가 허용 범위를 먼저 계산한다.
2. prompt는 그 범위 안에서만 해석/표현하도록 agent를 유도한다.
3. retrieval은 품질 향상 레이어이지 진실 소스가 아니다.
4. 최종 안전성은 prompt가 아니라 runtime validation과 fallback이 보장한다.
