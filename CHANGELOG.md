# Changelog

All notable changes to Agent Nonsense are documented here. The project follows Semantic Versioning.

## [Unreleased]

### Fixed

- Parse coalesced SSE batches in linear time and drain live replies in bounded batches so fast continuous output keeps the desktop responsive. The stop button retains the correct cancellation status.
- Avoid reverse DNS during local HTTP server startup, flush readiness immediately, and report occupied Windows ports consistently before launching the owned child process.
- Continuous random streams now switch tasks after a complete preset and its tool results, instead of repeating the first selection forever. Consecutive random selections avoid immediate repeats; explicit presets and finite responses remain pinned.
- Desktop previews now display the actual selected task for all three protocols without changing the random selector into a fixed preset.
- Preview dialogue selection now updates its question and clears the previous output; switching dialogue or protocol during streaming cancels the old reply and starts the selected conversation immediately.
- Kept the preview send action available during streaming so an edited question can be resent; stale replies no longer write into a replacement conversation.
- Restored the repository's original Doupi icon in the sidebar, dashboard, preview, and application window, including installed wheels.

### Added

- Self-contained Windows x64 EXE installers, Linux x64 DEB packages, and macOS arm64/x64 DMGs, plus portable archives, checksums and native installation smoke tests.
- GitHub Actions builds on all four target systems, publishes verified preview/release downloads, and preserves diagnostic reports on failure.
- Optional Python/Qt desktop app (`pip install '.[gui]'`, `doupi`) with a Chinese UI, service lifecycle, configuration, real streaming previews, background jobs, preset editing, and logs.
- Personal preset copies, validation before atomic saves, loopback-only requests, port-conflict reporting, and cleanup of owned processes on close.
- Cross-platform launchers, VS Code debug configurations, desktop documentation, and offscreen GUI integration tests.

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
