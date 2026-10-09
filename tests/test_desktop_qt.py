"""Real offscreen Qt/process/HTTP integration tests (optional gui extra)."""
import os
import socket
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QProcess, QTimer
    from PySide6.QtWidgets import QApplication
    from agent_nonsense.desktop.window import MainWindow
    from agent_nonsense.desktop.theme import STYLE
except ModuleNotFoundError as exc:
    if not exc.name or not exc.name.startswith("PySide6"):
        raise
    QApplication = None


@unittest.skipIf(QApplication is None, "Install .[gui] to run desktop integration tests")
class DesktopQtTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="豆皮 UI ")
        self.window = MainWindow(self.directory.name)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.window.port.setValue(port)
        self.window.delay.setValue(0.02)
        self.window.jitter.setValue(0)
        self.window.character_delay.setValue(0)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.preset_dirty = False
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.directory.cleanup()

    def wait_for(self, predicate, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return
            # Yield between bounded event drains so a continuous SSE stream
            # cannot keep a nested Qt test event loop busy past the deadline.
            time.sleep(0.02)
        backend = self.window.backend
        diagnostics = f"state={backend.state}, process={backend.process.state()}, pid={backend.process.processId()}, ready={backend._ready}"
        if backend.config and backend.process.state() == QProcess.ProcessState.Running:
            import urllib.request
            try:
                with urllib.request.urlopen(backend.config.base_url + "/health", timeout=0.5) as response:
                    diagnostics += ", HTTP health=" + str(response.status)
            except Exception as exc:
                diagnostics += ", HTTP health=" + str(exc)
        self.fail("Timed out; " + diagnostics + "\nChild output:\n" + backend._last_output + "\nLogs:\n" + self.window.logs.toPlainText())

    def start(self):
        self.window.toggle_server()
        self.wait_for(lambda: self.window.backend.state == "running")

    def test_real_streams_for_all_three_protocols_and_restart(self):
        self.start()
        self.assertFalse(self.window.settings_body.isEnabled())
        for protocol in ("Responses", "Chat Completions", "Messages"):
            with self.subTest(protocol=protocol):
                self.window.protocol.setCurrentText(protocol)
                self.window.preview_events.setValue(2)
                self.window.start_preview()
                self.wait_for(lambda: self.window.backend.stream is None)
                self.assertGreater(self.window.stream_chars, 100)
                self.assertIn("阶段", self.window.stream_buffer)
                self.assertIn("阶段", self.window.output.toPlainText())
                self.assertEqual(self.window.preview_status.text(), "输出已完成")
        self.window.toggle_server()
        self.wait_for(lambda: self.window.backend.state == "stopped")
        self.start()
        self.assertTrue(self.window.preview_start.isEnabled())

    def test_cancel_continuous_stream_and_close_reaps_owned_child(self):
        self.start()
        self.window.preview_continuous.setChecked(True)
        self.window.start_preview()
        self.wait_for(lambda: self.window.stream_chars > 100)
        self.window.backend.cancel_stream()
        self.assertIsNone(self.window.backend.stream)
        self.assertFalse(self.window.preview_stop.isEnabled())
        self.assertTrue(self.window.preview_start.isEnabled())
        self.window.start_preview()
        self.wait_for(lambda: self.window.stream_chars > 100)
        self.window.close()
        self.assertIsNone(self.window.backend.stream)
        self.assertEqual(self.window.backend.process.state(), QProcess.ProcessState.NotRunning)

    def test_random_resends_display_different_actual_presets_for_every_protocol(self):
        self.window.tools.setChecked(False)
        self.window.preview_events.setValue(1)
        self.start()
        selected = []
        self.window.backend.stream_preset.connect(lambda preset: selected.append(preset))
        for protocol in ("Responses", "Chat Completions", "Messages"):
            with self.subTest(protocol=protocol):
                self.window.protocol.setCurrentText(protocol)
                for _ in range(2):
                    before = len(selected)
                    self.window.start_preview()
                    self.wait_for(lambda: self.window.backend.stream is None)
                    self.assertEqual(len(selected), before + 1)
                    self.assertEqual(self.window.preset_combo.currentData(), "")
                    title = selected[-1]["title"]
                    self.assertEqual(self.window.preview_preset.text(), "当前剧本：" + title)
                    self.assertIn(title, self.window.stream_buffer)
                    if before:
                        self.assertNotEqual(selected[-1]["id"], selected[-2]["id"])

    def test_continuous_random_rotation_updates_label_without_restarting_request(self):
        import json
        payload = json.loads(self.window.preset_editor.toPlainText())
        payload["presets"] = payload["presets"][:2]
        for preset in payload["presets"]:
            preset["steps"] = preset["steps"][:1]
        self.window.preset_editor.setPlainText(json.dumps(payload, ensure_ascii=False))
        self.assertTrue(self.window.save_presets())
        self.window.tools.setChecked(False)
        self.window.delay.setValue(0.2)
        self.window.preview_continuous.setChecked(True)
        self.start()
        selected = []
        self.window.backend.stream_preset.connect(lambda preset: selected.append(preset))
        self.window.start_preview()
        reply = self.window.backend.stream
        self.wait_for(lambda: len(selected) >= 2)
        self.assertIs(self.window.backend.stream, reply)
        self.assertNotEqual(selected[0]["id"], selected[1]["id"])
        self.assertEqual(self.window.preset_combo.currentData(), "")
        self.assertEqual(self.window.preview_preset.text(), "当前剧本：" + selected[-1]["title"])
        self.wait_for(lambda: selected[-1]["title"] in self.window.stream_buffer)
        for preset in selected[:2]:
            self.assertIn(preset["title"], self.window.stream_buffer)
        self.window.backend.cancel_stream()
        self.assertEqual(self.window.preview_status.text(), "已停止输出")

    def test_background_job_lifecycle(self):
        self.window.delay.setValue(0.1)
        self.start()
        self.window.job_prompt.setText("豆皮后台任务")
        self.window.job_max.setValue(0)
        self.window.job_duration.setValue(0)
        self.window.create_job()
        self.wait_for(lambda: len(self.window.jobs) == 1)
        self.window.job_table.selectRow(0)
        self.assertTrue(self.window.stop_job_button.isEnabled())
        self.window.stop_job()
        self.wait_for(lambda: self.window.jobs[0]["status"] == "stopped")
        self.assertFalse(self.window.stop_job_button.isEnabled())

    def test_zero_delay_stream_keeps_stop_button_responsive(self):
        self.window.delay.setValue(0)
        self.window.tools.setChecked(False)
        self.window.preview_continuous.setChecked(True)
        self.start()
        self.window.start_preview()
        self.wait_for(lambda: self.window.stream_chars > 500)
        started = time.monotonic()
        QTimer.singleShot(50, self.window.preview_stop.click)
        self.wait_for(lambda: self.window.backend.stream is None, timeout=4)
        self.assertLess(time.monotonic() - started, 4)
        self.assertEqual(self.window.preview_status.text(), "已停止输出")
        self.assertLessEqual(len(self.window.stream_buffer), 60000)

    def test_selecting_dialogue_updates_question_and_clears_previous_output(self):
        import json
        presets = json.loads(self.window.preset_editor.toPlainText())["presets"]
        self.window._stream_text("上一个对话的内容")
        self.window._render_stream()
        for index, preset in enumerate(presets, 1):
            self.window.preset_combo.setCurrentIndex(index)
            self.assertEqual(self.window.prompt.toPlainText(), preset["question"])
            self.assertEqual(self.window.stream_buffer, "")
            self.assertEqual(self.window.stream_chars, 0)
            self.assertEqual(self.window.char_count.text(), "0 字符")
            self.assertEqual(self.window.output_stack.currentIndex(), 0)

    def test_switch_dialogue_during_continuous_output_replaces_old_stream(self):
        self.window.character_delay.setValue(0.001)
        self.start()
        self.window.preview_continuous.setChecked(True)
        self.window.preset_combo.setCurrentIndex(1)
        self.window.start_preview()
        self.wait_for(lambda: "排查 Python 文件读写边界" in self.window.stream_buffer)
        previous = self.window.backend.stream
        self.window.preset_combo.setCurrentIndex(2)
        self.assertIsNot(self.window.backend.stream, previous)
        self.assertTrue(self.window.preview_start.isEnabled())
        self.wait_for(lambda: "排查 API 请求超时" in self.window.stream_buffer)
        self.assertNotIn("排查 Python 文件读写边界", self.window.stream_buffer)
        self.assertIn("超时", self.window.prompt.toPlainText())
        self.window.backend.cancel_stream()
        self.assertEqual(self.window.preview_status.text(), "已停止输出")

    def test_protocol_switch_and_resend_during_stream_keep_latest_request(self):
        self.window.character_delay.setValue(0.001)
        self.start()
        self.window.preview_continuous.setChecked(True)
        self.window.start_preview()
        self.wait_for(lambda: self.window.stream_chars > 50)
        previous = self.window.backend.stream
        self.window.protocol.setCurrentText("Messages")
        self.assertIsNot(self.window.backend.stream, previous)
        self.assertEqual(self.window.backend.stream.url().path(), "/v1/messages")
        self.assertTrue(self.window.preview_start.isEnabled())
        self.window.prompt.setPlainText("切换后的新问题")
        from unittest.mock import patch
        with patch.object(self.window.backend, "start_stream", wraps=self.window.backend.start_stream) as send:
            self.window.preview_start.click()
            path, body = send.call_args.args
            self.assertEqual(path, "/v1/messages")
            self.assertEqual(body["messages"][0]["content"], "切换后的新问题")
        self.wait_for(lambda: self.window.stream_chars > 50)
        self.assertEqual(self.window.preview_status.text(), "●  正在接收…")

    def test_rapid_dialogue_switches_only_display_the_latest_topic(self):
        self.window.character_delay.setValue(0.001)
        self.start()
        self.window.preview_continuous.setChecked(True)
        self.window.start_preview()
        self.wait_for(lambda: self.window.stream_chars > 50)
        for index in range(1, self.window.preset_combo.count()):
            self.window.preset_combo.setCurrentIndex(index)
        title = self.window.preset_combo.currentText()
        self.wait_for(lambda: title in self.window.stream_buffer)
        self.assertNotIn("排查 Python 文件读写边界", self.window.stream_buffer)
        self.assertEqual(self.window.backend.stream.url().path(), "/v1/responses")

    def test_original_icon_is_packaged_and_used(self):
        import hashlib
        from agent_nonsense.desktop.widgets import ORIGINAL_ICON, app_icon
        original = Path(__file__).resolve().parents[1] / "docs/assets/agent-nonsense.ico"
        self.assertEqual(hashlib.sha256(ORIGINAL_ICON.read_bytes()).digest(),
                         hashlib.sha256(original.read_bytes()).digest())
        self.assertFalse(app_icon().isNull())

    def test_busy_port_never_adopts_or_kills_external_listener(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]
            self.window.port.setValue(port)
            self.window.toggle_server()
            self.wait_for(lambda: self.window.backend.state == "error")
            self.assertIn("已被占用", self.window.notice.text())
            self.assertIsNone(self.window.backend.started_at)
            self.window.backend.stop()
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                pass

    def test_invalid_edit_does_not_destroy_presets_or_start_server(self):
        path = Path(self.window.config.presets)
        before = path.read_bytes()
        self.window.preset_editor.setPlainText('{"presets": []}')
        self.assertFalse(self.window.save_presets())
        self.assertEqual(path.read_bytes(), before)
        self.window.toggle_server()
        self.assertEqual(self.window.backend.state, "stopped")

    def test_valid_edit_updates_preview_catalog_and_is_persisted(self):
        import json
        payload = json.loads(self.window.preset_editor.toPlainText())
        payload["presets"][0]["title"] = "豆皮自定义剧本"
        self.window.preset_editor.setPlainText(json.dumps(payload, ensure_ascii=False))
        self.assertTrue(self.window.save_presets())
        self.assertEqual(self.window.preset_combo.itemText(1), "豆皮自定义剧本")
        self.window.port.setValue(9911)
        self.assertTrue(self.window.save_settings())
        restored = MainWindow(self.directory.name)
        self.assertEqual(restored.config.port, 9911)
        self.assertEqual(restored.preset_combo.itemText(1), "豆皮自定义剧本")
        restored.close()
