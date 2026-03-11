# OpenNovel Agent

`agent`는 OpenNovel backend와 분리된 Python + LangGraph 서비스다.

현재 포함 범위:

- `POST /intent/validate`
- `POST /narrative/opening`
- `POST /narrative/turn`
- `GET /health`

지원 provider:

- `mock`
- `openai`
- `openai_compatible`
- `gemini`

원칙:

- backend가 게임 상태와 판정을 소유한다.
- agent는 입력 의도 검증과 narrative 표현만 담당한다.
- agent는 상태를 변경하지 않는다.

실행 예시:

```bash
uvicorn app.main:app --reload --app-dir agent
```

환경 변수:

```bash
export AGENT_LLM_PROVIDER=openai
export AGENT_LLM_MODEL=gpt-4.1-mini
export AGENT_LLM_API_KEY=...
```

OpenAI 호환 provider를 붙일 때는 다음처럼 base URL을 바꾼다.

```bash
export AGENT_LLM_PROVIDER=openai_compatible
export AGENT_LLM_BASE_URL=https://your-provider.example/v1
export AGENT_LLM_MODEL=your-model-name
export AGENT_LLM_API_KEY=...
```

Gemini를 붙일 때는 다음처럼 설정한다.

```bash
export AGENT_LLM_PROVIDER=gemini
export AGENT_LLM_MODEL=gemini-2.5-flash
export AGENT_LLM_API_KEY=...
```
