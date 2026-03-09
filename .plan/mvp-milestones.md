# MVP 마일스톤 (Rust)

상세 구현 순서, 산출물, 완료 기준은 `implementation-roadmap.md`를 기준으로 진행한다.

## M1: 엔진 단독 실행(LLM/DB 없음)
- domain/engine/content 최소 구현 + CLI 시뮬레이터
- 퀘스트 1개(`murder_case`)를 stage 0→end까지 진행 가능

## M2: 저장소 + 세션 서비스
- SQLite storage + session 파이프라인(LLM mock)

## M3: LLM 연동
- intent/narrative 프롬프트 + JSON 검증 + 폴백

## M4: API + 프론트 연결
- axum API 3개 완성, 프론트 Chat UI에서 플레이 가능
