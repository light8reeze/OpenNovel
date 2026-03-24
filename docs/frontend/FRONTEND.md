# FRONTEND.md

OpenNovel Frontend Guide

## 1. Overview

현재 `main`의 frontend는 Python `agent` 서버가 정적 파일로 직접 서빙하는 단일 페이지 UI다.

전체 흐름:

```text
User Input
  -> Backend API
  -> StoryAgent
  -> Story Response
  -> UI Update
```

프론트는 다음 역할을 맡는다.
- story log 출력
- choice 버튼 렌더링
- player input 전송
- 상태 패널 표시
- turn graph 표시
- 개발 모드 debug hover 표시

## 2. Stack

현재 구현:

```text
Plain HTML + CSS + Vanilla JavaScript
```

실제 파일:
- [frontend/index.html](/Users/light8reeze/Documents/Projects/OpenNovel/frontend/index.html)
- [frontend/app.js](/Users/light8reeze/Documents/Projects/OpenNovel/frontend/app.js)
- [frontend/styles.css](/Users/light8reeze/Documents/Projects/OpenNovel/frontend/styles.css)

React / TypeScript는 아직 도입되지 않았다.

## 3. Current Layout

```text
+--------------------------------------+---------------------------+
| Story View                           | Game State Panel          |
|                                      | Story Graph               |
| Narrative log                        | Turn Detail               |
+--------------------------------------+---------------------------+
| Choice Buttons / Player Input / Start Controls                |
+---------------------------------------------------------------+
```

현재 주요 UI 요소:
- story setup selector
- Gemini API Key 입력
- 새 세션 시작 버튼
- story log
- choice buttons
- player input form
- state panel
- story graph
- graph hover debug

## 4. Client State

현재 `frontend/app.js`가 관리하는 핵심 상태:
- `sessionId`
- `turnHistory`
- `selectedTurnId`
- `debugUiEnabled`
- `storySetups`
- `selectedStorySetupId`
- Gemini API key 입력값

브라우저 저장:
- `sessionId` -> `localStorage`
- Gemini API key -> `localStorage`
- 선택한 `storySetupId` -> `localStorage`

## 5. Start Flow

앱 로드 시:
1. `GET /health`
2. `GET /story-setups`
3. selector를 story setup 목록으로 채움

사용자가 `새 세션 시작`을 누르면:
1. 선택한 `storySetupId` 읽음
2. 입력된 Gemini key/model을 함께 읽음
3. `POST /game/start`
4. 응답 narrative/state/choices를 초기 화면에 렌더링
5. `turn 0` 노드를 그래프에 추가

## 6. Turn Flow

플레이어는 두 방식으로 턴을 보낼 수 있다.
- 자유 입력
- choice 버튼 클릭

두 경우 모두 최종적으로 `POST /game/action`으로 전송된다.

응답이 오면 프론트는:
- story log에 player / assistant 메시지 추가
- choice 버튼 갱신
- state panel 갱신
- graph에 새 turn node 추가
- detail panel 갱신

## 7. State Panel

현재 `main`의 상태 패널은 compatibility state를 직접 표시한다.

표시 항목:
- `Turn`
- `HP`
- `Gold`
- `Location`
- `Quest Stage`

주의:
- 현재 `Quest Stage`는 `state.quests.sunken_ruins.stage`를 사용한다.
- 위치도 compatibility id를 그대로 출력한다.

## 8. Story Graph and Debug

Story graph:
- `turn 0` opening부터 누적
- 노드 클릭 시 turn detail 표시
- message code와 location을 간단히 표시

개발 모드:
- `OPENNOVEL_DEBUG_UI=true`일 때 활성화
- hover 시 `/debug/turn-log` 호출
- intent / narrative / game 로그를 툴팁과 detail에 표시

## 9. API Usage

현재 프론트가 호출하는 주요 API:

- `GET /health`
- `GET /story-setups`
- `POST /game/start`
- `POST /game/action`
- `GET /game/state`

개발 모드에서 추가:
- `GET /debug/turn-log`

### `/game/start` 요청 예시

```json
{
  "storySetupId": "sunken_ruins",
  "geminiApiKey": "AIza...",
  "geminiModel": "gemini-2.5-flash"
}
```

### `/game/action` 요청 예시

```json
{
  "sessionId": "session-...",
  "inputText": "주변을 조사한다"
}
```

또는

```json
{
  "sessionId": "session-...",
  "choiceText": "회랑으로 이동한다"
}
```

## 10. Current Limitations

현재 `main`의 한계:
- server-driven HTML/JS 구조
- 전체 story log는 새로고침 시 완전 복원되지 않음
- debug UI는 hover 중심의 단순 형태
- streaming / partial response 없음
- mobile 최적화는 제한적

즉 현재 frontend는 `StoryAgent` 기반 single-server UI를 빠르게 확인하고 디버그하기 위한 MVP 구현이다.
