# OpenNovel

Languages: [English](./README.md) | [한국어](./README.ko.md)

OpenNovel is an AI-powered interactive fiction game.  
The current `main` branch ships a single Python service that serves both the backend API and the browser UI.

At runtime, the app starts with a small set of story setup presets, opens a session, and lets a `StoryAgent` generate the next scene, choices, and a lightweight compatibility state snapshot.

## Current Architecture

High-level flow:

```text
Player Input
  -> FastAPI Server
  -> GameSessionService
  -> StoryAgent
  -> Narrative / Choices / State Snapshot
  -> UI Update
```

Current implementation includes:
- Python `agent` service as the official runtime
- startup `StorySetupAgent` that generates or falls back to 3 story presets
- `StoryAgent`-owned story progression for `/game/*`
- compatibility `IntenderAgent` and `NarratorAgent` endpoints
- in-memory session storage
- Chroma-based retrieval
- static frontend served by the same server
- chat UI, turn graph, and debug turn-log tools

Current limitations:
- no persistent database
- no streaming responses
- no React/TypeScript frontend
- compatibility state on `main` still uses dungeon-era field names such as `quests.sunken_ruins.stage`

## Repository Layout

```text
agent/        Python runtime, API routes, agents, prompts, retrieval
frontend/     HTML, CSS, and vanilla JS client
content/      Static world/content data used by the runtime
docs/         Backend and frontend documentation
```

Useful docs:
- [AGENTS.md](./AGENTS.md)
- [docs/backend/BACKEND.md](./docs/backend/BACKEND.md)
- [docs/frontend/FRONTEND.md](./docs/frontend/FRONTEND.md)
- [agent/README.md](./agent/README.md)

## Requirements

- Python `>=3.9`
- a virtual environment for `agent/`
- optional Gemini API key if you want live Gemini narrative generation

## Quick Start

1. Create and activate a virtual environment inside `agent/`.
2. Install dependencies.
3. Copy or adapt `agent/.env.example`.
4. Run the FastAPI server.

Example:

```bash
cd path/to/OpenNovel/agent
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -e ".[dev]"
```

Then start the app from the repo root:

```bash
cd path/to/OpenNovel
PYTHONPATH=agent agent/.venv/bin/uvicorn app.main:app --app-dir agent --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

## Environment Variables

`agent/.env.example` contains the current baseline. The main runtime supports role-based LLM settings.

Common settings:

```bash
AGENT_VECTOR_DB_PROVIDER=chroma
AGENT_VECTOR_DB_PATH=.chroma
AGENT_VECTOR_AUTO_INDEX=true

AGENT_INTENDER_PROVIDER=mock
AGENT_INTENDER_MODEL=gpt-4.1-mini
AGENT_INTENDER_TIMEOUT_SECONDS=180

AGENT_NARRATOR_PROVIDER=mock
AGENT_NARRATOR_MODEL=gpt-4.1-mini
AGENT_NARRATOR_TIMEOUT_SECONDS=180
```

To use Gemini from the server side, set role-specific provider fields such as:

```bash
AGENT_INTENDER_PROVIDER=gemini
AGENT_INTENDER_MODEL=gemini-2.5-flash
AGENT_INTENDER_API_KEY=...

AGENT_NARRATOR_PROVIDER=gemini
AGENT_NARRATOR_MODEL=gemini-2.5-flash
AGENT_NARRATOR_API_KEY=...
```

The browser UI can also accept a per-session Gemini key on start.

## Main API Endpoints

Runtime endpoints:
- `GET /`
- `GET /health`
- `GET /story-setups`
- `POST /game/start`
- `POST /game/action`
- `GET /game/state`

Compatibility / debug endpoints:
- `GET /debug/turn-log`
- `POST /intent/validate`
- `POST /narrative/opening`
- `POST /narrative/turn`

Example start request:

```json
{
  "storySetupId": "sunken_ruins",
  "geminiApiKey": "AIza...",
  "geminiModel": "gemini-2.5-flash"
}
```

Example action request:

```json
{
  "sessionId": "session-...",
  "inputText": "주변을 조사한다"
}
```

## Frontend

The frontend is currently a server-served single-page app built with plain HTML, CSS, and JavaScript.

Main UI pieces:
- story setup selector
- Gemini API key input
- new session button
- story log
- choice buttons
- free-text input
- state panel
- turn graph
- debug hover panel

## Debugging

For local debugging, enable the debug UI and inspect per-turn bundles:

```bash
PYTHONPATH=agent \
OPENNOVEL_DEBUG_UI=true \
agent/.venv/bin/uvicorn app.main:app --app-dir agent --host 127.0.0.1 --port 8000
```

Useful checks:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/story-setups
curl "http://127.0.0.1:8000/debug/turn-log?sessionId=SESSION_ID&turn=0"
```

Logs are written under `log/`, including:
- `log/agent/backend-requests.jsonl`
- `log/agent/intent-results.jsonl`
- `log/agent/narrative-results.jsonl`
- `log/agent/game-results.jsonl`
- `log/agent/llm-errors.jsonl`

## Testing

Backend tests:

```bash
cd path/to/OpenNovel
PYTHONPATH=agent agent/.venv/bin/pytest agent/tests
```

Basic static checks:

```bash
python3 -m compileall agent/app frontend
node --check frontend/app.js
```

## Status

This repository is still an MVP-oriented codebase. The current `main` branch prioritizes:
- fast iteration on story runtime behavior
- compatibility with older intent/narrative endpoints
- local debugging visibility

It does not yet aim for final architecture stability.
