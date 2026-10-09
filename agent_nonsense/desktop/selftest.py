"""Exercise the installed application without touching personal configuration."""
import json
import os
from pathlib import Path
import socket
import tempfile
import time
import traceback


def run(report_path):
    report_path = Path(report_path).resolve()
    report = {"ok": False, "checks": []}
    window = None
    try:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QProcess
        from PySide6.QtWidgets import QApplication
        from .models import BUILTIN_PRESETS
        from .theme import STYLE
        from .widgets import app_icon
        from .window import MainWindow

        original = BUILTIN_PRESETS.read_bytes()
        app = QApplication.instance() or QApplication([])
        app.setStyle("Fusion")
        app.setStyleSheet(STYLE)

        def wait(predicate):
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                app.processEvents()
                if predicate():
                    return
                time.sleep(0.01)
            raise RuntimeError("Application timed out:\n" + window.logs.toPlainText())

        with tempfile.TemporaryDirectory(prefix="Doupi installed test ") as directory:
            window = MainWindow(directory)
            window.show()
            assert not app_icon().isNull(), "Missing original icon"
            assert len(window.preset_ids) >= 2, "Missing bundled presets"
            report["checks"].append("original icon and bundled presets")
            payload = json.loads(window.preset_editor.toPlainText())
            payload["presets"] = payload["presets"][:2]
            for preset in payload["presets"]:
                preset["steps"] = preset["steps"][:1]
            window.preset_editor.setPlainText(json.dumps(payload, ensure_ascii=False))
            assert window.save_presets(), "Cannot save personal presets"
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                window.port.setValue(sock.getsockname()[1])
            window.delay.setValue(0.1)
            window.jitter.setValue(0)
            window.character_delay.setValue(0)
            window.tools.setChecked(False)
            window.toggle_server()
            wait(lambda: window.backend.state == "running")
            report["checks"].append("owned bundled server startup and health")
            window.preview_events.setValue(1)
            for protocol in ("Responses", "Chat Completions", "Messages"):
                window.protocol.setCurrentText(protocol)
                window.start_preview()
                wait(lambda: window.backend.stream is None)
                assert window.stream_chars > 100, "Empty stream: " + protocol
                assert window.preview_status.text() == "输出已完成", window.preview_status.text()
                assert "当前剧本：" in window.preview_preset.text()
                report["checks"].append(protocol + " HTTP/SSE preview")
            selected = []
            window.backend.stream_preset.connect(lambda preset: selected.append(preset))
            window.preview_continuous.setChecked(True)
            window.start_preview()
            reply = window.backend.stream
            wait(lambda: len(selected) >= 2)
            assert selected[0]["id"] != selected[1]["id"], "Random rotation repeated"
            assert window.backend.stream is reply, "Rotation restarted the connection"
            assert window.preset_combo.currentData() == "", "Random mode became pinned"
            window.preview_stop.click()
            assert window.preview_status.text() == "已停止输出"
            report["checks"].append("continuous random rotation and cancellation")
            window.close()
            app.processEvents()
            assert window.backend.process.state() == QProcess.ProcessState.NotRunning
            assert window.backend.stream is None
            assert BUILTIN_PRESETS.read_bytes() == original, "Changed installed resources"
            report["checks"].append("child cleanup and read-only install resources")
        report["ok"] = True
    except Exception:
        report["error"] = traceback.format_exc()
    finally:
        if window is not None:
            window.preset_dirty = False
            window.close()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
