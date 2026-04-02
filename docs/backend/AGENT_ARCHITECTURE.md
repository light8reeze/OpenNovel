# Agent Architecture

이 문서는 현재 OpenNovel `agent` 서비스의 클래스 기준 아키텍처를 설명한다.

현재 `agent`는 OpenNovel의 공식 단일 서버이며, 다음 역할을 함께 수행한다.

* 정적 frontend 서빙
* `/game/*` 게임 API 제공
* deterministic validation 실행
* LLM 기반 intent / narrative 계층 호출
* retrieval / vector store 관리

---

## 1. 전체 구조

```
HTTP Request
    |
FastAPI Router
    |
AgentRuntime
    |
GameSessionService
    |
+----------------------+------------------------+----------------+
|                      |                        |                |
v                      v                        v                v
IntenderAgent   StoryStateManagerAgent   RuleValidator   NarratorAgent
                                          |
                                          v
                                      GameState
```

핵심 원칙:

* `GameSessionService`가 오케스트레이션을 담당한다.
* `RuleValidator`가 상태 전이의 진실 소스다.
* `IntenderAgent`, `StoryStateManagerAgent`, `NarratorAgent`는 제안/표현 계층이다.
* LLM은 상태를 바꾸지 않는다.

---

## 2. Runtime 조립 계층

### `AgentRuntime`

파일:

* `agent/app/runtime.py`

역할:

* 전체 서비스의 조립 루트
* 설정 로딩
* vector store / retrieval 초기화
* `IntenderAgent`, `NarratorAgent`, `StoryStateManagerAgent`, `WorldBuilderAgent`, `GameSessionService` 생성
* startup 시 retrieval 문서 인덱싱

이 클래스는 직접 게임 판정이나 narrative 생성을 수행하지 않는다.
책임은 객체 생성과 의존성 연결이다.

보유 객체:

* `settings`
* `store: ChromaVectorStore`
* `retrieval: RetrievalService`
* `intender: IntenderAgent`
* `narrator: NarratorAgent`
* `game: GameSessionService`

관련 함수:

* `get_runtime()`
  * 싱글턴 런타임 반환
* `game_content_root()`
  * 루트 `content/` 경로 반환
* `frontend_root()`
  * 루트 `frontend/` 경로 반환

---

## 3. API 계층

### FastAPI Router

파일:

* `agent/app/api/routes.py`

역할:

* HTTP 요청을 내부 서비스 호출로 변환
* request/response 직렬화
* 에러를 HTTP status code로 변환
* 정적 frontend 파일 응답

주요 엔드포인트:

* `GET /`
* `GET /frontend/app.js`
* `GET /frontend/styles.css`
* `POST /game/start`
* `POST /game/action`
* `GET /game/state`
* `GET /health`
* `POST /intent/validate`
* `POST /narrative/opening`
* `POST /narrative/turn`

설계 원칙:

* 라우터는 얇게 유지한다.
* 상태 전이 로직은 라우터에 두지 않는다.
* 라우터는 `AgentRuntime`에 연결된 서비스만 호출한다.

---

## 4. Game Runtime 계층

### `GameSessionService`

파일:

* `agent/app/game/service.py`

역할:

* `/game/*` API의 실제 application service
* 세션 생성 / 조회 / 갱신
* 플레이어 입력 처리 흐름 제어
* world builder 호출
* intender 호출
* state manager 호출
* validator 호출
* narrator 호출
* 응답 조립

이 클래스가 현재 OpenNovel backend 역할의 중심이다.

주요 메서드:

* `start_game()`
  * 초기 상태 생성
  * 세션 ID 발급
  * opening narrative 생성
  * 세션 저장
* `apply_action()`
  * 입력 검증
  * 세션 조회
  * intent 정규화
  * 엔진 판정
  * turn narrative 생성
  * 다음 상태 저장
* `get_state()`
  * 현재 세션 상태 반환
* `demo_script()`
  * 고정 시나리오를 재생해 검증용 turn 목록 생성

### `SessionRecord`

