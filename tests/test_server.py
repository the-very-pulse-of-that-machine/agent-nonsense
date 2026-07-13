import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from agent_nonsense.server import build_argument_parser, create_server, split_stream_text_event


class ConfigurationTestCase(unittest.TestCase):
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
