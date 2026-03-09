# FRONTEND.md

AI Novel Player – Frontend Development Guide

---

# 1. 프로젝트 개요

AI Novel Player는 **플레이어가 소설 속 주인공이 되어 이야기를 진행하는 텍스트 기반 게임 서비스**이다.

사용자는 채팅 인터페이스를 통해 행동을 입력하고, AI는 스토리 진행 및 세계 상태를 기반으로 다음 장면을 생성한다.

초기 MVP 단계에서는 다음과 같은 구조를 가진다.

```
User Input → Backend API → Game Engine → LLM → Story Response → UI
```

프론트엔드는 **채팅 기반 인터페이스와 게임 상태 시각화**를 담당한다.

---

# 2. MVP 목표

프론트엔드 MVP 목표:

1. 채팅 기반 인터페이스 제공
2. 플레이어 입력 처리
3. AI 응답 출력
4. 간단한 게임 상태 표시
5. 세션 기반 플레이 유지

초기 버전에서는 다음 기능은 제외한다.

* 멀티플레이
* 복잡한 UI
* 그래픽 렌더링
* 실시간 동기화

---

# 3. 프론트엔드 기술 스택

추천 스택

```
Framework: React / Next.js
Language: TypeScript
State Management: Zustand or Redux
Styling: TailwindCSS
Chat Rendering: React Markdown
Networking: Fetch / Axios
```

선택 이유

* React 기반 채팅 UI 구현 용이
* 상태 관리 확장성
* LLM 텍스트 렌더링 편리

---

# 4. 전체 아키텍처

```
frontend/
│
├─ components/
│  ├─ Chat
│  ├─ StoryView
│  ├─ InputBox
│  └─ GameStatePanel
│
├─ pages/
│  └─ GamePage
│
├─ hooks/
│  └─ useGameSession
│
├─ store/
│  └─ gameStore
│
├─ services/
│  └─ apiClient
│
└─ types/
   └─ gameTypes
```

---

# 5. UI 구조

## 5.1 Game Layout

기본 레이아웃

```
+--------------------------------------+
|           Story View                 |
|                                      |
|  AI가 생성한 소설 내용 표시          |
|                                      |
+--------------------------------------+
| Player Input                        |
| [________________________________]  |
|             [Send]                  |
+--------------------------------------+
| Game State Panel                    |
| HP | Inventory | Location | Quest   |
+--------------------------------------+
```

---

# 6. 주요 컴포넌트

## ChatMessage

채팅 메시지를 렌더링

```ts
type ChatMessage = {
  id: string
  role: "player" | "system" | "ai"
  content: string
}
```

지원 기능

* Markdown 렌더링
* 시스템 메시지 스타일
* AI 메시지 스타일

---

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

---

## StoryView

스토리 텍스트 출력

기능

* AI 생성 텍스트 출력
* 이전 스토리 히스토리
* 스크롤 관리

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

게임 상태 모델

```ts
type GameState = {
  sessionId: string
  messages: ChatMessage[]
  player: PlayerState
  world: WorldState
}
```

PlayerState

```ts
type PlayerState = {
  hp: number
  inventory: string[]
  location: string
}
```

---

# 8. API 통신

Backend API

```
POST /game/start
POST /game/action
GET  /game/state
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
  initialStory
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
  action: "open the door"
}
```

Response

```
{
  story,
  updatedState
}
```

---

# 9. 게임 흐름

전체 흐름

```
1 User enters action
2 Frontend sends API request
3 Backend game engine updates state
4 LLM generates story
5 Response returned
6 UI updates
```

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