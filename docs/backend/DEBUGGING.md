# Backend Debug Logging

현재 backend는 Python `agent` 단일 서비스다. 별도의 Rust debug 플래그는 없다.

실행 예시

```bash
PYTHONPATH=agent OPENNOVEL_RUN_ID=$(date +%Y%m%d-%H%M%S) \
agent/.venv/bin/uvicorn app.main:app --app-dir agent --host 127.0.0.1 --port 8000
```

현재 확인하는 핵심 로그

* `log/agent/backend-requests.jsonl`: HTTP 요청 로그
* `log/agent/intent-results.jsonl`: intent 결과 로그
* `log/agent/narrative-results.jsonl`: narrative 결과 로그
* `log/agent/game-results.jsonl`: `/game/*` 응답 로그
* `log/agent/llm-errors.jsonl`: provider 호출/파싱 실패 로그
* `log/combined/run-<run-id>.jsonl`: 전체 로그 통합 파일
* 개발 모드에서는 `GET /debug/turn-log?sessionId=...&turn=...`로 turn 단위 bundle 조회 가능

주의

* API key 원문은 로그에 남기지 않는 것을 원칙으로 한다.
* JSONL 로그는 append 방식이므로 디버깅 시 run id와 timestamp를 함께 본다.
* `GET /debug/turn-log`는 개발 모드에서만 활성화된다.
* turn bundle은 `sessionId + turn` 기준으로 `game`, `intent`, `narrative` 로그를 묶어 반환한다.