파일:

* `agent/app/game/service.py`

역할:

* 세션별 런타임 데이터 저장
* 현재 `GameState`
* 세션별 runtime agent 집합
* world blueprint
* discovery log

세션별 narrator를 따로 저장하는 이유:

* `/game/start`에서 받은 `geminiApiKey`, `geminiModel`을 세션 단위로 유지하기 위해서다.

### 예외 클래스

파일:

* `agent/app/game/service.py`

클래스:

* `SessionNotFoundError`
* `InvalidActionRequestError`

역할:

* 도메인 오류를 HTTP 레벨과 분리
* 라우터가 적절한 status code로 변환할 수 있게 함

---

## 5. Deterministic Validation 계층

파일:

* `agent/app/services/validator.py`

역할:

* state patch 검증
* intent 기본 진행 적용
* 테마 규칙 반영
* style scoring 누적
* objective / victory path 판정
* allowed choices 재생성
* `EngineResult` 생성

중요한 설계 포인트:

* 이 계층은 LLM 출력에 종속되지 않는다.
* 게임의 성공/실패 판정은 여기서 결정된다.
* `GameSessionService`는 이 결과를 오케스트레이션한다.

---

## 6. Game Model 계층

파일:

* `agent/app/game/models.py`

이 파일은 게임 상태, API 모델, 콘텐츠 모델을 정의한다.

### 상태 모델

* `MetaState`
* `PlayerState`
* `WorldState`
* `QuestProgress`
* `QuestState`
* `RelationsState`
* `GameState`

역할:

* 엔진이 읽고 쓰는 상태 구조 정의
* `GameState.summary()`로 LLM에 전달할 축약 상태 생성
* `GameState.has_flag()`로 엔진 조건 검사 지원

### 턴 / 오케스트레이션 모델

* `TurnResult`
* `Event`
* `Resolution`
* `StartOptions`

역할:

* 엔진 결과와 narrative 결과를 묶는 중간 표현
* 세션 생성 옵션 전달

### API 모델

* `StartRequest`
* `StartResponse`
* `ActionRequest`
* `ActionResponse`
* `StateResponse`

역할:

* `/game/*` wire contract 정의
* `sessionId`, `inputText`, `choiceText`, `engineResult` 등의 alias 유지

### 콘텐츠 모델

* `Location`
* `Npc`
* `QuestStageDefinition`
* `QuestDefinition`
* `ContentBundle`

역할:

* 루트 `content/` JSON 로드
* location / quest 데이터 검증
* `location_name()` 조회 제공

---

## 7. Intent 계층

### `IntenderAgent`

파일:

* `agent/app/agents/intender.py`

역할:

* 플레이어 자유 입력을 action candidate로 정규화
* retrieval 기반 문맥 검색
* prompt 생성
* LLM JSON 호출
* fallback heuristic 적용
* 최종 검증

주요 의존성:

* `RoleModelSettings`
* `BaseLlmClient`
* `RetrievalService`

처리 순서:

1. `RetrievalService`로 intender 문서 검색
2. prompt builder로 system/user prompt 생성
3. LLM JSON 호출
4. 실패 시 heuristic fallback
5. allowed action / visible target 기준으로 결과 보정

중요:

* `IntenderAgent`는 action 후보만 만든다.
* 상태 전이는 전혀 수행하지 않는다.

---

## 8. Narrative 계층

### `NarratorAgent`

파일:

* `agent/app/agents/narrator.py`

역할:

* opening narrative 생성
* turn narrative 생성
* retrieval 기반 문맥 검색
* prompt 생성
* LLM JSON 호출
* fallback narrative 적용
* choice filtering / safety validation

주요 메서드:

* `render_opening()`
* `render_turn()`
* `_render()`
* `_validate()`
* `_fallback()`

처리 순서:

1. narrator 문서 retrieval
2. prompt builder 호출
3. LLM JSON 응답 파싱
4. 실패 시 fallback renderer 사용
5. `allowed_choices` 기준으로 choices 필터링
6. narrative/choices 품질 검증

