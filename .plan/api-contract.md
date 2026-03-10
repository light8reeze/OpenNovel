# API 계약 (MVP)

## POST /game/start
Response
```json
{
  "sessionId": "...",
  "narrative": "...",
  "choices": ["..."],
  "state": { "meta": {"turn": 0, "seed": 123}, "player": {}, "world": {}, "quests": {}, "relations": {} }
}
```

## POST /game/action
Request (텍스트 입력)
```json
{ "sessionId": "...", "inputText": "창고 문을 조사한다" }
```
Request (버튼 선택)
```json
{ "sessionId": "...", "choiceText": "문을 열어 안을 살핀다" }
```
Response
```json
{
  "narrative": "...",
  "choices": ["..."],
  "engineResult": { "success": true, "messageCode": "INVESTIGATE_OK" },
  "state": { "meta": {"turn": 1, "seed": 123}, "player": {}, "world": {}, "quests": {}, "relations": {} }
}
```

## GET /game/state?sessionId=...
Response
```json
{ "state": { } }
```

## 서버 규칙
- LLM 출력은 반드시 JSON 파싱 후 사용하며 실패 시 폴백한다.
- `engineResult`와 `state`가 진실이며, narrative/choices는 표현이다.
