---
name: pm-planner
description: Break a product or engineering feature request into concrete requirements, scoped implementation tasks, dependencies, risks, and an execution plan. Use when Codex is asked to act like a PM, turn a rough feature idea into actionable work items, estimate delivery order, define milestones, or prepare a development plan before implementation.
---

# PM Planner

Convert a vague or high-level feature request into a delivery-ready plan. Reduce ambiguity, expose assumptions, and organize the work so an engineer can start execution without inventing the structure from scratch.

## Workflow

### 1. Frame the request

- Restate the feature in one sentence.
- Extract the user goal, target user, and expected outcome.
- Separate facts from assumptions.
- Identify missing constraints such as deadline, scope boundary, success metric, affected surfaces, and integration points.
- If a missing detail materially changes the plan, ask a short targeted question. Otherwise proceed with explicit assumptions.

### 2. Define scope

- State what is in scope.
- State what is explicitly out of scope for the proposed iteration.
- Prefer an MVP-first boundary when the request is broad.
- Note external dependencies such as APIs, content, infra, design, or approvals.

### 3. Break the feature into workstreams

- Group work by workstream rather than by chronology when that improves clarity.
- For OpenNovel, default to these sections unless the user asks for a different structure:
  - backend
  - frontend
  - content
  - prompt
  - QA
- Keep every section in the output even if it is small. If a section has no meaningful work, say `No major work for this iteration` instead of omitting it.
- Use project architecture constraints when assigning work:
  - `backend`: engine logic, state transitions, API, persistence, session handling
  - `frontend`: UI, interaction flow, state sync, rendering, input handling
  - `content`: JSON content, quests, locations, NPC data, narrative assets
  - `prompt`: LLM prompt structure, narrative formatting, guardrails, prompt pipeline
  - `QA`: deterministic engine tests, API validation, prompt/output checks, regression coverage

### 4. Decompose into actionable tasks

For each task:

- Use a verb-led title.
- Keep the unit of work small enough for one owner to complete and review.
- State why the task exists when it is not obvious.
- Capture dependencies or blockers.
- Flag parallelizable tasks.
- Distinguish build work from validation work.

### 5. Sequence the plan

- Order tasks by dependency, not preference.
- Split into phases or milestones when useful:
  - discovery
  - implementation
  - integration
  - verification
  - release
- Call out the critical path.
- Mark items that can be deferred to a later iteration.

### 6. Surface delivery risks

- Identify scope, technical, UX, dependency, and testing risks.
- Pair each major risk with a mitigation or follow-up.
- Mention open questions separately from risks.

### 7. Propose commit slices

- After defining the work plan, suggest a practical commit sequence.
- Group changes into reviewable units rather than one commit per tiny task.
- Use the format `commitType(feature-type)`.
- Build `feature-type` as `category/feature-name`.
- Default categories for OpenNovel are:
  - `backend`
  - `frontend`
  - `content`
  - `prompt`
  - `qa`
- Write `feature-name` in lowercase kebab-case.
- Example scopes:
  - `backend/session-store`
  - `frontend/chat-log`
  - `content/murder-case`
  - `prompt/narrative-json`
  - `qa/action-api`
- Recommended commit types include:
  - `feat`
  - `fix`
  - `chore`
  - `refactor`
  - `test`
  - `docs`
- When useful, attach one short commit message suggestion per phase or workstream.
- Do not invent commit messages for work that is explicitly out of scope.

## Output Format

Prefer this structure unless the user requests a different format:

### Summary

- One short paragraph describing the feature objective and planning assumptions.

### Scope

- `In scope`
- `Out of scope`

### Workstreams

1. `Backend`
2. `Frontend`
3. `Content`
4. `Prompt`
5. `QA`

For each workstream include:

- `Goal`
- `Tasks`
- `Dependencies`
- `Notes`

### Execution Plan

1. `Phase 1`
2. `Phase 2`
3. `Phase 3`

### Suggested Commits

- `commitType(category/feature-name): short summary`
- Example: `feat(prompt/narrative-json): add prompt builder for action results`
- Example: `test(backend/investigate-action): cover event resolution flow`

### Risks and Open Questions

- `Risk`
- `Mitigation`
- `Open question`

## Planning Rules

- Prefer concrete deliverables over abstract recommendations.
- Prefer tasks that map cleanly to tickets.
- Do not pad the plan with generic engineering chores unless they are actually needed.
- State assumptions explicitly instead of hiding uncertainty.
- If the repository context is available, align the plan to the existing architecture and constraints.
- In OpenNovel, respect the rule that the core game engine is the source of truth and LLM work stays in the narrative layer.
- Do not place state mutation or success/failure judgment inside `prompt` tasks.
- When the request is implementation-ready, keep the plan tight. When the request is ambiguous, spend more effort on scope control and assumptions.
- Suggested commits should follow the user's convention exactly: `commitType(category/feature-name)`.

## Example Triggers

- "결제 기능 추가하려는데 작업 단위로 쪼개줘"
- "이 기능을 MVP 범위로 나누고 구현 순서를 짜줘"
- "채팅 UI 리팩터링 작업을 백엔드/프론트/테스트로 분해해줘"
- "이 요구사항으로 개발 계획 세워줘"
