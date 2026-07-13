# Changelog

All notable changes to Agent Nonsense are documented here. The project follows Semantic Versioning.

## [Unreleased]

### Changed

- Slowed the default stream cadence to a 2.0 second base delay with up to 0.32 seconds of random jitter.
- Randomized task selection for every new message while preserving explicit `preset` overrides.
- Added AI-style Markdown headings, quotes, checklists, emphasis, and fenced tool/status blocks.
- Added `AGENT_NONSENSE_PORT` as a startup port configuration option.
- Removed simulation labels from visible chat and tool text while retaining zero-token API metadata and documentation.
- Added character-by-character streaming with configurable `character_delay` and `--character-delay` options.

## [0.1.0] - 2026-07-13

### Added

- OpenAI Responses and Chat Completions compatible endpoints.
- Anthropic Messages compatible endpoint.
- Finite and continuous SSE streaming with disconnect handling.
- API-only distribution with finite and continuous status streams.
- Sandboxed `list_files`, `read_file`, and `write_file` tools.
- Desktop-compatible text tool loops and opt-in native Responses tool events.
- Ten editable long-form activity presets with generated questions and tool nodes.
- Background activity jobs with start, inspect, and stop endpoints.
- Standard-library test suite, packaging metadata, and GitHub Actions CI.

### Security

- Tool paths are constrained to the configured sandbox.
- Write size is limited and API responses report zero upstream token usage.
