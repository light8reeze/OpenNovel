# Backend Debug Logging

개발 중 디버그 로그는 환경변수 `NOVEL_GG_DEBUG=1`로 활성화한다.

예시

```bash
NOVEL_GG_DEBUG=1 npm run start:app
```

현재 출력되는 핵심 로그

* `user_input`: 사용자의 원본 입력
* `normalized_action`: 엔진이 해석한 `ActionType`, target, message code
* `gemini_narrative_request`: Gemini narrative 요청 시작
* `gemini_narrative_fallback`: Gemini 실패 후 fallback 전환
* `narrative_generated`: 최종 narrative, choices, source(`Gemini` 또는 `Fallback`)

주의

* Gemini API key 자체는 로그에 출력하지 않는다.
* narrative 텍스트는 길이 제한 후 출력된다.
