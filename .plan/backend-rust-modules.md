# Rust Backend 모듈 작업계획 (MVP)

## 목표
- Core Game Engine이 게임 상태의 진실(Source of Truth)을 유지한다.
- LLM은 `Intent Parsing`과 `Narrative`만 담당하고 상태/판정/이벤트 생성은 절대 하지 않는다.
- 엔진 로직은 결정론적(deterministic)이며 DB/LLM/네트워크에 의존하지 않는다.

## 권장 Rust 스택(초기 선택)
- Runtime/HTTP: `tokio`, `axum`
- JSON: `serde`, `serde_json`
- Validation: `jsonschema`(선택) 또는 수동 검증
- DB: `sqlx` + SQLite (MVP), 마이그레이션 포함
- Logging: `tracing`, `tracing-subscriber`

## 디렉터리(권장)
- `backend/` Cargo workspace
  - `backend/crates/domain/` : 도메인 타입/스키마
  - `backend/crates/engine/` : Core Game Engine(판정 + 이벤트 생성 + 상태 전이)
  - `backend/crates/content/` : 정적 콘텐츠 로더(로케이션/NPC/퀘스트)
  - `backend/crates/narrative/` : LLM 어댑터 + 프롬프트 빌더 + JSON 파서
  - `backend/crates/session/` : 턴 오케스트레이션(의도→엔진→서술)
  - `backend/crates/storage/` : 세션 저장소(SQLite)
  - `backend/crates/api/` : HTTP API(axum)
- `content/` : 게임 데이터(JSON/YAML)
- `prompts/` : 프롬프트 템플릿(버전 관리)

---

## crates/domain (타입/DTO)
### 책임
- AGENTS.md의 `GameState` 스키마를 Rust struct로 고정
- 엔진/세션/API 사이 계약 DTO 정의

### 주요 타입
- `GameState` (meta/player/world/quests/relations)
- `ActionType` (MOVE/TALK/ATTACK/INVESTIGATE/REST/USE_ITEM/FLEE/TRADE)
- `Action { action_type, slots }` (slots는 MVP 최소)
- `Event` (HP_DELTA, GOLD_DELTA, ADD_FLAG, QUEST_STAGE_SET, AFFINITY_DELTA, …)
- `EngineResult` (success, message_code, found_clue?, deltas?, quest_changed?, …)
- `TurnResult { narrative, choices, state, engine_result }` (API 응답 기준)

### 작업
- `serde` derive + 버전 호환(필드 추가에 강한 구조)
- `StateSummary`(프롬프트/UI용 최소 상태) 생성 함수 제공

---

## crates/engine (Core Game Engine)
### 책임
- 입력 Action과 현재 GameState로부터 `events[]`와 `engine_result`를 생성
- `Reducer`로 이벤트를 적용해 `next_state`를 만든다
- 결정론 보장(동일 seed/state/action => 동일 결과)

### 모듈
- `reducer`: `apply_events(state, events) -> GameState`
- `rules`: `resolve(action, state, content, rng) -> (events, engine_result)`
- `available_actions`: `list_available_actions(state, content) -> Vec<ActionHint>`
- `rng`: `SeededRng(meta.seed)` 래퍼

### 작업
- 이벤트 적용 경계값 처리(HP 0..=100 등)
- `murder_case` 퀘스트 stage 전이 테이블 구현(조건=플래그/스테이지/인벤토리)
- 불가능/모호 입력에 대한 엔진 안전 응답(실패 result + 상태 변화 없음)

---

## crates/content (정적 데이터)
### 책임
- `content/` 아래 데이터 로딩 및 런타임 조회 API 제공

### 작업
- 스키마 확정
  - `content/locations.json`: 이동 가능한 연결, 조사 포인트
  - `content/npcs.json`: 등장 위치, 대화 키, affinity 초기값
  - `content/quests/murder_case.json`: stage 정의, 조건, 보상 이벤트
- 로더: `load_all() -> Content` + 조회 메서드

---

## crates/narrative (LLM + Prompt)
### 책임
- Intent Parsing / Narrative / Memory Summary 3종 프롬프트 호출
- LLM 응답 JSON 파싱/검증/폴백
- LLM이 생성한 텍스트는 “표현”만, 상태/판정/이벤트는 절대 반영하지 않음

### 인터페이스
- `trait LlmClient { async fn complete(prompt: String) -> String; }`
- `IntentParser`: `parse_intent(input, state_summary) -> Action` (JSON only)
- `NarrativeGenerator`: `generate(state_summary, engine_result, action_hints) -> (narrative, choices[])`
- `MemorySummarizer`: `summarize(recent_log) -> summary_text`

### 작업
- JSON 파싱 실패 시: 1회 재요청(“반드시 JSON만”) 후 실패하면 폴백
- choices는 2~4개로 강제, 길이/중복 제한
- prompts는 `prompts/` 템플릿 + 코드에서 변수 치환

---

## crates/storage (세션 저장소)
### 책임
- 세션/상태/로그/요약 저장

### 작업
- SQLite 스키마
  - `sessions(session_id, created_at, updated_at)`
  - `session_state(session_id, state_json, memory_summary, turn)`
  - `session_log(session_id, idx, role, content, created_at)`
- Repo trait
  - `create_session() -> session_id`
  - `get_state(session_id) -> GameState`
  - `save_turn(session_id, next_state, log_append, memory_summary?)`

---

## crates/session (턴 오케스트레이션)
### 책임
- 고정 파이프라인을 구현하는 유일한 서비스 레이어

### 파이프라인
1) 입력 수신(텍스트/choice)
2) `narrative::IntentParser` → `Action`
3) `engine::resolve` → `(events, engine_result)`
4) `engine::apply_events` → `next_state`
5) `narrative::NarrativeGenerator` → `(narrative, choices)`
6) `storage`에 저장 + API DTO 반환

### 작업
- 메모리 요약 트리거(턴 수/로그 길이) 및 summary 저장
- 엔진/LLM 예외 시 사용자에게 안전한 시스템 메시지 제공

---

## crates/api (HTTP)
### 책임
- axum 라우팅 + DTO 변환 + 세션 서비스 호출

### 엔드포인트
- `POST /game/start`
- `POST /game/action`
- `GET /game/state`

### 작업
- CORS, request id, tracing
- 입력 검증(sessionId 존재, payload 상호배타)

---

## 테스트(최소)
- `crates/engine`: reducer/rules 단위 테스트(결정론, 경계값, 퀘스트 전이)
- `crates/session`: LLM mock으로 turn 시뮬레이션 테스트 1개
- `crates/api`: 라우트 스모크(LLM mock + in-memory sqlite)
