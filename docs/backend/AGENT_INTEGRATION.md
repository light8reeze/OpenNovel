# Agent Integration

현재 backend는 외부 `agent` 서비스와 다음 계약으로 통신한다.

- `POST /intent/validate`
- `POST /narrative/opening`
- `POST /narrative/turn`

원칙:

- backend/engine이 상태와 판정의 진실 소스다.
- `IntenderAgent`는 플레이어 입력을 action candidate로 정규화한다.
- `NarratorAgent`는 engine result를 narrative로 표현한다.
- backend는 agent 응답을 그대로 신뢰하지 않고 최종 검증한다.

환경 변수:

```bash
export NOVEL_AGENT_BASE_URL=http://127.0.0.1:8000
```

agent 응답 실패 시 backend는 기존 heuristic/template 경로로 fallback한다.
