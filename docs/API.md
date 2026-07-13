# Agent Nonsense API

The default server listens on `127.0.0.1:8787`. All JSON responses use UTF-8, include `X-Mock-Agent: true` and `X-Token-Usage: 0`, and report zero usage.

Set a startup port with `--port 9901` or `AGENT_NONSENSE_PORT=9901`. The command-line flag takes precedence over the environment variable.

## Compatibility endpoints

### `GET /v1/models`

Returns `agent-nonsense` and the backward-compatible `mock-agent` alias for desktop client discovery.

### `POST /v1/responses`

Accepts a string or Responses-style `input` list. Supported Agent Nonsense extensions:

- `continuous`: keep a streaming request open until disconnect.
- `max_activity_events`: number of scripted stages in finite mode.
- `modules`: activity module names.
- `preset`: force a preset ID.
- `use_presets`: set to `false` to use random conversation lines.
- `simulate_tools`: execute sandbox tools and stream readable results.
- `native_tools`: emit native Responses function-call events.
- `character_delay`: delay in seconds between individual streamed text characters.
- `speed_factor`: values above `1` stream faster.

```json
{
  "model": "agent-nonsense",
  "stream": true,
  "continuous": false,
  "max_activity_events": 4,
  "preset": "api-timeout",
  "simulate_tools": true,
  "input": "Investigate an API timeout"
}
```

Finite streams end with `response.completed`. Continuous streams end only when the client disconnects.

Loaded presets are compiled to at least 5,000 characters each. Every new request randomly selects one unless the explicit `preset` field is supplied. One streaming response keeps its selected task for the lifetime of that response. Visible text uses Markdown headings, blockquotes, checklists, emphasis, and fenced status/tool blocks without describing the internal selection process.

### `POST /v1/chat/completions`

Accepts OpenAI-style `messages`. Streaming responses use Chat Completions chunks and end with `data: [DONE]` in finite mode.

### `POST /v1/messages`

Accepts Anthropic-style `messages`. Streaming responses use Messages events and end with `message_stop` in finite mode.

## Activity jobs

- `GET /v1/agent/modules`
- `GET /v1/agent/jobs`
- `POST /v1/agent/jobs`
- `GET /v1/agent/jobs/{id}`
- `POST /v1/agent/jobs/{id}/stop`
- `POST /v1/agent/activity`

`max_events: 0` and `duration_seconds: 0` create an unlimited job that runs until stopped.

## File tools

`POST /tools/call` accepts `list_files`, `read_file`, or `write_file`. Paths are relative to the configured sandbox. Absolute paths and paths escaping the sandbox return `403`.

```json
{
  "name": "write_file",
  "arguments": {
    "path": "notes/example.txt",
    "content": "hello"
  }
}
```

## Errors

Unknown routes and validation failures return JSON. The service is intentionally small and does not attempt to reproduce every optional field from upstream APIs.
