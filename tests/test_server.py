import json
import os
import socket
import subprocess
import sys
from itertools import islice
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from agent_nonsense.server import MockAgentServer, build_argument_parser, create_server, split_stream_text_event


class ConfigurationTestCase(unittest.TestCase):
    def test_server_startup_does_not_require_reverse_dns(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch("socket.getfqdn", side_effect=RuntimeError("Resolver unavailable")):
                with create_server(host="127.0.0.1", port=0, sandbox=directory) as server:
                    self.assertEqual(server.server_name, "127.0.0.1")
                    self.assertEqual(server.server_port, server.server_address[1])
                    self.assertGreater(server.server_port, 0)

    def test_startup_readiness_is_flushed_without_unbuffered_python(self):
        with tempfile.TemporaryDirectory() as directory:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            environment = dict(os.environ)
            environment.pop("PYTHONUNBUFFERED", None)
            process = subprocess.Popen(
                [sys.executable, "-m", "agent_nonsense", "--port", str(port), "--sandbox", directory],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", env=environment,
            )
            lines = []
            reader = threading.Thread(target=lambda: lines.append(process.stdout.readline()), daemon=True)
            try:
                reader.start()
                reader.join(timeout=5)
                self.assertTrue(lines, "Server did not announce readiness")
                self.assertIn(f"listening on http://127.0.0.1:{port}", lines[0])
            finally:
                process.terminate()
                process.wait(timeout=5)
                reader.join(timeout=2)
                process.stdout.close()

    def test_port_can_come_from_environment_or_command_line(self):
        with mock.patch.dict("os.environ", {"AGENT_NONSENSE_PORT": "9901"}):
            parser = build_argument_parser()
            self.assertEqual(parser.parse_args([]).port, 9901)
            self.assertEqual(parser.parse_args(["--port", "9902"]).port, 9902)
            self.assertEqual(parser.parse_args([]).character_delay, 0.06)
            self.assertEqual(parser.parse_args(["--character-delay", "0.12"]).character_delay, 0.12)

    def test_all_compatible_protocols_split_visible_text(self):
        responses = list(split_stream_text_event({"type": "response.output_text.delta", "delta": "AB"}))
        chat = list(
            split_stream_text_event(
                {
                    "object": "chat.completion.chunk",
                    "choices": [{"delta": {"content": "AB"}}],
                }
            )
        )
        claude = list(
            split_stream_text_event(
                {
                    "type": "content_block_delta",
                    "delta": {"type": "text_delta", "text": "AB"},
                }
            )
        )
        self.assertEqual("".join(item[0]["delta"] for item in responses), "AB")
        self.assertEqual("".join(item[0]["choices"][0]["delta"]["content"] for item in chat), "AB")
        self.assertEqual("".join(item[0]["delta"]["text"] for item in claude), "AB")
        for chunks in (responses, chat, claude):
            self.assertEqual([item[2] for item in chunks], [False, True])


class ServerTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.server = create_server(
            host="127.0.0.1",
            port=0,
            sandbox=self.tempdir.name,
            delay=0,
            jitter=0,
            character_delay=0,
            speed_factor=100,
            default_max_activity_events=3,
            simulate_tools=True,
            quiet=True,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.tempdir.cleanup()

    def request(self, path, payload=None):
        data = None
        headers = {}
        method = "GET"
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
            method = "POST"
        request = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.headers, response.read().decode("utf-8")

    def response_stream_events(self, raw):
        events = []
        for line in raw.splitlines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            event = json.loads(line[6:])
            if event.get("type") == "response.output_text.delta":
                events.append(event)
        return events

    def test_health_and_models(self):
        status, headers, raw = self.request("/health")
        self.assertEqual(status, 200)
        self.assertEqual(headers["X-Token-Usage"], "0")
        self.assertEqual(json.loads(raw)["token_usage"], 0)

        _, _, raw = self.request("/v1/models")
        models = json.loads(raw)
        self.assertEqual(models["data"][0]["id"], "agent-nonsense")
        self.assertEqual(models["data"][1]["id"], "mock-agent")

    def test_openai_chat_completion_uses_zero_tokens(self):
        _, _, raw = self.request(
            "/v1/chat/completions",
            {"model": "agent-nonsense", "messages": [{"role": "user", "content": "检查文件"}]},
        )
        response = json.loads(raw)
        self.assertEqual(response["usage"]["total_tokens"], 0)
        self.assertIn("## 当前工作状态", response["choices"][0]["message"]["content"])
        self.assertNotIn("SIMULATED:", response["choices"][0]["message"]["content"])

    def test_responses_stream_contains_tools_and_completion(self):
        _, _, raw = self.request(
            "/v1/responses",
            {
                "model": "agent-nonsense",
                "stream": True,
                "continuous": False,
                "max_activity_events": 3,
                "preset": "python-file-io",
                "simulate_tools": True,
                "input": "检查 Python 文件读写",
            },
        )
        self.assertIn("response.output_text.delta", raw)
        text = "".join(event["delta"] for event in self.response_stream_events(raw))
        self.assertIn("tool.call name=", text)
        self.assertIn("tool.result name=", text)
        self.assertIn("### 阶段", text)
        self.assertIn("```text", text)
        self.assertNotIn("剧本", text)
        self.assertNotIn("SIMULATED:", text)
        self.assertIn("response.completed", raw)
        self.assertNotIn("data: [DONE]", raw)

    def test_each_message_can_choose_a_different_random_task(self):
        first_preset, second_preset = self.server.presets[:2]
        with mock.patch("agent_nonsense.server.random.choice", side_effect=[first_preset, second_preset]):
            _, _, first_raw = self.request(
                "/v1/chat/completions",
                {"model": "agent-nonsense", "messages": [{"role": "user", "content": "检查 Python 文件"}]},
            )
            _, _, second_raw = self.request(
                "/v1/chat/completions",
                {"model": "agent-nonsense", "messages": [{"role": "user", "content": "检查 Python 文件"}]},
            )
        first_content = json.loads(first_raw)["choices"][0]["message"]["content"]
        second_content = json.loads(second_raw)["choices"][0]["message"]["content"]
        self.assertIn(first_preset["closing"], first_content)
        self.assertIn(second_preset["closing"], second_content)
        self.assertNotEqual(first_content, second_content)

    def test_random_requests_never_immediately_repeat(self):
        self.server.presets = self.server.presets[:2]
        # Always take the first available candidate: exclusion, rather than luck,
        # must make consecutive random requests different.
        with mock.patch("agent_nonsense.server.random.choice", side_effect=lambda items: items[0]):
            for index in range(6):
                _, _, raw = self.request(
                    "/v1/chat/completions",
                    {"messages": [{"role": "user", "content": "相同问题"}]},
                )
                content = json.loads(raw)["choices"][0]["message"]["content"]
                self.assertIn(self.server.presets[index % 2]["closing"], content)

    def test_continuous_random_rotation_for_every_protocol(self):
        self.server.presets = [
            {"id": "a", "title": "任务 A", "steps": [{"text": "A1"}, {"text": "A2"}]},
            {"id": "b", "title": "任务 B", "steps": [{"text": "B1"}, {"text": "B2"}]},
        ]
        handler = object.__new__(MockAgentServer)
        handler.server = self.server
        for method in (handler.responses_stream_events, handler.openai_stream_events, handler.claude_stream_events):
            with self.subTest(protocol=method.__name__):
                self.server.last_random_preset_id = None
                with mock.patch("agent_nonsense.server.random.choice", side_effect=lambda items: items[0]):
                    source = method({"simulate_tools": False}, "", [], 3, True)
                    stages, selected = [], []
                    for event in source:
                        if event.get("type") == "response.output_text.delta":
                            stages.append(event["delta"].strip())
                        elif event.get("object") == "chat.completion.chunk":
                            stages.append(event["choices"][0]["delta"]["content"].strip())
                        elif event.get("type") == "content_block_delta":
                            stages.append(event["delta"]["text"].strip())
                        preset = event.get("agent_nonsense", {}).get("preset")
                        if preset:
                            selected.append(preset["id"])
                        if len(stages) == 6:
                            break
                    source.close()
                self.assertEqual(stages, ["A1", "A2", "B1", "B2", "A1", "A2"])
                self.assertEqual(selected, ["a", "b", "a"])

    def test_explicit_and_single_presets_keep_streaming(self):
        self.server.presets = [
            {"id": "a", "steps": [{"text": "A1"}, {"text": "A2"}]},
            {"id": "b", "steps": [{"text": "B1"}]},
        ]
        handler = object.__new__(MockAgentServer)
        handler.server = self.server
        body = {"preset": "A", "simulate_tools": False}
        source = handler.conversation_events(body, "", [], 3, True)
        self.assertEqual([e["text"] for e in islice(source, 6)], ["A1", "A2"] * 3)
        source.close()
        self.server.presets = self.server.presets[:1]
        source = handler.conversation_events({"simulate_tools": False}, "", [], 3, True)
        self.assertEqual([e["text"] for e in islice(source, 6)], ["A1", "A2"] * 3)
        source.close()

    def test_finite_random_stream_keeps_selected_preset_and_closing(self):
        self.server.presets = [
            {"id": "a", "closing": "任务 A 结束", "steps": [{"text": "A1"}]},
            {"id": "b", "closing": "任务 B 结束", "steps": [{"text": "B1"}]},
        ]
        handler = object.__new__(MockAgentServer)
        handler.server = self.server
        with mock.patch("agent_nonsense.server.random.choice", side_effect=lambda items: items[0]) as choose:
            events = list(handler.responses_stream_events({"simulate_tools": False}, "", [], 3, False))
        self.assertEqual(choose.call_count, 1)
        text = "".join(e["delta"] for e in events if e.get("type") == "response.output_text.delta")
        self.assertIn("A1\nA1\nA1\n", text)
        self.assertIn("任务 A 结束", text)
        self.assertNotIn("B1", text)

    def test_stream_jitter_never_precedes_base_delay(self):
        self.server.delay = 2.0
        self.server.jitter = 0.32
        with mock.patch("agent_nonsense.server.time.sleep") as sleep:
            self.request(
                "/v1/responses",
                {
                    "model": "agent-nonsense",
                    "stream": True,
                    "continuous": False,
                    "max_activity_events": 2,
                    "speed_factor": 1.0,
                    "input": "检查文件",
                },
            )
        intervals = [call.args[0] for call in sleep.call_args_list]
        self.assertTrue(intervals)
        self.assertTrue(all(2.0 <= interval <= 2.32 for interval in intervals))

    def test_stream_text_is_emitted_character_by_character(self):
        self.server.delay = 0
        self.server.character_delay = 0.06
        with mock.patch("agent_nonsense.server.time.sleep") as sleep:
            _, _, raw = self.request(
                "/v1/responses",
                {
                    "model": "agent-nonsense",
                    "stream": True,
                    "continuous": False,
                    "max_activity_events": 1,
                    "speed_factor": 1.0,
                    "input": "检查文件",
                },
            )
        delta_events = self.response_stream_events(raw)
        self.assertGreater(len(delta_events), 100)
        self.assertTrue(all(len(event["delta"]) == 1 for event in delta_events))
        character_sleeps = [call.args[0] for call in sleep.call_args_list]
        self.assertGreater(len(character_sleeps), 100)
        self.assertTrue(all(interval == 0.06 for interval in character_sleeps))

    def test_claude_stream_completes(self):
        _, _, raw = self.request(
            "/v1/messages",
            {
                "model": "agent-nonsense",
                "stream": True,
                "continuous": False,
                "max_activity_events": 2,
                "messages": [{"role": "user", "content": "API 超时"}],
            },
        )
        self.assertIn("content_block_delta", raw)
        self.assertIn("message_stop", raw)
        self.assertNotIn("data: [DONE]", raw)

    def test_tool_roundtrip_and_path_escape(self):
        _, _, raw = self.request(
            "/tools/call",
            {"name": "write_file", "arguments": {"path": "notes/test.txt", "content": "hello"}},
        )
        self.assertTrue(json.loads(raw)["ok"])

        _, _, raw = self.request(
            "/tools/call",
            {"name": "read_file", "arguments": {"path": "notes/test.txt"}},
        )
        self.assertEqual(json.loads(raw)["result"]["content"], "hello")

        request = urllib.request.Request(
            self.base_url + "/tools/call",
            data=json.dumps({"name": "read_file", "arguments": {"path": "../outside.txt"}}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as context:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(context.exception.code, 403)

    def test_unknown_route_returns_json(self):
        request = urllib.request.Request(self.base_url + "/missing")
        with self.assertRaises(urllib.error.HTTPError) as context:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(context.exception.code, 404)
        self.assertEqual(context.exception.headers.get_content_type(), "application/json")

    def test_continuous_stream_can_be_disconnected(self):
        request = urllib.request.Request(
            self.base_url + "/v1/responses",
            data=json.dumps({"model": "agent-nonsense", "stream": True, "continuous": True, "input": "hi"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        response = urllib.request.urlopen(request, timeout=5)
        first_event = response.readline().decode("utf-8")
        response.close()
        self.assertIn("response.created", first_event)
        status, _, _ = self.request("/health")
        self.assertEqual(status, 200)


if __name__ == "__main__":
    unittest.main()
