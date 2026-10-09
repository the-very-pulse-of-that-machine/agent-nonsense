"""Configuration and wire-format helpers, independent of Qt."""
import codecs
import json
import math
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from agent_nonsense.server import ACTIVITY_MODULES

BUILTIN_PRESETS = Path(__file__).resolve().parents[1] / "presets.json"


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@dataclass
class ServerConfig:
    port: int = 8787
    delay: float = 2.0
    jitter: float = 0.32
    character_delay: float = 0.06
    speed_factor: float = 1.0
    max_events: int = 16
    continuous: bool = True
    simulate_tools: bool = True
    native_tools: bool = False
    sandbox: str = ""
    presets: str = ""

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.port}"

    def validate(self):
        for name, low, high in (
            ("port", 1, 65535), ("delay", 0, 3600), ("jitter", 0, 0.9),
            ("character_delay", 0, 60), ("speed_factor", 0.01, 1000),
            ("max_events", 1, 10000),
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} 必须为数字")
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"{name} 必须在 {low}–{high} 之间")
        if not isinstance(self.port, int) or not isinstance(self.max_events, int):
            raise ValueError("端口和事件数必须为整数")
        for name in ("continuous", "simulate_tools", "native_tools"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} 必须为布尔值")
        if not isinstance(self.sandbox, str) or not self.sandbox.strip():
            raise ValueError("请选择 sandbox 目录")
        if not isinstance(self.presets, str) or not self.presets.strip():
            raise ValueError("请选择预设文件")
        validate_presets(Path(self.presets).read_text(encoding="utf-8"))
        return self

    def arguments(self):
        self.validate()
        args = ["-u", "-m", "agent_nonsense", "--host", "127.0.0.1"]
        for flag, value in (
            ("port", self.port), ("delay", self.delay), ("jitter", self.jitter),
            ("character-delay", self.character_delay), ("speed-factor", self.speed_factor),
            ("default-max-activity-events", self.max_events),
            ("sandbox", self.sandbox), ("presets", self.presets),
        ):
            args.extend(["--" + flag, str(value)])
        for enabled, flag in ((self.continuous, "continuous-stream"),
                              (self.simulate_tools, "simulate-tools"),
                              (self.native_tools, "native-tools")):
            if enabled:
                args.append("--" + flag)
        return args

    def launch_command(self):
        arguments = self.arguments()
        if getattr(sys, "frozen", False):
            executable = Path(sys.executable)
            if sys.platform == "win32":
                executable = executable.with_name("doupi-server.exe")
            return str(executable), ["--doupi-server", *arguments[3:]]
        return sys.executable, arguments

    def save(self, path):
        self.validate()
        atomic_write(path, json.dumps(asdict(self), ensure_ascii=False, indent=2) + "\n")

    @classmethod
    def load(cls, path, data_dir):
        defaults = cls(sandbox=str(Path(data_dir) / "sandbox"), presets=str(BUILTIN_PRESETS))
        path = Path(path)
        if not path.exists():
            return defaults
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("配置文件必须为 JSON 对象")
        values = asdict(defaults)
        values.update({f.name: payload[f.name] for f in fields(cls) if f.name in payload})
        return cls(**values).validate()


def validate_presets(text):
    payload = json.loads(text)
    presets = payload.get("presets") if isinstance(payload, dict) else None
    if not isinstance(presets, list) or not presets:
        raise ValueError("需要非空 presets 数组")
    seen = set()
    for preset in presets:
        if not isinstance(preset, dict):
            raise ValueError("每个预设必须为对象")
        identity = preset.get("id")
        if not isinstance(identity, str) or not identity.strip() or identity in seen:
            raise ValueError("每个预设需要唯一且非空的 id")
        seen.add(identity)
        for key in ("title", "question", "closing"):
            if not isinstance(preset.get(key), str) or not preset[key].strip():
                raise ValueError(f"{identity} 缺少 {key}")
        keywords = preset.get("keywords")
        if not isinstance(keywords, list) or not keywords or not all(isinstance(k, str) and k.strip() for k in keywords):
            raise ValueError(f"{identity} 需要非空 keywords 字符串数组")
        steps = preset.get("steps")
        if not isinstance(steps, list) or not steps:
            raise ValueError(f"{identity} 缺少 steps")
        for step in steps:
            if not isinstance(step, dict) or step.get("module") not in ACTIVITY_MODULES:
                raise ValueError(f"{identity} 包含未知 module")
            if not isinstance(step.get("text"), str) or not step["text"].strip():
                raise ValueError(f"{identity} 包含空步骤")
            if step.get("tool") not in (None, "list_files", "read_file", "write_file"):
                raise ValueError(f"{identity} 包含未知 tool")
    return payload


class SSEDecoder:
    """Incremental UTF-8 / SSE decoder, including split code points and CRLF."""
    def __init__(self):
        self.decoder = codecs.getincrementaldecoder("utf-8")()
        self.buffer = ""
        self.data = []

    def feed(self, chunk, final=False):
        self.buffer += self.decoder.decode(chunk, final=final)
        result = []
        # Split each received batch once. Repeatedly copying the remaining
        # buffer becomes quadratic when fast streams deliver large batches.
        lines = self.buffer.split("\n")
        self.buffer = lines.pop()
        for line in lines:
            line = line.removesuffix("\r")
            if not line:
                if self.data:
                    result.append("\n".join(self.data))
                    self.data.clear()
            elif line.startswith("data:"):
                self.data.append(line[5:].removeprefix(" "))
        if final:
            if self.buffer.startswith("data:"):
                self.data.append(self.buffer[5:].removeprefix(" "))
            self.buffer = ""
            if self.data:
                result.append("\n".join(self.data))
                self.data.clear()
        return result


def event_text(event):
    if event.get("type") == "response.output_text.delta":
        return event.get("delta", "")
    if event.get("type") == "content_block_delta":
        return event.get("delta", {}).get("text", "")
    choices = event.get("choices") or []
    if choices:
        return choices[0].get("delta", {}).get("content", "")
    if str(event.get("type", "")).startswith("agent."):
        return event.get("text", "")
    return ""


def preview_request(protocol, prompt, preset="", continuous=False, max_events=3):
    body = {"model": "agent-nonsense", "stream": True, "continuous": continuous,
            "native_tools": False, "max_activity_events": max_events}
    if preset:
        body["preset"] = preset
    if protocol == "Responses":
        body["input"] = prompt
        return "/v1/responses", body
    body["messages"] = [{"role": "user", "content": prompt}]
    if protocol == "Messages":
        body["max_tokens"] = 2048
        return "/v1/messages", body
    return "/v1/chat/completions", body
