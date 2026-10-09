import json
import tempfile
import unittest
import sys
from unittest.mock import patch
from pathlib import Path

from agent_nonsense.desktop.models import (
    BUILTIN_PRESETS, SSEDecoder, ServerConfig, event_text, preview_request, validate_presets,
)


class DesktopModelsTestCase(unittest.TestCase):
    def test_source_and_frozen_server_commands_preserve_paths_and_arguments(self):
        with tempfile.TemporaryDirectory(prefix="Doupi install ") as directory:
            config = ServerConfig.load(Path(directory) / "settings.json", directory)
            executable, arguments = config.launch_command()
            self.assertEqual(executable, sys.executable)
            self.assertEqual(arguments[:3], ["-u", "-m", "agent_nonsense"])
            for target in ("win32", "darwin", "linux"):
                with self.subTest(platform=target):
                    frozen = Path(directory) / ("Doupi.exe" if target == "win32" else "Doupi")
                    with patch.object(sys, "frozen", True, create=True), patch.object(sys, "executable", str(frozen)), patch.object(sys, "platform", target):
                        executable, arguments = config.launch_command()
                    self.assertEqual(executable, str(frozen.with_name("doupi-server.exe") if target == "win32" else frozen))
                    self.assertEqual(arguments[0], "--doupi-server")
                    self.assertNotIn("-m", arguments)
                    self.assertEqual(arguments[arguments.index("--sandbox") + 1], str(Path(directory) / "sandbox"))

    def test_configuration_round_trip_and_argument_mapping(self):
        with tempfile.TemporaryDirectory(prefix="豆皮 ") as directory:
            path = Path(directory) / "settings.json"
            config = ServerConfig.load(path, directory)
            config.port = 9812
            config.native_tools = True
            config.save(path)
            restored = ServerConfig.load(path, directory)
            self.assertEqual(restored, config)
            args = restored.arguments()
            self.assertEqual(args[args.index("--sandbox") + 1], str(Path(directory) / "sandbox"))
            self.assertIn("--continuous-stream", args)
            self.assertIn("--native-tools", args)
            self.assertEqual(args[args.index("--host") + 1], "127.0.0.1")

    def test_invalid_configuration_is_rejected_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            config = ServerConfig.load(path, directory)
            config.save(path)
            original = path.read_bytes()
            for key, value in (("port", 0), ("port", 12.3), ("delay", -1),
                               ("jitter", 1), ("speed_factor", float("nan")),
                               ("simulate_tools", "false"), ("sandbox", "")):
                with self.subTest(key=key, value=value):
                    broken = ServerConfig.load(path, directory)
                    setattr(broken, key, value)
                    with self.assertRaises(ValueError):
                        broken.save(path)
                    self.assertEqual(path.read_bytes(), original)

    def test_sse_decodes_every_byte_boundary_and_multiple_data_lines(self):
        wire = ': keepalive\r\ndata: {"delta": "豆皮🌱"}\r\n\r\ndata: first\ndata: second\n\ndata: [DONE]\n\n'.encode()
        for step in (1, 2, 7, len(wire)):
            with self.subTest(step=step):
                parser = SSEDecoder()
                output = []
                for index in range(0, len(wire), step):
                    output += parser.feed(wire[index:index + step])
                output += parser.feed(b"", final=True)
                self.assertEqual(output, ['{"delta": "豆皮🌱"}', "first\nsecond", "[DONE]"])

    def test_sse_flushes_unterminated_final_event(self):
        self.assertEqual(SSEDecoder().feed(b"data: last", final=True), ["last"])

    def test_sse_large_coalesced_batch_preserves_order_and_partial_tail(self):
        events = [json.dumps({"index": i, "delta": "豆皮" * 128 + "🌱"}, ensure_ascii=False) for i in range(12000)]
        parser = SSEDecoder()
        wire = ("".join("data: " + event + "\r\n\r\n" for event in events) + "data: 最后").encode()
        self.assertEqual(parser.feed(wire), events)
        self.assertEqual(parser.feed("一个事件\n\n".encode(), final=True), ["最后一个事件"])

    def test_request_and_text_mapping_for_all_protocols(self):
        for protocol, path in (("Responses", "/v1/responses"), ("Messages", "/v1/messages"),
                               ("Chat Completions", "/v1/chat/completions")):
            result, body = preview_request(protocol, "豆皮", "python-file-io", False, 2)
            self.assertEqual(result, path)
            self.assertFalse(body["continuous"])
            self.assertFalse(body["native_tools"])
            self.assertEqual(body["preset"], "python-file-io")
        for event in ({"type": "response.output_text.delta", "delta": "豆皮"},
                      {"type": "content_block_delta", "delta": {"text": "豆皮"}},
                      {"choices": [{"delta": {"content": "豆皮"}}]}):
            self.assertEqual(event_text(event), "豆皮")

    def test_presets_require_unique_ids_and_valid_tool_boundaries(self):
        text = BUILTIN_PRESETS.read_text(encoding="utf-8")
        self.assertEqual(len(validate_presets(text)["presets"]), 10)
        for change in ("duplicate", "tool", "module", "empty", "keywords"):
            payload = json.loads(text)
            if change == "duplicate":
                payload["presets"][1]["id"] = payload["presets"][0]["id"]
            elif change == "empty":
                payload["presets"][0]["steps"] = []
            elif change == "keywords":
                payload["presets"][0]["keywords"] = "bad"
            else:
                payload["presets"][0]["steps"][0][change] = "shell_exec"
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_presets(json.dumps(payload))
