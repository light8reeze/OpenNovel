# Changelog

All notable changes to OpenNovel will be documented in this file.

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
