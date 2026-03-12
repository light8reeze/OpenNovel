## OpenNovel Running And Logging

이 문서는 현재 저장소에서 구현된 단일 `agent` 실행 방식과 로그 구조를 정리한다.

### 현재 구성

- Python agent
  - `GET /`
  - `GET /frontend/app.js`
  - `GET /frontend/styles.css`
  - `POST /game/start`
  - `POST /game/action`
  - `GET /game/state`
  - `GET /health`
  - `POST /intent/validate`
  - `POST /narrative/opening`
  - `POST /narrative/turn`

기본 포트:

- agent: `127.0.0.1:8000`

### 현재 동작 방식

agent 내부 game runtime이 게임 상태와 판정을 소유한다.

- action 판정
- state 변경
- event 처리
- quest 진행

agent 내부 LLM 계층은 표현과 입력 보조를 담당한다.

- intent validation
- opening narrative 생성
- turn narrative 생성

LLM 호출에 실패하면 agent는 fallback 경로를 사용한다.

- intent: heuristic fallback
- narrative: template 또는 기존 Gemini 기반 fallback

### Agent 프로젝트 구조

agent는 Python 프로젝트이며 FastAPI 기반으로 구성되어 있다.

주요 디렉터리:

- `agent/app/main.py`
  - FastAPI app 진입점
- `agent/app/api/routes.py`
  - HTTP 라우트 정의
- `agent/app/config.py`
  - `.env` 로딩 및 환경 변수 파싱
- `agent/app/graph/`
  - intent / narrative 워크플로 정의
- `agent/app/prompts/`
  - system rules, intent prompt, narrative prompt 구성
- `agent/app/schemas/`
  - request / response 스키마
- `agent/app/services/llm_client.py`
  - provider별 LLM 호출
- `agent/app/services/fallback_renderer.py`
  - fallback narrative 생성
- `agent/app/game/`
  - deterministic engine, session service, game API 모델
- `agent/app/services/file_logger.py`
  - agent JSONL 파일 로그 기록
- `agent/tests/test_workflows.py`
  - 기본 API / workflow 테스트

### Agent 엔드포인트

- `GET /health`
  - 현재 provider / model / API key 설정 여부 확인
- `POST /intent/validate`
  - game runtime이 보낸 플레이어 입력을 intent로 정규화
- `POST /narrative/opening`
  - 게임 시작 시 opening narrative 생성
- `POST /narrative/turn`
  - 각 turn의 narrative 생성

### Agent 내부 워크플로

#### intent workflow

순서:

1. request 기반으로 intent prompt 생성
2. LLM에 JSON 출력 요청
3. 응답 파싱
4. 실패 시 heuristic fallback 적용
5. 허용 action / visible target 기준으로 validation

현재 heuristic fallback 예시는 다음을 포함한다.

- `창고`, `warehouse` → `MOVE`
- `아리아`, `talk` → `TALK`
- `휴식` → `REST`
- `횃불` → `USE_ITEM`
- 그 외 기본값 → `INVESTIGATE`

#### narrative workflow

순서:

1. kind(`opening` 또는 `turn`)에 맞는 prompt 생성
2. LLM에 JSON 출력 요청
3. 응답 파싱
4. 실패 시 fallback narrative 생성
5. allowed choices 기준으로 choice filtering
6. choice 개수나 narrative 본문이 유효하지 않으면 fallback으로 대체

현재 validation 규칙:

- choice는 allowed choices 안에 있어야 한다.
- choice는 최대 4개만 유지한다.
- 최소 2개 이상이어야 한다.
- narrative 본문이 비어 있으면 invalid 처리한다.

### Agent LLM provider 처리

현재 provider:

- `mock`
- `openai`
- `openai_compatible`
- `gemini`

구현 방식:

- OpenAI 계열은 `/chat/completions` 호출
- Gemini는 `:generateContent` 호출
- 응답은 JSON schema 또는 JSON 텍스트로 받아 파싱
- HTTP 실패 / 응답 shape 오류 / JSON parse 오류는 `LlmError`로 처리

### Agent fallback 동작

intent fallback:

- LLM 실패 시 heuristic intent 결과 반환
- 실패 원인을 `validation_flags`에 `llm_error:...` 형태로 기록

