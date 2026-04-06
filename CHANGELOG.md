# Changelog

All notable changes to OpenNovel will be documented in this file.

## [Unreleased] - Phase 2

### Added
- **Phase 2-A: Diegetic Feedback**
  - Player style reflection: `style_tags` now influence narrative tone and NPC reactions
  - Theme-specific `style_narrative_hints` for contextual storytelling
  - NPC affinity + style combination for special choices (affinity ≥7 + diplomatic/curious)
  - 5 new tests in `test_diegetic_feedback.py`
- **Phase 2-B: NPC Autonomous Actions**
  - `NpcBehavior` model with trigger, condition, action, cooldown_turns
  - `NpcEvent` system for autonomous NPC reactions
  - Validator checks NPC events on `turn_start` and `player_enters`
  - Condition evaluation: affinity thresholds, turn thresholds
  - Narrator NPC Events section for autonomous action narration
  - 42 behaviors across 7 themes (2 per NPC)
  - 6 new tests in `test_npc_autonomous.py`

### Changed
- `WorldNpc` model extended with `personality` and `behaviors` fields
- Narrator prompts now include Player Style and NPC Events sections
- World Builder preserves NPC behaviors from theme packs

### Tests
- 56 → 62 tests passed

## [1.0.0.0] - 2026-04-03

### Added
- StateManager victory condition awareness: prompts now include victory path conditions for better ending recognition
- LLM client retry backoff: respects provider retry-after headers and body hints from Gemini/OpenAI
- Improved retrieval query composition: location + action type + tone for better context

### Changed
- Prompt token optimization: 22% reduction through history removal and lightweight blueprint summaries
- StateManager discovery log now limited to 5 most recent entries

### Fixed
- Ending narrative tone: added ENDING DIRECTIVE to prevent incomplete expressions in victory scenes
- Ending choices cleared: validator now removes choices when objective completed
- QA regression: finale path resolution uses correct climax location
- QA regression: session restore logic prevents stale state false positives
- Move and talk progression flags now managed by validator, not StateManager proposals
