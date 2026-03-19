# FRONTEND.md

OpenNovel – Frontend Development Guide

---

# 1. 프로젝트 개요

OpenNovel은 **플레이어가 소설 속 주인공이 되어 이야기를 진행하는 텍스트 기반 게임 서비스**이다.

사용자는 채팅 인터페이스를 통해 행동을 입력하고, AI는 스토리 진행 및 세계 상태를 기반으로 다음 장면을 생성한다.

현재 구현 기준 전체 흐름은 다음과 같다.

```
User Input → Backend API → Game Engine → LLM → Story Response → UI
```

프론트엔드는 **채팅 기반 인터페이스, 턴 누적 스토리 그래프, 게임 상태 시각화**를 담당한다.

---

# 2. MVP 목표

프론트엔드 MVP 목표:

1. 채팅 기반 인터페이스 제공
2. 플레이어 입력 처리
3. AI 응답 출력
4. 간단한 게임 상태 표시
5. 턴 누적 스토리 그래프 표시
6. 개발 모드용 hover 디버그 로그 확인

초기 버전에서는 다음 기능은 제외한다.

* 멀티플레이
* 복잡한 UI
* 그래픽 렌더링
* 실시간 동기화

---
# 3. 프론트엔드 기술 스택

현재 구현 선택

```
Plain HTML + CSS + Vanilla JavaScript
```

설명

* Python `agent` 서버가 정적 파일을 직접 서빙한다.
* 프론트는 `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`로 구성된다.
* React / Next.js 구조는 아직 도입되지 않았다.

---

# 4. 현재 구조

```
frontend/
  index.html
  app.js
  styles.css
```

---

# 5. UI 구조

## 5.1 Game Layout

기본 레이아웃

```
+--------------------------------------+---------------------------+
|           Story View                 |      Game State Panel     |
|                                      |      Story Graph          |
|  AI가 생성한 소설 내용 표시          |      Turn Detail          |
|                                      |                           |
+--------------------------------------+---------------------------+
| Player Input                        |
| [________________________________]  |
|             [Send]                  |
+--------------------------------------+
```

추가 설명

* `Story Graph`는 turn 단위 노드를 시간순으로 누적한다.
* 노드를 클릭하면 `Turn Detail` 패널에 해당 턴 narrative와 state 요약이 표시된다.
* 개발 모드에서는 노드 hover 시 request/response debug 로그를 확인할 수 있다.

---

# 6. 주요 컴포넌트

## InputBox

플레이어 입력 UI

기능

* 사용자 행동 입력
* Enter 입력 전송
* loading 상태 표시

예시

```
> 문을 열고 방 안을 조사한다
```

현재 구현 추가 사항

* 헤더에 Gemini API Key 입력 필드가 존재한다.
* 새 세션 시작 시 API 키를 `POST /game/start`로 전달한다.
* 입력한 키는 브라우저 `localStorage`에 저장된다.
* 입력 또는 choice 선택이 끝날 때마다 그래프에 새 turn node가 추가된다.

---

## StoryView

스토리 텍스트 출력

기능

* AI 생성 텍스트 출력
* 이전 스토리 히스토리
* 스크롤 관리

---

## StoryGraph

턴 누적 흐름도 출력

기능

* `turn 0` opening 노드 생성
* 이후 `/game/action` 응답마다 새 노드 누적
* 현재 턴 강조 표시
* 노드 클릭 시 detail 패널 갱신
* 개발 모드에서 hover debug 조회

---

## GameStatePanel

게임 상태 표시

```
HP: 100
Location: Castle
Inventory:
- Sword
- Potion
```

---

# 7. 상태 관리

현재 frontend는 프레임워크 store 없이 브라우저 메모리와 `localStorage`를 함께 사용한다.

주요 클라이언트 상태

* `sessionId`
* `turnHistory`
* `selectedTurnId`
* `debugUiEnabled`
* Gemini API 키 입력값

저장 방식

* `sessionId`는 `localStorage`에 저장된다.
* Gemini API 키도 `localStorage`에 저장된다.
* 새로고침 시 `GET /game/state`로 현재 상태 패널은 복원되지만, 전체 스토리 로그는 다시 구성하지 않는다.

---

# 8. API 통신

Game API

```
POST /game/start
POST /game/action
GET  /game/state
```

현재 구현 세부

### `POST /game/start`

요청 body는 비어 있을 수도 있고, 다음 필드를 포함할 수도 있다.

```json
{
  "geminiApiKey": "AIza...",
  "geminiModel": "gemini-2.5-flash"
}
```

### `POST /game/action`

현재 frontend는 자유 입력과 choice 버튼 둘 다 같은 API에 전달한다.

```json
{
  "sessionId": "...",
  "inputText": "주변을 조사한다"
}
```

또는

```json
{
  "sessionId": "...",
  "choiceText": "회랑으로 이동한다"
}
```

---

## Start Game

```
POST /game/start
```

Response

```
{
  sessionId,
  narrative,
  choices,
  state
}
```

---

## Player Action

```
POST /game/action
```

Request

```
{
  sessionId,
  inputText: "open the door"
}
```

Response

```
{
  narrative,
  choices,
  engineResult,
  state
}
```

---

# 9. 게임 흐름

전체 흐름

```
1 User enters action
2 Frontend sends API request
3 Agent game runtime updates state
4 Agent narrator generates story
5 Response returned
6 UI updates
```

현재 frontend 동작

* 최초 로드 시 `localStorage`의 `sessionId`를 확인한다.
* 최초 로드 시 `GET /health`로 debug UI 사용 가능 여부를 먼저 확인한다.
* 세션이 있으면 `GET /game/state`로 상태를 복원한다.
* 세션이 없으면 새 세션을 시작한다.
* 선택지 버튼 또는 직접 입력을 `POST /game/action`으로 전송한다.
* 응답의 `narrative`, `choices`, `state`로 화면을 갱신한다.
* turn 응답은 동시에 그래프 노드로 누적된다.
* 개발 모드에서는 노드 hover 시 `GET /debug/turn-log`를 조회한다.

주의

* 현재 message history 전체를 서버에서 복구하지는 않는다.
* 새로고침 시 상태 패널은 복원되지만, 전체 스토리 로그는 재생성되지 않는다.

---

# 10. UX 원칙

1. **채팅 중심 인터페이스**
2. **텍스트 가독성 최우선**
3. **스토리 몰입 유지**
4. **빠른 입력 가능**

---

# 11. 향후 확장

추후 기능

### Streaming Response

LLM streaming 출력

```
AI typing...
```

---

### 선택지 기반 플레이

```
1. 문을 연다
2. 창문을 조사한다
3. 뒤로 돌아간다
```

---

### 캐릭터 UI

```
Portrait
Emotion
Dialogue
```

---

### 세이브 시스템

```
Save Slot
Load Game
```

---

# 12. Codex 작업 규칙

AI agent (Codex)가 작업할 때 규칙

* TypeScript strict mode 사용
* 모든 컴포넌트는 함수형
* 상태는 store로 관리
* API 로직은 services 폴더에 작성
* UI 로직과 API 로직 분리

---

# 13. MVP 개발 순서

1️⃣ Chat UI 구현
2️⃣ API 연결
3️⃣ 게임 상태 표시
4️⃣ 세션 관리
5️⃣ 스토리 렌더링 개선

---

# 14. 개발 우선순위

Priority 1

* Chat UI
* Input
* API call

Priority 2

* Game state panel
* Session persistence

Priority 3

* Streaming response
* UI polish
