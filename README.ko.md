# OpenNovel

언어: [English](./README.md) | [한국어](./README.ko.md)

OpenNovel은 AI 기반 인터랙티브 소설 게임입니다.  
현재 `main` 브랜치는 Python 단일 서버가 백엔드 API와 브라우저 UI를 함께 제공하는 형태로 동작합니다.

런타임에서는 소규모 story setup preset으로 세션을 시작하고, `StoryAgent`가 다음 장면, 선택지, 경량 compatibility state snapshot을 생성합니다.

## 현재 아키텍처

상위 흐름:

```text
플레이어 입력
  -> FastAPI 서버
  -> GameSessionService
  -> StoryAgent
  -> 내러티브 / 선택지 / 상태 스냅샷
  -> UI 갱신
```

현재 구현 요소:
- 공식 런타임인 Python `agent` 서비스
- startup 시 3개의 story preset을 생성하거나 fallback으로 채우는 `StorySetupAgent`
- `/game/*` 경로의 진행을 담당하는 `StoryAgent`
- compatibility endpoint용 `IntenderAgent`, `NarratorAgent`
- 메모리 기반 세션 저장
- Chroma 기반 retrieval
- 동일 서버에서 서빙되는 정적 frontend
- 채팅 UI, 턴 그래프, 디버그 turn-log 도구

현재 한계:
- 영속 데이터베이스 없음
- streaming 응답 없음
- React/TypeScript frontend 없음
- `main`의 compatibility state에는 아직 `quests.sunken_ruins.stage` 같은 예전 필드명이 남아 있음

## 저장소 구조

```text
agent/        Python 런타임, API, agent, prompt, retrieval
frontend/     HTML, CSS, Vanilla JS 클라이언트
content/      런타임이 읽는 정적 콘텐츠
docs/         백엔드/프론트엔드 문서
```

관련 문서:
- [AGENTS.md](./AGENTS.md)
- [docs/backend/BACKEND.md](./docs/backend/BACKEND.md)
- [docs/frontend/FRONTEND.md](./docs/frontend/FRONTEND.md)
- [agent/README.md](./agent/README.md)

## 요구 사항

- Python `>=3.9`
- `agent/`용 가상환경
- live Gemini narrative 생성을 원할 경우 Gemini API 키

## 빠른 시작

1. `agent/` 안에 가상환경을 만듭니다.
2. 의존성을 설치합니다.
3. `agent/.env.example`를 복사하거나 참고해서 환경 변수를 준비합니다.
4. FastAPI 서버를 실행합니다.

예시:

```bash
cd path/to/OpenNovel/agent
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -e ".[dev]"
```

그 다음 저장소 루트에서 실행합니다.

```bash
cd path/to/OpenNovel
PYTHONPATH=agent agent/.venv/bin/uvicorn app.main:app --app-dir agent --host 127.0.0.1 --port 8000
```

브라우저:

```text
http://127.0.0.1:8000
```

## 환경 변수

기본 예시는 `agent/.env.example`에 있습니다. 현재 런타임은 role별 LLM 설정을 지원합니다.

공통 설정 예시:

```bash
AGENT_VECTOR_DB_PROVIDER=chroma
AGENT_VECTOR_DB_PATH=.chroma
AGENT_VECTOR_AUTO_INDEX=true

AGENT_INTENDER_PROVIDER=mock
AGENT_INTENDER_MODEL=gpt-4.1-mini
AGENT_INTENDER_TIMEOUT_SECONDS=180

AGENT_NARRATOR_PROVIDER=mock
AGENT_NARRATOR_MODEL=gpt-4.1-mini
AGENT_NARRATOR_TIMEOUT_SECONDS=180
```

서버 측 Gemini 사용 예시:

```bash
AGENT_INTENDER_PROVIDER=gemini
AGENT_INTENDER_MODEL=gemini-2.5-flash
AGENT_INTENDER_API_KEY=...

AGENT_NARRATOR_PROVIDER=gemini
AGENT_NARRATOR_MODEL=gemini-2.5-flash
AGENT_NARRATOR_API_KEY=...
```

브라우저 UI에서도 세션 시작 시 Gemini 키를 따로 입력할 수 있습니다.

## 주요 API

런타임 엔드포인트:
- `GET /`
- `GET /health`
- `GET /story-setups`
- `POST /game/start`
- `POST /game/action`
- `GET /game/state`

호환 / 디버그 엔드포인트:
- `GET /debug/turn-log`
- `POST /intent/validate`
- `POST /narrative/opening`
- `POST /narrative/turn`

시작 요청 예시:

```json
{
  "storySetupId": "sunken_ruins",
  "geminiApiKey": "AIza...",
  "geminiModel": "gemini-2.5-flash"
}
```

액션 요청 예시:

```json
{
  "sessionId": "session-...",
  "inputText": "주변을 조사한다"
}
```

## 프론트엔드

현재 프론트엔드는 HTML, CSS, JavaScript만으로 구성된 단일 페이지 앱입니다.

주요 UI 요소:
- story setup selector
- Gemini API Key 입력
- 새 세션 시작 버튼
- story log
- choice buttons
- 자유 입력창
- state panel
- turn graph
- debug hover panel

## 디버깅

로컬 디버깅 시 debug UI를 켜고 turn 단위 bundle을 확인할 수 있습니다.

```bash
PYTHONPATH=agent \
OPENNOVEL_DEBUG_UI=true \
agent/.venv/bin/uvicorn app.main:app --app-dir agent --host 127.0.0.1 --port 8000
```

유용한 확인 명령:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/story-setups
curl "http://127.0.0.1:8000/debug/turn-log?sessionId=SESSION_ID&turn=0"
```

로그 위치:
- `log/agent/backend-requests.jsonl`
- `log/agent/intent-results.jsonl`
- `log/agent/narrative-results.jsonl`
- `log/agent/game-results.jsonl`
- `log/agent/llm-errors.jsonl`

## 테스트

백엔드 테스트:

```bash
cd path/to/OpenNovel
PYTHONPATH=agent agent/.venv/bin/pytest agent/tests
```

기본 정적 검사:

```bash
python3 -m compileall agent/app frontend
node --check frontend/app.js
```

## 현재 상태

이 저장소는 아직 MVP 중심 코드베이스입니다. 현재 `main` 브랜치는 아래를 우선합니다.
- story runtime 동작의 빠른 실험
- 예전 intent/narrative endpoint와의 compatibility 유지
- 로컬 디버깅 가시성 확보

아직 최종 아키텍처 안정성을 목표로 하지는 않습니다.
