"""Asynchronous loopback client and owned server-process lifecycle."""
import json
import socket
import time
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkProxy, QNetworkReply, QNetworkRequest

from .models import SSEDecoder, event_text


class Backend(QObject):
    state_changed = Signal(str)
    log = Signal(str)
    error = Signal(str)
    health = Signal(dict)
    stream_text = Signal(str)
    stream_preset = Signal(dict)
    stream_finished = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = "stopped"
        self.config = None
        self.started_at = None
        self.network = QNetworkAccessManager(self)
        self.network.setProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))
        self.process = QProcess(self)
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("PYTHONIOENCODING", "utf-8")
        environment.insert("PYTHONUNBUFFERED", "1")
        self.process.setProcessEnvironment(environment)
        self.process.setWorkingDirectory(str(Path(__file__).resolve().parents[2]))
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._output)
        self.process.finished.connect(self._exited)
        self.process.errorOccurred.connect(self._process_error)
        self.replies = set()
        self.stream = None
        self._decoder = None
        self._ready = False
        self._output_buffer = ""
        self._last_output = ""
        self._probing = False
        self._launch_time = 0
        self._closing = False
        self.monitor = QTimer(self)
        self.monitor.setInterval(400)
        self.monitor.timeout.connect(self._poll)
        self.kill_timer = QTimer(self)
        self.kill_timer.setSingleShot(True)
        self.kill_timer.timeout.connect(self.process.kill)

    def _set_state(self, state):
        self.state = state
        self.state_changed.emit(state)

    def start(self, config):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            return
        try:
            executable, arguments = config.launch_command()
        except (ValueError, OSError) as exc:
            self.error.emit(str(exc))
            return
        self.config = replace(config)
        # A TCP-only preflight gives the same occupied-port message on Windows,
        # where binding an existing listener can report WSAEACCES (10013).
        try:
            with socket.socket() as probe:
                probe.settimeout(0.1)
                if probe.connect_ex(("127.0.0.1", config.port)) == 0:
                    self._set_state("error")
                    self.error.emit(f"端口 {config.port} 已被占用，请更换端口后重试。")
                    return
        except OSError:
            pass
        self._ready = False
        self._output_buffer = self._last_output = ""
        self._launch_time = time.monotonic()
        self._set_state("starting")
        self.process.start(executable, arguments)
        self.monitor.setInterval(400)
        self.monitor.start()

    def _output(self):
        text = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._last_output = (self._last_output + text)[-8000:]
        self._output_buffer += text
        while "\n" in self._output_buffer:
            line, self._output_buffer = self._output_buffer.split("\n", 1)
            self.log.emit(line.rstrip())
            # Only our child's startup message authorizes a health probe. A different
            # server occupying the port must never be adopted or terminated.
            if line.startswith("agent-nonsense listening on "):
                self._ready = True

    def _poll(self):
        if self.state == "starting" and time.monotonic() - self._launch_time > 10:
            self.error.emit("服务启动超时，请查看运行日志。")
            self.stop()
            return
        if self.state not in ("starting", "running") or not self._ready or self._probing:
            return
        self._probing = True

        def succeeded(payload):
            self._probing = False
            if self.state not in ("starting", "running"):
                return
            if payload.get("ok") and payload.get("service") == "agent-nonsense":
                if self.state == "starting":
                    self.started_at = time.monotonic()
                    self._set_state("running")
                    self.monitor.setInterval(2000)
                self.health.emit(payload)
            else:
                failed("健康检查返回了未知服务")

        def failed(message):
            self._probing = False
            if self.state == "running":
                self.error.emit("健康检查失败：" + message)
                self.stop()

        self.request("/health", callback=succeeded, on_error=failed)

    def _process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.monitor.stop()
            self._set_state("error")
            self.error.emit("无法启动 Python 服务：" + self.process.errorString())

    def _exited(self, code, _status):
        self._output()
        self.monitor.stop()
        self.kill_timer.stop()
        self._probing = False
        self.started_at = None
        expected = self.state == "stopping" or self._closing
        self._abort_requests()
        self._set_state("stopped" if expected or code == 0 else "error")
        if not expected and code != 0:
            occupied = any(s in self._last_output.lower() for s in
                           ("address already in use", "winerror 10048", "errno 48", "errno 98"))
            message = (f"端口 {self.config.port} 已被占用，请更换端口后重试。" if occupied
                       else "服务意外退出，请查看运行日志。")
            self.error.emit(message)

    def stop(self):
        self.monitor.stop()
        self._abort_requests()
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self._set_state("stopped")
            return
        self._set_state("stopping")
        self.process.terminate()
        self.kill_timer.start(1500)

    def shutdown(self):
        self._closing = True
        self.stop()
        if not self.process.waitForFinished(1500):
            self.process.kill()
            self.process.waitForFinished(1000)
        self.kill_timer.stop()

    def _abort_requests(self):
        self.cancel_stream()
        for reply in list(self.replies):
            reply.abort()

    def request(self, path, payload=None, callback=None, on_error=None):
        if self.config is None:
            return None
        request = QNetworkRequest(QUrl(self.config.base_url + path))
        request.setTransferTimeout(3000)
        if payload is None:
            reply = self.network.get(request)
        else:
            request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json; charset=utf-8")
            reply = self.network.post(request, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        self.replies.add(reply)

        def finished():
            self.replies.discard(reply)
            try:
                if reply.error() == QNetworkReply.NetworkError.OperationCanceledError:
                    if on_error:
                        on_error("请求已取消")
                    return
                if reply.error() != QNetworkReply.NetworkError.NoError:
                    (on_error or self.error.emit)(reply.errorString())
                    return
                data = json.loads(bytes(reply.readAll()).decode("utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("响应必须为 JSON 对象")
                if callback:
                    callback(data)
            except (ValueError, UnicodeError) as exc:
                (on_error or self.error.emit)(str(exc))
            finally:
                reply.deleteLater()

        reply.finished.connect(finished)
        return reply

    def start_stream(self, path, body):
        if self.state != "running":
            self.error.emit("请先启动本地服务")
            return
        self.cancel_stream()
        request = QNetworkRequest(QUrl(self.config.base_url + path))
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json; charset=utf-8")
        request.setRawHeader(b"Accept", b"text/event-stream")
        request.setTransferTimeout(0)
        reply = self.network.post(request, json.dumps(body, ensure_ascii=False).encode("utf-8"))
        reply.setReadBufferSize(256 * 1024)
        self.stream = reply
        decoder = SSEDecoder()
        self._decoder = decoder
        last_preset_id = None
        drain_timer = QTimer(reply)
        drain_timer.setInterval(10)
        # A watchdog detects a stalled connection without limiting long streams.
        watchdog = QTimer(reply)
        watchdog.setSingleShot(True)
        watchdog.setInterval(120000)

        def timed_out():
            if self.stream is reply:
                self.cancel_stream("连接超过 120 秒没有收到数据")

        watchdog.timeout.connect(timed_out)
        watchdog.start()

        def consume(final=False):
            nonlocal last_preset_id
            if self.stream is not reply:
                return
            if not final and not reply.bytesAvailable():
                return
            raw = bytes(reply.readAll() if final else reply.read(64 * 1024))
            if raw:
                watchdog.start()
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            if status and int(status) >= 400:
                return
            try:
                for data in decoder.feed(raw, final=final):
                    if self.stream is not reply:
                        return
                    if data == "[DONE]":
                        continue
                    event = json.loads(data)
                    if not isinstance(event, dict):
                        raise ValueError("流式事件必须为 JSON 对象")
                    metadata = event.get("agent_nonsense")
                    preset = metadata.get("preset") if isinstance(metadata, dict) else None
                    if isinstance(preset, dict) and preset.get("id") and preset["id"] != last_preset_id:
                        last_preset_id = preset["id"]
                        self.stream_preset.emit(preset)
                        if self.stream is not reply:
                            return
                    text = event_text(event)
                    if text:
                        self.stream_text.emit(text)
            except (ValueError, UnicodeError) as exc:
                self.cancel_stream("流解析失败：" + str(exc))

        def finished():
            watchdog.stop()
            drain_timer.stop()
            if self.stream is reply:
                consume(final=True)
                if self.stream is reply:
                    self.stream = None
                    if reply.error() != QNetworkReply.NetworkError.NoError:
                        self.stream_finished.emit("请求失败：" + reply.errorString())
                    else:
                        self.stream_finished.emit("输出已完成")
            reply.deleteLater()

        reply.readyRead.connect(consume)
        reply.finished.connect(finished)
        # Qt can coalesce readyRead notifications while a zero-delay producer
        # keeps the socket busy. Poll bounded batches as well as handling signals.
        drain_timer.timeout.connect(consume)
        drain_timer.start()

    def cancel_stream(self, reason="已停止输出"):
        reply, self.stream = self.stream, None
        if reply is not None:
            reply.abort()
            self.stream_finished.emit(reason)
