#!/usr/bin/env python3
import argparse
import json
import os
import random
import threading
import time
import uuid
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .longform import compile_preset


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787

PHASES = [
    "Inspecting the request and identifying relevant context",
    "Checking available tools and constraints",
    "Drafting an approach and validating assumptions",
    "Preparing the final response",
]

ACTIVITY_MODULES = {
    "research": {
        "description": "Simulated web/codebase research activity",
        "lines": [
            "agent: expanding query terms from user prompt",
            "agent: checking local notes and cached references",
            "agent: scoring sources by relevance and freshness",
            "agent: extracting candidate facts into scratchpad",
            "agent: reconciling conflicting signals",
        ],
    },
    "code_edit": {
        "description": "Simulated code editing activity",
        "lines": [
            "agent: locating implementation boundary",
            "agent: reading adjacent tests and helpers",
            "agent: preparing minimal patch",
            "agent: applying edit set to workspace",
            "agent: formatting touched files",
        ],
    },
    "test_run": {
        "description": "Simulated test/build activity",
        "lines": [
            "runner: collecting tests",
            "runner: building dependency graph",
            "runner: executing focused test selection",
            "runner: replaying failed-case seed",
            "runner: summarizing verification result",
        ],
    },
    "file_ops": {
        "description": "Simulated file tool activity",
        "lines": [
            "tool:list_files path=.",
            "tool:read_file path={file}",
            "tool:write_file path={scratch} bytes={bytes}",
            "tool:read_file path={scratch}",
            "agent: indexed file operation results",
        ],
    },
    "debug_trace": {
        "description": "Simulated debugging activity",
        "lines": [
            "debug: capturing failing input shape",
            "debug: tracing caller chain",
            "debug: checking state transition invariants",
            "debug: comparing expected and actual output",
            "debug: narrowing likely root cause",
        ],
    },
}

FAKE_FILES = [
    "src/agent/runtime.ts",
    "src/tools/filesystem.ts",
    "app/services/planner.py",
    "tests/test_agent_flow.py",
    "packages/core/src/session.rs",
]

FINAL_TEMPLATES = [
    "我先把任务拆成上下文、修改和验证三个部分。目前更适合从相关文件和调用链开始确认，再决定是否需要改动。",
    "我已经把这次请求的工作范围整理出来了。接下来会先核对边界条件，再做一个尽量小的修改，并用针对性测试复核。",
    "目前没有必要扩大修改范围。我会继续沿着现有实现检查关键路径，确认结果稳定后再整理结论。",
]

CONVERSATION_LINES = {
    "research": [
        "我先看一下现有上下文，确认这个问题具体落在哪一层。",
        "我把相关信息整理一下，先区分现象、影响范围和可能的触发条件。",
        "这里我先不急着修改，先确认当前实现和预期行为是不是一致。",
        "结合目前看到的线索，问题更像是局部边界条件，我继续往调用链下游看。",
    ],
    "file_ops": [
        "我先读一下相关文件，看看读写逻辑和调用方之间有没有不一致。",
        "我找到一个比较相关的文件了，接下来核对它的输入、输出和异常处理。",
        "这里先做一次小范围的文件检查，确认路径、编码和空内容这些情况。",
        "我把相邻文件也看一遍，避免只修到表面而漏掉另一个调用入口。",
    ],
    "code_edit": [
        "我准备先做一个最小范围的修改，尽量不影响旁边已经工作的逻辑。",
        "修改边界已经比较清楚了，我先把变更点收窄到这个函数和它的直接调用方。",
        "我正在对照现有代码整理补丁，先保留原来的接口和错误处理方式。",
        "这一步先不引入新的抽象，直接修正当前路径里的行为，再看测试反馈。",
    ],
    "test_run": [
        "我先跑一组针对性的测试，确认问题是否能稳定复现。",
        "测试正在跑，我会先看失败位置和输入形状，再决定要不要补边界用例。",
        "这一轮主要验证正常路径、空输入和异常分支，避免只看一个 happy path。",
        "测试结果出来后我再复核一次，确认没有因为修改一个地方而影响其它路径。",
    ],
    "debug_trace": [
        "我沿着调用链往回看，先确认状态是在什么时候发生变化的。",
        "这里有两个可能的分支，我分别核对一下实际输入和预期状态。",
        "我继续缩小范围，目前更值得关注的是边界条件而不是主流程。",
        "这个方向基本明确了，我再检查一次异常分支，避免过早下结论。",
    ],
}


def now_unix() -> int:
    return int(time.time())


def json_bytes(payload) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def split_stream_text_event(event):
    target = None
    text = ""
    if event.get("type") == "response.output_text.delta":
        target = "responses"
        text = str(event.get("delta", ""))
    elif event.get("object") == "chat.completion.chunk":
        choices = event.get("choices") or []
        if choices:
            target = "chat"
            text = str((choices[0].get("delta") or {}).get("content", ""))
    elif event.get("type") == "content_block_delta" and (event.get("delta") or {}).get("type") == "text_delta":
        target = "claude"
        text = str((event.get("delta") or {}).get("text", ""))
    elif str(event.get("type", "")).startswith("agent.") and isinstance(event.get("text"), str):
        target = "agent"
        text = event["text"]

    if not target or not text:
        yield event, False, True
        return

    last_index = len(text) - 1
    for index, character in enumerate(text):
        chunk = deepcopy(event)
        if target == "responses":
            chunk["delta"] = character
        elif target == "chat":
            chunk["choices"][0]["delta"]["content"] = character
        elif target == "claude":
            chunk["delta"]["text"] = character
        else:
            chunk["text"] = character
        yield chunk, True, index == last_index