중요:

* `NarratorAgent`는 묘사만 담당한다.
* `engine_result`를 받아 표현할 뿐, 결과를 바꾸지 않는다.

---

## 9. Retrieval 계층

### `RetrievalService`

파일:

* `agent/app/retrieval/search.py`

역할:

* intender / narrator용 검색 진입점
* Chroma query 실행
* stage / location / visibility 필터링

주요 메서드:

* `search_for_intender()`
* `search_for_narrator()`
* `collection_count()`

### `ChromaVectorStore`

파일:

* `agent/app/retrieval/vector_store.py`

역할:

* Chroma PersistentClient 래퍼
* role별 collection 접근

### `LocalHashEmbeddingFunction`

파일:

* `agent/app/retrieval/vector_store.py`

역할:

* 로컬 해시 기반 임베딩 생성
* 외부 embedding API 없이 retrieval 가능하게 함

### Retrieval 데이터 모델

파일:

* `agent/app/retrieval/schemas.py`

클래스:

* `RetrievalDocument`
* `RetrievalHit`
* `RetrievalContext`

역할:

* 문서 인덱싱과 검색 결과의 스키마 정의

---

## 10. LLM Client 계층

파일:

* `agent/app/services/llm_client.py`

### `BaseLlmClient`

역할:

* provider 공통 인터페이스 정의

### `MockLlmClient`

역할:

* 실제 원격 호출 없이 fallback 경로를 유도

### `OpenAICompatibleClient`

역할:

* OpenAI / OpenAI-compatible `/chat/completions` 호출

### `GeminiClient`

역할:

* Gemini `generateContent` 호출

### 기타 클래스

* `LlmJsonResult`
  * provider / model / payload 묶음
* `LlmError`
  * LLM 계층 공통 예외

중요:

* 이 계층은 외부 모델 호출만 담당한다.
* 게임 상태나 세션 개념은 모른다.

---

## 11. 공용 스키마 계층

파일:

* `agent/app/schemas/common.py`
* `agent/app/schemas/intent.py`
* `agent/app/schemas/narrative.py`

### 공용 스키마

* `ActionType`
* `Action`
* `StateSummary`
* `SceneContext`
* `EngineResult`

### intent 스키마

* `IntentValidationRequest`
* `IntentValidationResponse`

### narrative 스키마

* `NarrativeRequest`
* `NarrativeResponse`

역할:

* 계층 간 request/response 계약 고정
* LLM 출력 JSON 스키마 정의
* game runtime과 agent 계층 사이의 데이터 형식 통일

---

## 12. 요청 흐름 예시

### `POST /game/action`

```
HTTP Request
  -> FastAPI route
  -> AgentRuntime.game.apply_action()
  -> Session lookup
  -> IntenderAgent.handle()
  -> StoryStateManagerAgent.propose()
  -> RuleValidator.validate_transition()
  -> NarratorAgent.render_turn()
  -> HTTP Response
```

세부 흐름:

1. 라우터가 `ActionRequest`를 파싱한다.
2. `GameSessionService`가 세션을 조회한다.
3. `IntenderAgent`가 입력을 action candidate로 정규화한다.
4. `StoryStateManagerAgent`가 scene summary와 state patch 초안을 제안한다.
5. `RuleValidator`가 최종 state, `EngineResult`, allowed choices를 확정한다.
6. `NarratorAgent`가 `state_summary`, `scene_context`, `engine_result`, `allowed_choices` 기반으로 narrative를 생성한다.
7. `ActionResponse`가 반환된다.

---

## 13. 설계 요약

현재 `agent` 아키텍처의 핵심은 다음 세 줄로 정리할 수 있다.

* `AgentRuntime`은 객체를 조립한다.
* `GameSessionService`는 요청 흐름을 오케스트레이션한다.
* `RuleValidator`는 상태 전이의 진실 소스이고, `IntenderAgent` / `StoryStateManagerAgent` / `NarratorAgent`는 제안과 표현 계층이다.
