# 구현 로드맵 (MVP 상세)

## 목표
- 문서에 정의된 아키텍처를 실제 코드 구조로 고정한다.
- Core Game Engine을 먼저 완성하고, 그 위에 세션/LLM/API/UI를 순차적으로 올린다.
- 각 단계는 독립적으로 실행 및 검증 가능해야 한다.

## 구현 원칙
- `state`와 `engineResult`만 게임의 진실로 취급한다.
- LLM은 상태 변경, 판정, 이벤트 생성을 하지 않는다.
- 엔진은 결정론적이어야 하며 DB/네트워크/LLM에 의존하지 않는다.
- 각 단계는 "구현 완료"가 아니라 "실행 가능 + 테스트 가능" 상태를 완료 기준으로 삼는다.

## 권장 작업 순서
1. 백엔드 워크스페이스와 도메인 타입 고정
2. 콘텐츠 스키마와 초기 게임 데이터 작성
3. 엔진 규칙/리듀서/CLI 시뮬레이터 구현
4. 저장소와 세션 오케스트레이션 구현
5. LLM 어댑터와 프롬프트 파이프라인 구현
6. HTTP API 구현
7. 프론트엔드 MVP 연결
8. 통합 테스트와 운영 준비 항목 정리

## Phase 0. 저장소 골격 정리
### 목적
- 이후 구현이 흔들리지 않도록 디렉터리와 실행 엔트리를 먼저 확정한다.

### 작업
- `backend/` Cargo workspace 생성
- `backend/crates/{domain,engine,content,narrative,session,storage,api}` 생성
- `content/`와 `prompts/` 디렉터리 생성
- `frontend/` 초기 앱 생성 여부 결정
- 루트 `README` 또는 실행 문서 초안 추가

### 산출물
- 빌드 가능한 Cargo workspace
- crate 간 의존 방향이 정리된 `Cargo.toml`
- 빈 구현이라도 컴파일 가능한 기본 모듈

### 완료 기준
- `cargo check`가 전체 workspace에서 통과
- 실행 엔트리(`api` 또는 `cli`)가 최소 1개 존재

## Phase 1. 도메인 모델 고정
### 목적
- AGENTS.md의 상태 모델과 API 계약을 코드 타입으로 확정한다.

### 작업
- `GameState`, `PlayerState`, `WorldState`, `QuestState`, `RelationsState` 정의
- `ActionType`, `Action`, `Event`, `EngineResult`, `TurnResult` 정의
- 직렬화/역직렬화 규칙 확정
- 테스트용 초기 상태 팩토리 작성
- 프롬프트/UI용 `StateSummary` 생성 함수 작성

### 세부 결정
- 이벤트는 enum + payload struct 조합으로 고정
- `EngineResult.message_code`는 UI/LLM 폴백에서 재사용 가능한 안정 키로 관리
- `choices`는 엔진이 아니라 narrative 계층의 출력으로 유지

### 완료 기준
- 도메인 타입 단위 테스트 통과
- 샘플 상태 JSON round-trip 테스트 통과

## Phase 2. 콘텐츠 스키마 및 초기 시나리오 작성
### 목적
- 엔진이 코드 하드코딩에 묶이지 않도록 게임 데이터를 외부화한다.

### 작업
- `content/locations.json` 작성
- `content/npcs.json` 작성
- `content/quests/murder_case.json` 작성
- 초기 플레이 가능 위치, 조사 포인트, NPC, 퀘스트 stage 정의
- 콘텐츠 로더와 스키마 검증 작성

### 최소 콘텐츠 범위
- 지역 3~5개
- NPC 3명 이상
- 핵심 퀘스트 `murder_case` 1개
- 엔딩 2개 이상

### 완료 기준
- 로더가 모든 콘텐츠를 읽어 `Content` 객체 구성 가능
- 누락 필드/잘못된 참조를 검증하는 테스트 통과

## Phase 3. 엔진 코어 구현
### 목적
- LLM 없이도 게임이 진행되는 최소 플레이 루프를 완성한다.

### 작업
- `reducer::apply_events`
- `rules::resolve`
- `available_actions::list_available_actions`
- seed 기반 RNG 래퍼
- 불가능한 행동 처리 규칙
- 턴 증가, 상태 경계값 보정, 퀘스트 stage 전이 구현

### 우선 지원 액션
- `move`
- `talk`
- `investigate`
- `use_item`
- `rest`
- `flee`

### 엔진 규칙 최소 세트
- 위치 이동 가능 여부 판정
- 조사 성공 시 플래그 또는 단서 획득
- NPC 대화에 따른 affinity 변화
- 퀘스트 stage 조건 충족 시 전이
- HP/Gold/Flags/Inventory 변경

### 검증
- 같은 `seed + state + action` 조합에서 동일 결과 확인
- 경계값 테스트: HP 하한/상한, 중복 플래그, 없는 아이템 사용
- 퀘스트 전이 테스트: `murder_case` stage 0 -> end

### 완료 기준
- CLI에서 텍스트 입력 없이도 predefined action sequence로 엔딩까지 시뮬레이션 가능
- 엔진 테스트 스위트 통과

## Phase 4. CLI 시뮬레이터
### 목적
- API/프론트 없이 밸런스와 로직을 빠르게 검증한다.

