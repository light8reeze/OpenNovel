# Agent Integration

현재 `agent`는 OpenNovel의 공식 단일 서버이며, 내부적으로 다음 LLM 계층 계약을 사용한다.

- `POST /intent/validate`
- `POST /narrative/opening`
- `POST /narrative/turn`

원칙:

- `RuleValidator`가 상태와 판정의 진실 소스다.
- `StoryStateManagerAgent`는 scene summary, state patch, discovered facts, choice 후보를 제안한다.
- `IntenderAgent`는 플레이어 입력을 action candidate로 정규화한다.
- `NarratorAgent`는 validator result를 narrative로 표현한다.
- game runtime은 agent 응답을 그대로 신뢰하지 않고 최종 검증한다.

LLM 호출 실패 시 game runtime은 기존 heuristic/template 경로로 fallback한다.