def load_presets(path=None):
    preset_path = Path(path) if path else Path(__file__).with_name("presets.json")
    try:
        payload = json.loads(preset_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    presets = payload.get("presets", []) if isinstance(payload, dict) else []
    return [compile_preset(preset) for preset in presets if isinstance(preset, dict) and preset.get("steps")]


def extract_openai_prompt(body: dict) -> str:
    messages = body.get("messages") or []
    if not messages:
        return ""
    parts = []
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")
        if isinstance(content, list):
            text = " ".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
        else:
            text = str(content)
        parts.append(f"{role}: {text}")
    return "\n".join(parts)


def extract_claude_prompt(body: dict) -> str:
    messages = body.get("messages") or []
    parts = []
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")
        if isinstance(content, list):
            text = " ".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
        else:
            text = str(content)
        parts.append(f"{role}: {text}")
    return "\n".join(parts)


def extract_responses_prompt(body: dict) -> str:
    value = body.get("input", "")
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return str(value)
    parts = []
    for item in value:
        if isinstance(item, str):
            parts.append(item)
            continue
        if not isinstance(item, dict):
            continue
        role = item.get("role", "user")
        content = item.get("content", item.get("text", ""))
        if isinstance(content, list):
            text = " ".join(
                str(part.get("text", part.get("value", "")))
                for part in content
                if isinstance(part, dict)
            )
        else:
            text = str(content)
        if text:
            parts.append(f"{role}: {text}")
    return "\n".join(parts)


def build_mock_text(prompt: str, closing: str = "") -> str:
    hint = prompt.strip().splitlines()[-1][:240] if prompt.strip() else "empty prompt"
    final = closing or random.choice(FINAL_TEMPLATES)
    return (
        "## 当前工作状态\n\n"
        f"> {final}\n\n"
        "### 输入摘要\n\n"
        f"- **任务**：{hint}\n"
        "- **上游 token**：`0`\n"
        "- **状态**：`continuing`"
    )


def parse_modules(value):
    if isinstance(value, str):
        requested = [item.strip() for item in value.split(",") if item.strip()]
    elif isinstance(value, list):
        requested = [str(item) for item in value]
    else:
        requested = []
    return [item for item in requested if item in ACTIVITY_MODULES] or list(ACTIVITY_MODULES.keys())


def render_activity_line(module: str, line: str, prompt: str) -> str:
    fake_file = random.choice(FAKE_FILES)
    scratch = f".agent-scratch/{uuid.uuid4().hex[:8]}.md"
    rendered = line.format(
        file=fake_file,
        scratch=scratch,
        bytes=random.randint(128, 8192),
        prompt=prompt.strip()[:80],
    )
    elapsed = f"{random.uniform(0.08, 4.5):0.2f}s"
    status = random.choice(["ok", "pending", "cached", "retry=0", "score=0.82"])
    return f"[{elapsed}] [{module}] {rendered} ({status})"


def generate_activity_events(prompt: str, modules, max_events: int):
    count = 0
    while max_events is None or count < max_events:
        module = random.choice(modules)
        script = ACTIVITY_MODULES[module]["lines"]
        for line in script:
            if max_events is not None and count >= max_events:
                break
            count += 1
            yield {
                "id": f"evt_{uuid.uuid4().hex[:12]}",
                "type": "agent.activity",
                "module": module,
                "created": now_unix(),
                "text": render_activity_line(module, line, prompt),
            }


def generate_conversation_events(prompt: str, modules, max_events: int):
    count = 0
    while max_events is None or count < max_events:
        module = random.choice(modules)
        line = random.choice(CONVERSATION_LINES[module])
        hint = prompt.strip().splitlines()[-1][:80] if prompt.strip() else "当前任务"
        if count == 0:
            line = f"关于“{hint}”，{line}"
        count += 1
        yield {
            "id": f"evt_{uuid.uuid4().hex[:12]}",
            "type": "agent.conversation",
            "module": module,
            "created": now_unix(),
            "text": line,
        }


def generate_preset_events(preset, max_events):
    steps = preset.get("steps", [])
    count = 0
    index = 0
    while steps and (max_events is None or count < max_events):
        step = steps[index % len(steps)]
        count += 1
        index += 1
        yield {
            "id": f"evt_{uuid.uuid4().hex[:12]}",
            "type": "agent.preset",
            "module": step.get("module", "research"),
            "created": now_unix(),
            "text": str(step.get("text", "我继续检查当前任务的上下文。")),
            "tool": step.get("tool"),
        }


class ActivityJob:
    def __init__(self, server, prompt, modules, max_events, duration_seconds, speed_factor):
        self.server = server
        self.id = f"job_{uuid.uuid4().hex[:12]}"
        self.prompt = prompt
        self.modules = modules
        self.max_events = max_events
        self.duration_seconds = duration_seconds
        self.speed_factor = speed_factor
        self.status = "queued"
        self.started_at = None
        self.finished_at = None
        self.event_count = 0
        self.events = []
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, name=self.id, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def append_event(self, event):
        with self.lock:
            self.event_count += 1
            self.events.append(event)
            del self.events[:-200]

    def snapshot(self):
        with self.lock:
            return {
                "id": self.id,
                "status": self.status,
                "prompt": self.prompt,
                "modules": self.modules,
                "max_events": self.max_events,
                "duration_seconds": self.duration_seconds,
                "speed_factor": self.speed_factor,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "event_count": self.event_count,
                "events": list(self.events),
            }

    def run(self):
        with self.lock:
            self.status = "running"
            self.started_at = now_unix()
        started = time.monotonic()
        try:
            for event in generate_activity_events(self.prompt, self.modules, self.max_events or None):
                if self.stop_event.is_set():
                    break
                if self.duration_seconds and time.monotonic() - started >= self.duration_seconds:
                    break
                self.append_event(event)
                interval = (self.server.delay + random.uniform(0, self.server.jitter)) / self.speed_factor
                if self.stop_event.wait(interval):
                    break
            with self.lock:
                self.status = "stopped" if self.stop_event.is_set() else "completed"
        finally:
            with self.lock:
                self.finished_at = now_unix()


def maybe_tool_calls(body: dict):
    tools = body.get("tools") or []
    if not tools:
        return None

    tool = tools[0]
    if tool.get("type") == "function":
        fn = tool.get("function", {})
        name = fn.get("name", "mock_tool")
    else:
        name = tool.get("name", "mock_tool")

    return [
        {
            "id": f"call_{uuid.uuid4().hex[:12]}",
            "type": "function",
            "function": {
                "name": name,
                "arguments": json.dumps({"simulated": True}, ensure_ascii=False),
            },
        }
    ]


class MockAgentServer(BaseHTTPRequestHandler):
    server_version = "AgentNonsense/0.1.0"

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            with self.server.jobs_lock:
                active_jobs = sum(job.status in {"queued", "running"} for job in self.server.jobs.values())
            self.send_json(
                {
                    "ok": True,
                    "service": "agent-nonsense",
                    "mode": "local-zero-token-simulator",
                    "upstream_calls": 0,
                    "token_usage": 0,
                    "active_jobs": active_jobs,
                }
            )
            return
        if parsed.path == "/v1/models":
            self.send_json(
                {
                    "object": "list",
                    "data": [
                        {"id": "agent-nonsense", "object": "model", "created": now_unix(), "owned_by": "local-simulator"},
                        {"id": "mock-agent", "object": "model", "created": now_unix(), "owned_by": "local-simulator"},
                    ],
                }
            )
            return
        if parsed.path == "/v1/agent/modules":
            self.send_json(
                {
                    "modules": [
                        {"name": name, "description": meta["description"]}
                        for name, meta in sorted(ACTIVITY_MODULES.items())
                    ]
                }
            )
            return
        if parsed.path == "/v1/agent/jobs":
            with self.server.jobs_lock:
                jobs = [job.snapshot() for job in self.server.jobs.values()]
            self.send_json({"jobs": jobs})
            return
        job_parts = parsed.path.strip("/").split("/")
        if len(job_parts) == 4 and job_parts[:3] == ["v1", "agent", "jobs"]:
            with self.server.jobs_lock:
                job = self.server.jobs.get(job_parts[3])
            if job is None:
                self.send_json({"error": "job not found"}, status=404)
                return
            self.send_json({"job": job.snapshot()})
            return
        self.send_json({"error": {"message": "Not found", "type": "not_found_error"}}, status=404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            body = self.read_json()
        except ValueError as exc:
            self.send_json({"error": str(exc)}, status=400)
            return

        if parsed.path == "/v1/agent/jobs":
            self.handle_agent_job_start(body)
            return
        job_parts = parsed.path.strip("/").split("/")
        if len(job_parts) == 5 and job_parts[:3] == ["v1", "agent", "jobs"] and job_parts[4] == "stop":
            self.handle_agent_job_stop(job_parts[3])
            return
        if parsed.path == "/v1/chat/completions":
            self.handle_openai_chat(body)
            return
        if parsed.path == "/v1/responses":
            self.handle_openai_responses(body)
            return
        if parsed.path == "/v1/messages":
            self.handle_claude_messages(body)
            return
        if parsed.path == "/tools/call":
            self.handle_tool_call(body)
            return
        if parsed.path == "/v1/agent/activity":
            self.handle_agent_activity(body)
            return

        self.send_json({"error": {"message": "Not found", "type": "not_found_error"}}, status=404)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc}") from exc

    def send_json(self, payload, status=200, headers=None):
        data = json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("X-Mock-Agent", "true")
        self.send_header("X-Token-Usage", "0")
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def send_sse(self, events, delay=None, character_delay=None, done_marker=True):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("X-Mock-Agent", "true")
        self.send_header("X-Token-Usage", "0")
        self.end_headers()
        delay = self.server.delay if delay is None else max(0, delay)
        character_delay = self.server.character_delay if character_delay is None else max(0, character_delay)
        jitter_scale = delay / self.server.delay if self.server.delay else 0
        jitter = self.server.jitter * jitter_scale
        try:
            for event in events:
                for payload, is_text, is_last_character in split_stream_text_event(event):
                    self.wfile.write(f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    if not is_text:
                        continue
                    if is_last_character:
                        if delay or jitter:
                            time.sleep(delay + random.uniform(0, jitter))
                    elif character_delay:
                        time.sleep(character_delay)
            if done_marker:
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return
        finally:
            self.close_connection = True

    def stream_delays(self, body):
        try:
            speed_factor = float(body.get("speed_factor", self.server.default_speed_factor))
            character_delay = float(body.get("character_delay", self.server.character_delay))
        except (TypeError, ValueError) as exc:
            raise ValueError("speed_factor and character_delay must be numbers") from exc
        if speed_factor <= 0:
            raise ValueError("speed_factor must be a positive number")
        if character_delay < 0:
            raise ValueError("character_delay must be zero or greater")
        return self.server.delay / speed_factor, character_delay / speed_factor

    def activity_delay(self, body):
        return self.stream_delays(body)[0]

    def handle_agent_job_start(self, body):
        try:
            max_events = int(body.get("max_events", 0))
            duration_seconds = max(0, float(body.get("duration_seconds", 0)))
            speed_factor = float(body.get("speed_factor", self.server.default_speed_factor))
            if max_events < 0 or max_events > 100000:
                raise ValueError("max_events must be between 0 and 100000")
            if duration_seconds > 86400:
                raise ValueError("duration_seconds must be at most 86400")
            if speed_factor <= 0:
                raise ValueError("speed_factor must be a positive number")
        except (TypeError, ValueError) as exc:
            self.send_json({"error": str(exc)}, status=400)
            return

        job = ActivityJob(
            self.server,
            str(body.get("prompt", "")),
            parse_modules(body.get("modules")),
            max_events,
            duration_seconds,
            speed_factor,
        )
        with self.server.jobs_lock:
            self.server.jobs[job.id] = job
        job.start()
        self.send_json({"job": job.snapshot()})

    def handle_agent_job_stop(self, job_id):
        with self.server.jobs_lock:
            job = self.server.jobs.get(job_id)
        if job is None:
            self.send_json({"error": "job not found"}, status=404)
            return
        job.stop()
        job.thread.join(timeout=1)
        self.send_json({"job": job.snapshot()})

    def tools_enabled(self, body):
        configured = body.get("simulate_tools", getattr(self.server, "simulate_tools", False))
        return bool(configured) or bool(body.get("tools")) or self.native_tools_enabled(body)

    def native_tools_enabled(self, body):
        return bool(body.get("native_tools", getattr(self.server, "native_tools", False)))

    def tool_event(self, text):
        if text.startswith("tool.call"):
            text = f"#### Tool call\n\n```text\n{text}\n```"
        elif text.startswith("tool.result"):
            text = f"#### Tool result\n\n```text\n{text}\n```"
        return {
            "id": f"evt_{uuid.uuid4().hex[:12]}",
            "type": "agent.tool",
            "module": "file_ops",
            "created": now_unix(),
            "text": text,
        }

    def compact_tool_result(self, result):
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))[:280]

    def execute_tool_result(self, name, args):
        try:
            if name == "list_files":
                return {"ok": True, "result": self.tool_list_files(args)}
            if name == "read_file":
                return {"ok": True, "result": self.tool_read_file(args)}
            if name == "write_file":
                return {"ok": True, "result": self.tool_write_file(args)}
            return {"ok": False, "error": f"Unknown tool: {name}"}
        except PermissionError as exc:
            return {"ok": False, "error": str(exc)}
        except FileNotFoundError as exc:
            return {"ok": False, "error": str(exc)}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

    def native_response_tool_round(self, prompt, round_index, output_items, text_item_id):
        operations = [
            ("list_files", {"path": "."}),
            ("read_file", {"path": "notes/demo.txt"}),
            (
                "write_file",
                {
                    "path": ".agent-scratch/working-note.md",
                    "content": f"# Simulated working note\nround: {round_index}\ntask: {prompt.strip()[:160]}\n",
                },
            ),
        ]
        name, arguments = operations[(round_index - 1) % len(operations)]
        item_id = f"fc_{uuid.uuid4().hex[:20]}"
        call_id = f"call_{uuid.uuid4().hex[:20]}"
        arguments_json = json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))
        item = {
            "id": item_id,
            "type": "function_call",
            "status": "in_progress",
            "call_id": call_id,
            "name": name,
            "arguments": "",
        }
        yield {"type": "response.output_item.added", "output_index": len(output_items), "item": item.copy()}
        for offset in range(0, len(arguments_json), 24):
            yield {
                "type": "response.function_call_arguments.delta",
                "item_id": item_id,
                "output_index": len(output_items),
                "delta": arguments_json[offset : offset + 24],
            }
        yield {
            "type": "response.function_call_arguments.done",
            "item_id": item_id,
            "output_index": len(output_items),
            "arguments": arguments_json,
        }
        result = self.execute_tool_result(name, arguments)
        item["status"] = "completed"
        item["arguments"] = arguments_json
        output_items.append(item)
        yield {"type": "response.output_item.done", "output_index": len(output_items) - 1, "item": item}
        yield {
            "type": "response.output_text.delta",
            "item_id": text_item_id,
            "output_index": 0,
            "content_index": 0,
            "delta": f"\nTOOL_RESULT {name}: {self.compact_tool_result(result)}\n",
        }

    def simulated_tool_call(self, prompt, round_index, name):
        arguments = {
            "list_files": {"path": "."},
            "read_file": {"path": "notes/demo.txt"},
            "write_file": {
                "path": ".agent-scratch/working-note.md",
                "content": f"# Simulated working note\nround: {round_index}\ntask: {prompt.strip()[:160]}\n",
            },
        }.get(name, {"path": "."})
        yield self.tool_event(f"我先调用 `{name}`，把这一阶段需要的上下文取回来。")
        yield self.tool_event(f"tool.call name={name} arguments={json.dumps(arguments, ensure_ascii=False, separators=(',', ':'))}")
        result = self.execute_tool_result(name, arguments)
        yield self.tool_event(f"tool.result name={name} result={self.compact_tool_result(result)}")
        if name == "write_file" and result.get("ok"):
            verify_path = arguments["path"]
            verify = self.execute_tool_result("read_file", {"path": verify_path})
            yield self.tool_event(f"tool.call name=read_file arguments={{\"path\":\"{verify_path}\"}}")
            yield self.tool_event(f"tool.result name=read_file result={self.compact_tool_result(verify)}")
            yield self.tool_event("写入结果已经回读确认，我继续处理后面的检查。")

    def simulated_tool_round(self, prompt, round_index):
        yield self.tool_event('我先调用 `list_files`，确认 sandbox 里有哪些工作文件。')
        try:
            listed = self.tool_list_files({"path": "."})
            yield self.tool_event(f"tool.call name=list_files arguments={{\"path\":\".\"}}")
            yield self.tool_event(f"tool.result name=list_files result={self.compact_tool_result(listed)}")

            file_path = "notes/demo.txt"
            if not self.resolve_sandbox_path(file_path).is_file():
                file_path = "notes/agent-context.txt"
                self.tool_write_file({"path": file_path, "content": "local simulated workspace note\n"})
            yield self.tool_event(f"我再读一下 `{file_path}`，确认刚才的上下文。")
            read_result = self.tool_read_file({"path": file_path})
            yield self.tool_event(f"tool.call name=read_file arguments={{\"path\":\"{file_path}\"}}")
            yield self.tool_event(f"tool.result name=read_file result={self.compact_tool_result(read_result)}")

            scratch_path = ".agent-scratch/working-note.md"
            scratch_content = (
                "# Simulated working note\n"
                f"round: {round_index}\n"
                f"task: {prompt.strip()[:160]}\n"
                f"observation: {read_result.get('content', '')[:120]}\n"
            )
            yield self.tool_event("我把这一轮的观察写入临时工作笔记，再回读确认写入结果。")
            write_result = self.tool_write_file({"path": scratch_path, "content": scratch_content})
            yield self.tool_event(f"tool.call name=write_file arguments={{\"path\":\"{scratch_path}\"}}")
            yield self.tool_event(f"tool.result name=write_file result={self.compact_tool_result(write_result)}")
            verify_result = self.tool_read_file({"path": scratch_path})
            yield self.tool_event(f"tool.call name=read_file arguments={{\"path\":\"{scratch_path}\"}}")
            yield self.tool_event(f"tool.result name=read_file result={self.compact_tool_result(verify_result)}")
            yield self.tool_event("工具回路完成，结果已经回到当前工作上下文，我继续检查下一步。")
        except (PermissionError, FileNotFoundError, ValueError) as exc:
            yield self.tool_event(f"工具返回异常：{exc}，我先保留当前上下文并继续排查。")

    def select_preset(self, body, prompt):
        presets = getattr(self.server, "presets", [])
        if not presets or body.get("use_presets") is False:
            return None
        selected_id = body.get("_selected_preset")
        if selected_id:
            selected = next((preset for preset in presets if preset.get("id") == selected_id), None)
            if selected:
                return selected
        requested = str(body.get("preset", "")).strip().lower()
        if requested:
            matches = [preset for preset in presets if str(preset.get("id", "")).lower() == requested]
            if matches:
                body["_selected_preset"] = matches[0].get("id")
                return matches[0]
        selected = random.choice(presets)
        body["_selected_preset"] = selected.get("id")
        return selected

    def response_text(self, body, prompt):
        preset = self.select_preset(body, prompt)
        closing = preset.get("closing", "") if preset else ""
        return build_mock_text(prompt, closing)

    def conversation_events(self, body, prompt, modules, max_events, continuous, include_tool_text=True):
        event_limit = None if continuous else max_events
        tools_enabled = self.tools_enabled(body)
        conversation_event_count = 0
        round_index = 0
        preset = self.select_preset(body, prompt)
        if preset:
            source = generate_preset_events(preset, None)
            while event_limit is None or conversation_event_count < event_limit:
                event = next(source)
                conversation_event_count += 1
                yield event
                if include_tool_text and tools_enabled and event.get("tool"):
                    round_index += 1
                    yield from self.simulated_tool_call(prompt, round_index, event["tool"])
            return
        source = generate_conversation_events(prompt, modules, None)
        while event_limit is None or conversation_event_count < event_limit:
            event = next(source)
            conversation_event_count += 1
            yield event
            if include_tool_text and tools_enabled and (conversation_event_count == 1 or conversation_event_count % 3 == 0):
                round_index += 1
                yield from self.simulated_tool_round(prompt, round_index)

    def openai_stream_events(self, body, prompt, modules, max_events, continuous):
        model = body.get("model", "agent-nonsense")
        event_limit = None if continuous else max_events
        for event in self.conversation_events(body, prompt, modules, max_events, continuous):
            yield {
                "id": f"chatcmpl_{uuid.uuid4().hex[:16]}",
                "object": "chat.completion.chunk",
                "created": now_unix(),
                "model": model,
                "choices": [{"index": 0, "delta": {"content": event["text"] + "\n"}, "finish_reason": None}],
            }
        if continuous:
            return
        yield {
            "id": f"chatcmpl_{uuid.uuid4().hex[:16]}",
            "object": "chat.completion.chunk",
            "created": now_unix(),
            "model": model,
            "choices": [{"index": 0, "delta": {"content": self.response_text(body, prompt)}, "finish_reason": None}],
        }
        yield {
            "id": f"chatcmpl_{uuid.uuid4().hex[:16]}",
            "object": "chat.completion.chunk",
            "created": now_unix(),
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }

    def activity_event_limit(self, body, field="max_activity_events"):
        try:
            value = int(body.get(field, self.server.default_max_activity_events))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field} must be a positive integer") from exc
        if value <= 0:
            return self.server.default_max_activity_events
        if value > 100000:
            raise ValueError(f"{field} must be at most 100000")
        return value

    def handle_openai_chat(self, body: dict):
        prompt = extract_openai_prompt(body)
        try:
            delay, character_delay = self.stream_delays(body)
            max_events = self.activity_event_limit(body)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, status=400)
            return
        if body.get("stream"):
            modules = parse_modules(body.get("modules"))
            continuous = bool(body.get("continuous", self.server.continuous_stream))
            self.send_sse(
                self.openai_stream_events(body, prompt, modules, max_events, continuous),
                delay=delay,
                character_delay=character_delay,
                done_marker=not continuous,
            )
            return

        tool_calls = maybe_tool_calls(body) if body.get("tool_choice") in ("auto", "required") else None
        message = {"role": "assistant", "content": self.response_text(body, prompt)}
        finish_reason = "stop"
        if tool_calls:
            message["tool_calls"] = tool_calls
            finish_reason = "tool_calls"
        self.send_json(
            {
                "id": f"chatcmpl_{uuid.uuid4().hex[:16]}",
                "object": "chat.completion",
                "created": now_unix(),
                "model": body.get("model", "agent-nonsense"),
                "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }
        )

    def responses_stream_events(self, body, prompt, modules, max_events, continuous):
        response_id = f"resp_{uuid.uuid4().hex[:24]}"
        item_id = f"msg_{uuid.uuid4().hex[:24]}"
        model = body.get("model", "agent-nonsense")
        assistant_item = {
            "id": item_id,
            "type": "message",
            "status": "in_progress",
            "role": "assistant",
            "content": [],
        }
        output_items = [assistant_item]
        response = {
            "id": response_id,
            "object": "response",
            "created_at": now_unix(),
            "status": "in_progress",
            "model": model,
            "output": [],
            "usage": None,
        }
        yield {"type": "response.created", "response": response}
        yield {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": assistant_item,
        }
        yield {
            "type": "response.content_part.added",
            "item_id": item_id,
            "output_index": 0,
            "content_index": 0,
            "part": {"type": "output_text", "text": "", "annotations": []},
        }
        native_tools = self.native_tools_enabled(body)
        for event_index, event in enumerate(
            self.conversation_events(body, prompt, modules, max_events, continuous, include_tool_text=not native_tools),
            start=1,
        ):
            yield {
                "type": "response.output_text.delta",
                "item_id": item_id,
                "output_index": 0,
                "content_index": 0,
                "delta": event["text"] + "\n",
            }
            if native_tools and (event_index == 1 or event_index % 3 == 0):
                yield from self.native_response_tool_round(prompt, event_index, output_items, item_id)
        if continuous:
            return
        answer = self.response_text(body, prompt)
        yield {
            "type": "response.output_text.delta",
            "item_id": item_id,
            "output_index": 0,
            "content_index": 0,
            "delta": answer,
        }
        yield {"type": "response.output_text.done", "item_id": item_id, "output_index": 0, "content_index": 0, "text": answer}
        yield {"type": "response.content_part.done", "item_id": item_id, "output_index": 0, "content_index": 0}
        yield {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": {**assistant_item, "status": "completed", "content": [{"type": "output_text", "text": answer, "annotations": []}]},
        }
        output_items[0] = {**assistant_item, "status": "completed", "content": [{"type": "output_text", "text": answer, "annotations": []}]}
        yield {
            "type": "response.completed",
            "response": {
                **response,
                "status": "completed",
                "output": output_items,
                "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            },
        }

    def handle_openai_responses(self, body: dict):
        prompt = extract_responses_prompt(body)
        modules = parse_modules(body.get("modules"))
        try:
            delay, character_delay = self.stream_delays(body)
            max_events = self.activity_event_limit(body)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, status=400)
            return
        if body.get("stream"):
            continuous = bool(body.get("continuous", self.server.continuous_stream))
            self.send_sse(
                self.responses_stream_events(body, prompt, modules, max_events, continuous),
                delay=delay,
                character_delay=character_delay,
                done_marker=False,
            )
            return
        answer = self.response_text(body, prompt)
        response_id = f"resp_{uuid.uuid4().hex[:24]}"
        self.send_json(
            {
                "id": response_id,
                "object": "response",
                "created_at": now_unix(),
                "status": "completed",
                "model": body.get("model", "agent-nonsense"),
                "output": [
                    {
                        "id": f"msg_{uuid.uuid4().hex[:24]}",
                        "type": "message",
                        "status": "completed",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": answer, "annotations": []}],
                    }
                ],
                "output_text": answer,
                "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            }
        )

    def claude_stream_events(self, body, prompt, modules, max_events, continuous):
        message_id = f"msg_{uuid.uuid4().hex[:24]}"
        yield {
            "type": "message_start",
            "message": {
                "id": message_id,
                "type": "message",
                "role": "assistant",
                "model": body.get("model", "agent-nonsense"),
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            },
        }
        yield {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}
        event_limit = None if continuous else max_events
        for event in self.conversation_events(body, prompt, modules, max_events, continuous):
            yield {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": event["text"] + "\n"},
            }
        if continuous:
            return
        yield {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": self.response_text(body, prompt) + "\n"},
        }
        yield {"type": "content_block_stop", "index": 0}
        yield {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn", "stop_sequence": None},
            "usage": {"output_tokens": 0},
        }
        yield {"type": "message_stop"}

    def handle_claude_messages(self, body: dict):
        prompt = extract_claude_prompt(body)
        modules = parse_modules(body.get("modules"))
        try:
            delay, character_delay = self.stream_delays(body)
            max_events = self.activity_event_limit(body)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, status=400)
            return
        if body.get("stream"):
            continuous = bool(body.get("continuous", self.server.continuous_stream))
            self.send_sse(
                self.claude_stream_events(body, prompt, modules, max_events, continuous),
                delay=delay,
                character_delay=character_delay,
                done_marker=False,
            )
            return
        activity = [event["text"] for event in self.conversation_events(body, prompt, modules, max_events, False)]
        text = "\n".join(activity + ["", self.response_text(body, prompt)])
        self.send_json(
            {
                "id": f"msg_{uuid.uuid4().hex[:24]}",
                "type": "message",
                "role": "assistant",
                "model": body.get("model", "agent-nonsense"),
                "content": [{"type": "text", "text": text}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }
        )

    def handle_agent_activity(self, body: dict):
        prompt = str(body.get("prompt", ""))
        modules = parse_modules(body.get("modules"))
        max_events = int(body.get("max_events", 12))
        if body.get("stream", True):
            try:
                delay, character_delay = self.stream_delays(body)
            except ValueError as exc:
                self.send_json({"error": str(exc)}, status=400)
                return
            self.send_sse(generate_activity_events(prompt, modules, max_events), delay=delay, character_delay=character_delay)
            return
        self.send_json({"events": list(generate_activity_events(prompt, modules, max_events))})

    def handle_tool_call(self, body: dict):
        name = body.get("name")
        args = body.get("arguments") or {}
        try:
            if name == "list_files":
                result = self.tool_list_files(args)
            elif name == "read_file":
                result = self.tool_read_file(args)
            elif name == "write_file":
                result = self.tool_write_file(args)
            else:
                self.send_json({"error": f"Unknown tool: {name}"}, status=400)
                return
        except PermissionError as exc:
            self.send_json({"error": str(exc)}, status=403)
            return
        except FileNotFoundError as exc:
            self.send_json({"error": str(exc)}, status=404)
            return
        except ValueError as exc:
            self.send_json({"error": str(exc)}, status=400)
            return

        self.send_json({"ok": True, "tool": name, "result": result})

    def resolve_sandbox_path(self, requested: str) -> Path:
        if not requested:
            raise ValueError("path is required")
        sandbox = self.server.sandbox.resolve()
        candidate = (sandbox / requested).resolve()
        if candidate != sandbox and sandbox not in candidate.parents:
            raise PermissionError("path escapes sandbox")
        return candidate

    def tool_list_files(self, args: dict):
        root = self.resolve_sandbox_path(args.get("path", "."))
        if not root.exists():
            raise FileNotFoundError(str(root))
        if not root.is_dir():
            raise ValueError("path must be a directory")
        return [{"name": item.name, "type": "dir" if item.is_dir() else "file"} for item in sorted(root.iterdir())]

    def tool_read_file(self, args: dict):
        path = self.resolve_sandbox_path(args.get("path", ""))
        if not path.exists():
            raise FileNotFoundError(str(path))
        if not path.is_file():
            raise ValueError("path must be a file")
        max_bytes = int(args.get("max_bytes", 20000))
        data = path.read_bytes()[:max_bytes]
        return {"path": str(path.relative_to(self.server.sandbox)), "content": data.decode("utf-8", errors="replace")}

    def tool_write_file(self, args: dict):
        path = self.resolve_sandbox_path(args.get("path", ""))
        content = str(args.get("content", ""))
        if len(content.encode("utf-8")) > self.server.max_write_bytes:
            raise ValueError(f"content exceeds max_write_bytes={self.server.max_write_bytes}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {"path": str(path.relative_to(self.server.sandbox)), "bytes": len(content.encode("utf-8"))}

    def log_message(self, fmt, *args):
        if self.server.quiet:
            return
        super().log_message(fmt, *args)


def create_server(
    host=DEFAULT_HOST,
    port=DEFAULT_PORT,
    sandbox=None,
    presets=None,
    delay=2.0,
    jitter=0.32,
    character_delay=0.06,
    speed_factor=1.0,
    default_max_activity_events=16,
    continuous_stream=False,
    simulate_tools=False,
    native_tools=False,
    max_write_bytes=200_000,
    quiet=False,
):
    server = ThreadingHTTPServer((host, port), MockAgentServer)
    server.sandbox = Path(sandbox or (Path.cwd() / ".agent-nonsense-sandbox")).resolve()
    server.sandbox.mkdir(parents=True, exist_ok=True)
    server.delay = max(0, delay)
    server.jitter = jitter
    server.character_delay = max(0, character_delay)
    server.default_speed_factor = speed_factor
    server.default_max_activity_events = default_max_activity_events
    server.continuous_stream = continuous_stream
    server.simulate_tools = simulate_tools
    server.native_tools = native_tools
    server.max_write_bytes = max_write_bytes
    server.quiet = quiet
    server.presets = load_presets(presets)
    server.jobs = {}
    server.jobs_lock = threading.Lock()
    return server


def build_argument_parser():
    parser = argparse.ArgumentParser(description="Agent Nonsense zero-token API simulator")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=os.environ.get("AGENT_NONSENSE_PORT", str(DEFAULT_PORT)))
    parser.add_argument("--sandbox", default=str(Path.cwd() / ".agent-nonsense-sandbox"))
    parser.add_argument("--presets", default=str(Path(__file__).with_name("presets.json")), help="JSON file containing long scripted conversations")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between streaming progress chunks")
    parser.add_argument("--jitter", type=float, default=0.32, help="Maximum additional random delay in seconds (0 to 0.9)")
    parser.add_argument("--character-delay", type=float, default=0.06, help="Delay between streamed text characters")
    parser.add_argument("--speed-factor", type=float, default=1.0, help="Default activity speed; greater than 1 is faster")
    parser.add_argument("--default-max-activity-events", type=int, default=16)
    parser.add_argument("--continuous-stream", action="store_true", help="Keep compatible streaming requests open until the client disconnects")
    parser.add_argument("--simulate-tools", action="store_true", help="Run sandbox file tools inside compatible chat streams")
    parser.add_argument("--native-tools", action="store_true", help="Emit native Responses function-call events; requires a client tool loop")
    parser.add_argument("--max-write-bytes", type=int, default=200_000)
    parser.add_argument("--quiet", action="store_true")
    return parser


def main():
    parser = build_argument_parser()
    args = parser.parse_args()

    if args.speed_factor <= 0:
        parser.error("--speed-factor must be a positive number")
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if args.delay < 0:
        parser.error("--delay must be zero or greater")
    if args.character_delay < 0:
        parser.error("--character-delay must be zero or greater")
    if not 0 <= args.jitter <= 0.9:
        parser.error("--jitter must be between 0 and 0.9")
    if args.default_max_activity_events <= 0:
        parser.error("--default-max-activity-events must be positive")

    server = create_server(
        host=args.host,
        port=args.port,
        sandbox=args.sandbox,
        presets=args.presets,
        delay=args.delay,
        jitter=args.jitter,
        character_delay=args.character_delay,
        speed_factor=args.speed_factor,
        default_max_activity_events=args.default_max_activity_events,
        continuous_stream=args.continuous_stream,
        simulate_tools=args.simulate_tools,
        native_tools=args.native_tools,
        max_write_bytes=args.max_write_bytes,
        quiet=args.quiet,
    )

    print(f"agent-nonsense listening on http://{args.host}:{args.port}")
    print(f"sandbox: {server.sandbox.resolve()}")
    stream_mode = "continuous compatible streams" if server.continuous_stream else "finite compatible streams"
    tool_mode = "sandbox tools enabled" if server.simulate_tools else "sandbox tools opt-in"
    if server.native_tools:
        tool_mode += "; native tool loop"
    print(f"mode: local zero-token simulator; upstream calls: 0; {stream_mode}; {tool_mode}; presets: {len(server.presets)}")
    server.serve_forever()


if __name__ == "__main__":
    main()
