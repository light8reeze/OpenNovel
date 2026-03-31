# OpenNovel Agent

`agent`는 OpenNovel의 공식 단일 서비스다.

현재 구조:

- `IntenderAgent`: 플레이어 입력을 action type으로 정규화
- `StoryStateManagerAgent`: scene summary와 state patch 초안 제안
- `RuleValidator`: theme rules, style scoring, objective/victory truth 소유
- `NarratorAgent`: validator result를 narrative/choices로 표현
- `WorldBuilderAgent`: story setup을 world blueprint로 확장
- `GameSessionService`: 세션 관리, `/game/*` 오케스트레이션
- `Chroma`: role별 retrieval 문서 저장소

현재 포함 범위:

- `GET /`
- `GET /frontend/app.js`
- `GET /frontend/styles.css`
- `POST /game/start`
- `POST /game/action`
- `GET /game/state`
- `POST /intent/validate`
- `POST /narrative/opening`
- `POST /narrative/turn`
- `GET /health`

role별 지원 provider:

- `mock`
- `openai`
- `openai_compatible`
- `gemini`

원칙:

- agent 내부 validator/runtime이 게임 상태와 판정을 소유한다.
- agent는 입력 의도 검증과 narrative 표현을 같은 서비스 안에서 호출한다.
- LLM 계층은 상태를 직접 변경하지 않는다.

정확히는 상태 전이는 `GameSessionService`와 `RuleValidator`가 담당한다.

실행 예시:

```bash
uvicorn app.main:app --reload --app-dir agent
```

권장 실행:

```bash
PYTHONPATH=agent uvicorn app.main:app --reload --app-dir agent
```

환경 변수는 role별로 분리된다.

```bash
export AGENT_VECTOR_DB_PROVIDER=chroma
export AGENT_VECTOR_DB_PATH=.chroma

export AGENT_INTENDER_PROVIDER=openai
export AGENT_INTENDER_MODEL=gpt-4.1-mini
export AGENT_INTENDER_API_KEY=...

export AGENT_NARRATOR_PROVIDER=gemini
export AGENT_NARRATOR_MODEL=gemini-2.5-flash
export AGENT_NARRATOR_API_KEY=...
```

OpenAI 호환 provider를 role별로 붙일 수도 있다.

```bash
export AGENT_INTENDER_PROVIDER=openai_compatible
export AGENT_INTENDER_BASE_URL=https://your-provider.example/v1
export AGENT_INTENDER_MODEL=your-model-name
export AGENT_INTENDER_API_KEY=...
```

Chroma는 startup 시 `agent/content/intender_docs`, `agent/content/narrator_docs`를 자동 인덱싱한다.

게임 콘텐츠는 루트 `content/` 디렉터리에서 읽는다.

현재 `Phase 1`에서는 추가로 다음 데이터가 포함된다.

- `content/theme_packs.json`