narrative fallback:

- LLM 실패 시 template/fallback narrative 사용
- 실패 원인을 `safety_flags`에 `llm_error:...` 형태로 기록
- invalid response도 fallback으로 치환

### Agent 테스트 범위

현재 테스트 파일:

- `agent/tests/test_workflows.py`

포함 테스트:

- `/health` 응답 확인
- `/intent/validate`가 action을 반환하는지 확인
- `/narrative/turn`이 allowed choices 기반 응답을 반환하는지 확인

### 환경 변수

#### agent

- `AGENT_INTENDER_PROVIDER`
- `AGENT_INTENDER_MODEL`
- `AGENT_INTENDER_BASE_URL`
- `AGENT_INTENDER_API_KEY`
- `AGENT_NARRATOR_PROVIDER`
- `AGENT_NARRATOR_MODEL`
- `AGENT_NARRATOR_BASE_URL`
- `AGENT_NARRATOR_API_KEY`
- `AGENT_VECTOR_DB_PROVIDER`
- `AGENT_VECTOR_DB_PATH`

`.env` 자동 로딩이 구현되어 있으므로 `agent/.env`를 사용하면 된다.

### 실행 스크립트

#### 일반 실행

```bash
./scripts/start-app.sh
```

동작:

- agent를 시작
- 실행 시점 기준 `RUN_ID`를 생성
- process 로그를 `log/` 아래에 실행별 파일로 저장
- `OPENNOVEL_RUN_ID`를 agent에 전달

#### 디버그 실행

```bash
./scripts/start-debug.sh
```

동작:

- agent를 시작
- agent는 `--reload`
- process 로그를 `log/` 아래에 실행별 파일로 저장
- 콘솔에는 agent 로그 파일을 `tail -f`로 출력

#### 종료

```bash
./scripts/stop-app.sh
```

동작:

- `log/agent.pid`
를 읽어 프로세스를 종료한다.

### npm scripts

```bash
npm run start:app
npm run start:debug
npm run stop:app
```

### 로그 디렉터리 구조

모든 실행 로그는 `log/` 아래에 남는다.

#### process 로그

실행별 파일:

- `log/agent.app.<run-id>.log`
- `log/agent.debug.<run-id>.log`

#### agent JSONL 로그

고정 파일:

- `log/agent/backend-requests.jsonl`
- `log/agent/intent-results.jsonl`
- `log/agent/narrative-results.jsonl`
- `log/agent/game-results.jsonl`

의미:

- `backend-requests.jsonl`
  - HTTP 요청 원문
- `intent-results.jsonl`
  - intent 분석 결과
- `narrative-results.jsonl`
  - opening/turn narrative 결과
- `game-results.jsonl`
  - `/game/*` 응답 결과

각 항목에는 현재 다음 정보가 포함된다.

- `ts`
- `ts_unix_ms`
- `service`
- `kind`
- `endpoint`
- `payload` 또는 `request`/`response`

#### 통합 실행 로그

실행별 파일:

- `log/combined/run-<run-id>.jsonl`

의미:

- agent의 JSON 이벤트를 한 파일에 함께 남긴다.
- run id 기준으로 한 번의 실행 세션을 묶어 볼 수 있다.

현재 통합 로그에는 다음 source가 함께 들어간다.

- game request/result
- intent request/result
- narrative request/result

### 현재 구현된 파일 로깅 특성

- 개별 로그 파일은 누적 append 방식이다.
- 통합 로그는 실행 단위 파일 분리 방식이다.
- `service` 필드는 현재 `agent`로 기록된다.
- `/game/start` 요청 로그는 `geminiApiKey` 원문을 남기지 않도록 처리하는 것이 권장된다.

### 현재 확인된 운영 흐름

1. `start-app.sh` 또는 `start-debug.sh` 실행
2. agent 기동
3. `/game/*` 또는 내부 LLM 엔드포인트 요청 처리
4. agent 개별 JSONL 로그 기록
5. 동시에 `log/combined/run-<run-id>.jsonl`에도 통합 기록

### 관련 파일

- `agent/README.md`
- `docs/backend/DEBUGGING.md`
- `scripts/start-app.sh`
- `scripts/start-debug.sh`
- `scripts/stop-app.sh`