### 작업
- `backend/crates/api`와 별도 또는 `backend/bin/cli` 형태로 시뮬레이터 추가
- 현재 상태, 가능한 액션, 엔진 결과, 다음 상태 출력
- 스크립트 가능한 샘플 플레이 로그 저장

### 완료 기준
- 개발자가 CLI로 한 세션을 끝까지 재생 가능
- 회귀 테스트용 샘플 로그 1개 이상 확보

## Phase 5. 저장소와 세션 서비스
### 목적
- 단일 턴 엔진을 세션 단위 게임 플레이로 확장한다.

### 작업
- SQLite 스키마 작성
- `storage` repo trait 및 구현체 작성
- `session` 서비스에서 시작/행동/상태조회 파이프라인 작성
- 로그 저장 및 memory summary 필드 보관
- LLM 없는 mock narrative 생성 경로 제공

### 세션 파이프라인
1. 세션 생성
2. 초기 상태 적재
3. 사용자 입력 수신
4. intent 결과 또는 mock action 적용
5. 엔진 실행
6. 상태/로그 저장
7. 응답 DTO 반환

### 완료 기준
- SQLite 기반으로 세션 생성 후 여러 턴 진행 가능
- 서버 없이 세션 서비스 단위 테스트 통과

## Phase 6. LLM 연동
### 목적
- 문서에 정의된 세 가지 프롬프트를 실제 파이프라인에 붙인다.

### 작업
- `prompts/intent.*`, `prompts/narrative.*`, `prompts/memory_summary.*` 작성
- `LlmClient` trait와 provider adapter 작성
- Intent Parsing JSON 스키마 정의
- Narrative JSON 스키마 정의
- JSON 검증 실패 시 재시도 및 폴백 로직 구현

### 폴백 전략
- intent 실패 시 안전한 기본 액션 또는 시스템 메시지 반환
- narrative 실패 시 `message_code` 기반 고정 문장 생성
- choices 실패 시 `available_actions` 기반 버튼 텍스트 생성

### 완료 기준
- mock LLM과 실제 provider adapter를 교체 가능한 구조
- LLM 실패 상황에서도 턴 진행이 멈추지 않음

## Phase 7. HTTP API 구현
### 목적
- 프론트엔드와 연결 가능한 안정 API를 제공한다.

### 작업
- `POST /game/start`
- `POST /game/action`
- `GET /game/state`
- request/response DTO 검증
- tracing, request id, 에러 매핑
- CORS 설정

### 세부 기준
- `POST /game/action`은 `inputText`와 `choiceText`가 동시에 오면 400
- 존재하지 않는 세션은 404
- 내부 예외는 사용자에게 안전한 메시지로 변환

### 완료 기준
- API 스모크 테스트 통과
- curl 또는 HTTP 클라이언트로 전체 게임 루프 재현 가능

## Phase 8. 프론트엔드 MVP
### 목적
- 문서에 정의된 채팅형 플레이 UI를 최소 기능으로 구현한다.

### 작업
- `frontend/` 앱 생성
- Chat log, input box, choice buttons, game state panel 구현
- `services/apiClient` 작성
- `store/gameStore` 또는 동등 상태 관리 구현
- 세션 시작/행동 전송/상태 반영 연결

### 화면 최소 요구사항
- AI narrative 출력
- 플레이어 입력 전송
- 선택지 버튼 클릭
- 현재 HP, 위치, 퀘스트 stage 표시
- 로딩/에러 상태 처리

### 완료 기준
- 브라우저에서 첫 세션 시작 후 3턴 이상 정상 진행 가능
- 새로고침 후 `sessionId` 복원 전략이 정의됨

## Phase 9. 통합 검증 및 안정화
### 목적
- MVP를 실제 배포 전 수준으로 정리한다.

### 작업
- 엔진/세션/API/프론트 기본 회귀 시나리오 작성
- 프롬프트 버전 관리 규칙 정리
- 에러 로그와 관측성 최소 세팅
- 샘플 환경변수 문서화
- 로컬 개발 실행 절차 문서화

### 테스트 체크리스트
- 엔진 결정론 테스트
- 세션 저장/복원 테스트
- LLM JSON 파싱 실패 테스트
- API 계약 테스트
- 프론트 기본 사용자 흐름 테스트

### 완료 기준
- 신규 개발자가 문서만 보고 로컬에서 실행 가능
- MVP 데모 시나리오가 문서화되어 있음

## 추천 구현 단위
### 1주차
- Phase 0
- Phase 1
- Phase 2 일부

### 2주차
- Phase 2 마무리
- Phase 3
- Phase 4

### 3주차
- Phase 5
- Phase 6 일부

### 4주차
- Phase 6 마무리
- Phase 7
- Phase 8 최소 연결

### 5주차
- Phase 9
- 버그 수정 및 데모 준비

## 선행 리스크
- 프롬프트 설계보다 엔진 규칙 정의가 늦어질 가능성
- 콘텐츠 스키마가 흔들리면 엔진/LLM/API 타입이 같이 흔들릴 가능성
- 프론트를 먼저 만들면 엔진 계약이 자주 바뀌어 재작업이 커질 가능성

## 우선순위 결론
- 가장 먼저 확정할 것은 `GameState`, `Event`, `EngineResult`, 콘텐츠 스키마다.
- 그 다음은 엔진과 CLI다.
- LLM과 프론트는 엔진/세션 계약이 굳은 뒤 붙이는 것이 맞다.
