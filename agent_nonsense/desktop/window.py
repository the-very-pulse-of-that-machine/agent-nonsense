"""豆皮: a standalone, Chinese-language desktop control room."""
import json
import sys
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt, QTimer
from PySide6.QtGui import QDesktopServices, QFont, QTextBlockFormat, QTextCursor, QTextDocument
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QComboBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QHeaderView,
    QLineEdit, QListWidget, QMainWindow, QMessageBox, QPlainTextEdit,
    QScrollArea, QSpinBox, QSplitter, QStackedWidget,
    QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget,
)

from .backend import Backend
from .models import BUILTIN_PRESETS, ServerConfig, atomic_write, preview_request, validate_presets
from .theme import STYLE
from .widgets import ProjectLogo, Card, CheckBox as QCheckBox, app_icon, button, label, nav_icon, row

PAGES = ("控制台", "实时预览", "后台任务", "预设剧本", "服务设置", "运行日志")
DESCRIPTIONS = (
    "你的本地 Agent 状态工作台。", "发送一条请求，观察每一个字符的到来。",
    "创建、查看和停止后台活动。", "让每一段工作状态都有自己的表达。",
    "调整运行参数，找到合适的输出节奏。", "所有启动信息与请求记录，都在这里。",
)
STATES = {"stopped": "尚未启动", "starting": "正在启动", "running": "服务运行中",
          "stopping": "正在停止", "error": "启动异常"}
JOB_STATES = {"queued": "排队中", "running": "运行中", "stopped": "已停止", "completed": "已完成"}
DEFAULT_PREVIEW_PROMPT = "请展示一项项目排查任务的处理过程。"


class MainWindow(QMainWindow):
    def __init__(self, data_dir=None):
        super().__init__()
        self.setWindowTitle("豆皮 · 本地 Agent 工作台")
        self.setWindowIcon(app_icon())
        self.resize(1260, 850)
        self.setMinimumSize(1000, 700)
        self.data_dir = Path(data_dir or QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.settings_path = self.data_dir / "settings.json"
        self.startup_error = ""
        try:
            self.config = ServerConfig.load(self.settings_path, self.data_dir)
        except (ValueError, OSError, TypeError) as exc:
            self.config = ServerConfig(sandbox=str(self.data_dir / "sandbox"), presets=str(BUILTIN_PRESETS))
            self.startup_error = "配置读取失败，已使用默认值：" + str(exc)
        # The editor always starts with a user-owned copy, never package resources.
        if Path(self.config.presets).resolve() == BUILTIN_PRESETS:
            own_presets = self.data_dir / "presets.json"
            if not own_presets.exists():
                atomic_write(own_presets, BUILTIN_PRESETS.read_text(encoding="utf-8"))
            self.config.presets = str(own_presets)
        self.backend = Backend(self)
        self.jobs = []
        self.jobs_pending = False
        self.stream_buffer = ""
        self.stream_chars = 0
        self.stream_dirty = False
        self.preset_dirty = False
        self.preset_questions = {}
        self._build()
        self.notice_timer = QTimer(self)
        self.notice_timer.setSingleShot(True)
        self.notice_timer.timeout.connect(self.notice.hide)
        self._connect()
        self._load_config_fields()
        self._load_presets()
        self._state_changed("stopped")
        self.render_timer = QTimer(self)
        self.render_timer.setInterval(250)
        self.render_timer.timeout.connect(self._render_stream)
        self.render_timer.start()
        self.clock = QTimer(self)
        self.clock.setInterval(1000)
        self.clock.timeout.connect(self._tick)
        self.clock.start()
        if self.startup_error:
            QTimer.singleShot(0, lambda: self.notify(self.startup_error, error=True))

    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(200)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 28, 16, 24)
        side.setSpacing(8)
        brand = QWidget()
        brandbox = QHBoxLayout(brand)
        brandbox.setContentsMargins(4, 0, 0, 0)
        brandbox.setSpacing(4)
        brandbox.addWidget(ProjectLogo(48))
        brandbox.addWidget(label("豆皮", "brand"))
        brandbox.addStretch()
        side.addWidget(brand)
        tag = label("DOUPI  /  DESKTOP", "eyebrow")
        tag.setContentsMargins(14, 2, 0, 25)
        side.addWidget(tag)
        self.nav = QButtonGroup(self)
        for index, title in enumerate(PAGES):
            item = button("  " + title)
            item.setIcon(nav_icon(index))
            item.setCheckable(True)
            item.setProperty("nav", True)
            self.nav.addButton(item, index)
            side.addWidget(item)
        self.nav.button(0).setChecked(True)
        self.nav.idClicked.connect(self._navigate)
        side.addStretch()
        local = Card()
        local.box.setContentsMargins(12, 14, 12, 14)
        local.box.setSpacing(6)
        local.box.addWidget(label("●  只在你的电脑运行", "eyebrow"))
        foot = label("本地状态模拟器\n上游调用 0 · Token 0", muted=True)
        foot.setStyleSheet("font-size: 11px; line-height: 1.5;")
        local.box.addWidget(foot)
        side.addWidget(local)
        outer.addWidget(sidebar)
        workspace = QWidget()
        workspace.setObjectName("workspace")
        work = QVBoxLayout(workspace)
        work.setContentsMargins(28, 25, 28, 24)
        work.setSpacing(18)
        self.crumb = label("工作空间  /  控制台", muted=True)
        self.status_pill = label("●  尚未启动", "pill")
        work.addLayout(row(self.crumb, None, self.status_pill))
        self.page_title = label(PAGES[0], "pageTitle")
        self.page_subtitle = label(DESCRIPTIONS[0], "subtitle")
        headings = QVBoxLayout()
        headings.setSpacing(6)
        headings.addWidget(self.page_title)
        headings.addWidget(self.page_subtitle)
        work.addLayout(headings)
        self.notice = label("", "notice")
        self.notice.setWordWrap(True)
        self.notice.hide()
        work.addWidget(self.notice)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._overview_page())
        self.pages.addWidget(self._preview_page())
        self.pages.addWidget(self._jobs_page())
        self.pages.addWidget(self._presets_page())
        self.pages.addWidget(self._settings_page())
        self.pages.addWidget(self._logs_page())
        work.addWidget(self.pages, 1)
        footer = label("豆皮 0.1  ·  本地预置内容生成  ·  OpenAI / Anthropic 兼容", muted=True)
        footer.setStyleSheet("font-size: 11px;")
        work.addWidget(footer)
        outer.addWidget(workspace, 1)

    def _navigate(self, index):
        self.pages.setCurrentIndex(index)
        self.nav.button(index).setChecked(True)
        self.page_title.setText(PAGES[index])
        self.page_subtitle.setText(DESCRIPTIONS[index])
        self.crumb.setText("工作空间  /  " + PAGES[index])
        if index == 2:
            self.refresh_jobs()

    def _overview_page(self):
        content = QWidget()
        box = QVBoxLayout(content)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(18)
        metrics = QHBoxLayout()
        metrics.setSpacing(14)
        self.metric_labels = []
        for title, value, detail in (("服务状态", "待启动", "LOOPBACK / 127.0.0.1"),
                                     ("运行时长", "00:00:00", "当前服务会话"),
                                     ("可用剧本", "10", "可编辑的长对话预设"),
                                     ("Token 消耗", "0", "无上游模型调用")):
            card = Card()
            card.box.setContentsMargins(18, 16, 18, 16)
            card.box.setSpacing(8)
            card.box.addWidget(label(title, muted=True))
            value_label = label(value, "metricValue")
            self.metric_labels.append(value_label)
            card.box.addWidget(value_label)
            caption = label(detail, muted=True)
            caption.setStyleSheet("font-size: 10px;")
            card.box.addWidget(caption)
            metrics.addWidget(card, 1)
        box.addLayout(metrics)
        columns = QHBoxLayout()
        columns.setSpacing(18)
        left = QVBoxLayout()
        left.setSpacing(18)
        hero = Card(hero=True)
        hero.box.setSpacing(10)
        self.hero_title = label("豆皮，准备就绪。", "heroTitle")
        hero.box.addWidget(self.hero_title)
        intro = label("一键开启本地服务，让状态流持续发生。", muted=True)
        intro.setWordWrap(True)
        hero.box.addWidget(intro)
        self.logo = ProjectLogo(110)
        self.overview_address = label(self.config.base_url, "cardTitle")
        info = QVBoxLayout()
        info.setSpacing(10)
        info.addWidget(label("服务地址", muted=True))
        info.addWidget(self.overview_address)
        self.mode_label = label("连续输出 · sandbox 文件工具", muted=True)
        self.mode_label.setWordWrap(True)
        info.addWidget(self.mode_label)
        info.addStretch()
        art = QHBoxLayout()
        art.addLayout(info, 1)
        art.addWidget(self.logo)
        hero.box.addLayout(art)
        self.start_button = button("▶  启动服务", self.toggle_server, primary=True)
        settings_button = button("调整参数", lambda: self._navigate(4))
        hero.box.addLayout(row(self.start_button, settings_button, None))
        left.addWidget(hero)
        shortcuts = Card("开始使用")
        shortcuts.box.setContentsMargins(20, 16, 20, 16)
        shortcuts.box.setSpacing(10)
        shortcuts.box.addLayout(row(button("实时预览  ↗", lambda: self._navigate(1)),
                                    button("管理剧本  ↗", lambda: self._navigate(3))))
        note = label("预置内容生成状态流，文件工具仅在 sandbox 内执行。", muted=True)
        note.setWordWrap(True)
        shortcuts.box.addWidget(note)
        left.addWidget(shortcuts)
        left.addStretch()
        columns.addLayout(left, 3)
        connect = Card("接入你的客户端", "复制以下配置，填入兼容客户端。")
        connect.box.setSpacing(10)
        connect.setMinimumWidth(288)
        connect.setMaximumWidth(390)
        connect.box.addWidget(label("OpenAI Compatible", "eyebrow"))
        connect.box.addWidget(label("Base URL", muted=True))
        self.base_url = QLineEdit(self.config.base_url + "/v1")
        self.base_url.setReadOnly(True)
        connect.box.addLayout(row(self.base_url, button("复制", lambda: self.copy(self.base_url.text()))))
        credentials = QFormLayout()
        credentials.setSpacing(10)
        for name, value in (("API Key", "local"), ("Model", "agent-nonsense")):
            field = QLineEdit(value)
            field.setReadOnly(True)
            credentials.addRow(label(name, muted=True), field)
        connect.box.addLayout(credentials)
        connect.box.addWidget(label("●  Streaming / 开启", "eyebrow"))
        connect.box.addStretch()
        connect.box.addWidget(button("复制完整配置", self.copy_connection))
        anthropic = label("Anthropic Messages 使用根地址，\n不需要末尾的 /v1。", muted=True)
        anthropic.setWordWrap(True)
        connect.box.addWidget(anthropic)
        columns.addWidget(connect, 2)
        box.addLayout(columns, 1)
        return self._scroll(content)

    def _preview_page(self):
        content = QWidget()
        box = QVBoxLayout(content)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(16)
        controls = Card()
        self.protocol = QComboBox()
        self.protocol.addItems(["Responses", "Chat Completions", "Messages"])
        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumWidth(210)
        self.preview_continuous = QCheckBox("持续输出")
        self.preview_events = QSpinBox()
        self.preview_events.setRange(1, 1000)
        self.preview_events.setValue(3)
        self.preview_events.setSuffix(" 阶段")
        controls.box.addLayout(row(self.protocol, self.preset_combo, None,
                                   self.preview_events, self.preview_continuous))
        self.preview_preset = label("当前剧本：等待请求", muted=True)
        self.preview_preset.setWordWrap(True)
        controls.box.addWidget(self.preview_preset)
        self.preview_continuous.setToolTip("随机模式下，每份完整剧本结束后自动换下一份；指定剧本则循环播放。")
        self.prompt = QPlainTextEdit(DEFAULT_PREVIEW_PROMPT)
        self.prompt.setMaximumHeight(85)
        self.prompt.setPlaceholderText("输入一条测试请求…")
        controls.box.addWidget(self.prompt)
        self.preview_start = button("▶  发送请求", self.start_preview, primary=True)
        self.preview_stop = button("停止输出", lambda: self.backend.cancel_stream())
        self.preview_stop.setEnabled(False)
        self.preview_status = label("启动服务后即可预览", muted=True)
        controls.box.addLayout(row(self.preview_start, self.preview_stop, None, self.preview_status))
        box.addWidget(controls)
        output = Card()
        self.char_count = label("0 字符", muted=True)
        output.box.addLayout(row(label("实时输出", "cardTitle"), None, self.char_count,
                                 button("复制", lambda: self.copy(self.stream_buffer)),
                                 button("导出", self.export_stream)))
        self.output_stack = QStackedWidget()
        empty = QWidget()
        emptybox = QVBoxLayout(empty)
        emptybox.addStretch()
        emptybox.addWidget(ProjectLogo(120), alignment=Qt.AlignmentFlag.AlignHCenter)
        emptybox.addWidget(label("等候第一条状态", "cardTitle"), alignment=Qt.AlignmentFlag.AlignHCenter)
        emptybox.addWidget(label("选择协议与剧本，发送请求开始预览。", muted=True), alignment=Qt.AlignmentFlag.AlignHCenter)
        emptybox.addStretch()
        self.output_stack.addWidget(empty)
        self.output = QTextBrowser()
        self.output.setOpenExternalLinks(False)
        self.output.setOpenLinks(False)
        self.output.document().setDefaultStyleSheet(
            "body { color: #454158; } h2,h3 { color: #645184; } pre { background: #f1eef8; }"
        )
        self.output_stack.addWidget(self.output)
        output.box.addWidget(self.output_stack, 1)
        box.addWidget(output, 1)
        return content

    def _jobs_page(self):
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(16)
        create = Card("创建后台任务")
        self.job_prompt = QLineEdit()
        self.job_prompt.setPlaceholderText("例如：整理项目并检查测试")
        self.job_max = QSpinBox()
        self.job_max.setRange(0, 10000)
        self.job_max.setValue(20)
        self.job_max.setSpecialValueText("不限事件数")
        self.job_max.setSuffix(" 事件")
        self.job_duration = QSpinBox()
        self.job_duration.setRange(0, 86400)
        self.job_duration.setValue(60)
        self.job_duration.setSpecialValueText("不限时长")
        self.job_duration.setSuffix(" 秒")
        self.create_job_button = button("创建任务", self.create_job, primary=True)
        create.box.addLayout(row(self.job_prompt, self.job_max, self.job_duration, self.create_job_button))
        modules = QHBoxLayout()
        self.job_modules = {}
        for key, title in (("research", "调研"), ("code_edit", "代码编辑"), ("test_run", "测试"),
                           ("file_ops", "文件操作"), ("debug_trace", "调试")):
            check = QCheckBox(title)
            check.setChecked(key in ("research", "code_edit", "test_run"))
            self.job_modules[key] = check
            modules.addWidget(check)
        modules.addStretch()
        create.box.addLayout(modules)
        box.addWidget(create)
        self.jobs_status = label("暂无任务 · 启动服务后可创建", muted=True)
        self.stop_job_button = button("停止选中任务", self.stop_job)
        self.stop_job_button.setProperty("danger", True)
        box.addLayout(row(self.jobs_status, None, button("刷新", self.refresh_jobs), self.stop_job_button))
        self.job_table = QTableWidget(0, 4)
        self.job_table.setHorizontalHeaderLabels(["任务", "状态", "事件数", "任务 ID"])
        self.job_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            self.job_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.job_table.verticalHeader().hide()
        self.job_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.job_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.job_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.job_table.itemSelectionChanged.connect(self._job_selected)
        box.addWidget(self.job_table, 2)
        self.job_details = QPlainTextEdit()
        self.job_details.setReadOnly(True)
        self.job_details.setPlaceholderText("选择任务，查看最近的活动记录。")
        box.addWidget(self.job_details, 1)
        return page

    def _presets_page(self):
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(14)
        self.preset_status = label("", muted=True)
        self.import_button = button("导入 JSON", self.import_presets)
        self.save_presets_button = button("保存修改", self.save_presets, primary=True)
        box.addLayout(row(self.preset_status, None, self.import_button,
                          button("另存为", self.export_presets), self.save_presets_button))
        splitter = QSplitter()
        card = Card("剧本目录")
        card.setMinimumWidth(230)
        self.preset_list = QListWidget()
        self.preset_list.currentRowChanged.connect(self._jump_to_preset)
        card.box.addWidget(self.preset_list)
        hint = label("点击名称，定位到 JSON 中的预设。", muted=True)
        hint.setWordWrap(True)
        card.box.addWidget(hint)
        splitter.addWidget(card)
        self.preset_editor = QPlainTextEdit()
        self.preset_editor.setFont(QFont("Menlo" if sys.platform == "darwin" else "Consolas", 11))
        self.preset_editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.preset_editor.textChanged.connect(self._presets_changed)
        splitter.addWidget(self.preset_editor)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([250, 650])
        box.addWidget(splitter, 1)
        hint = label("保存前会校验 JSON、唯一 ID、模块和工具名称。运行中的服务需要停止后才能编辑。", muted=True)
        hint.setWordWrap(True)
        box.addWidget(hint)
        return page

    def _settings_page(self):
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(16)
        self.settings_body = QWidget()
        grid = QGridLayout(self.settings_body)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(18)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        network = Card("服务与文件", "只绑定 127.0.0.1，配置保存在本机。")
        form = QFormLayout()
        form.setSpacing(14)
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        form.addRow("端口", self.port)
        self.sandbox_path = QLineEdit()
        form.addRow("Sandbox", self.sandbox_path)
        form.addRow("", button("选择文件目录…", self.choose_sandbox))
        self.presets_path = QLineEdit()
        form.addRow("预设文件", self.presets_path)
        form.addRow("", button("选择预设 JSON…", self.choose_presets))
        self.max_events = QSpinBox()
        self.max_events.setRange(1, 10000)
        form.addRow("默认阶段数", self.max_events)
        network.box.addLayout(form)
        network.box.addStretch()
        grid.addWidget(network, 0, 0)
        pacing = Card("输出节奏", "速度倍率同时缩放阶段间隔与逐字间隔。")
        cadence = QFormLayout()
        cadence.setSpacing(14)
        self.delay = self._double(0, 3600, 2, " 秒")
        self.jitter = self._double(0, 0.9, 2, " 秒")
        self.character_delay = self._double(0, 60, 3, " 秒 / 字")
        self.speed = self._double(0.01, 1000, 2, " ×")
        cadence.addRow("阶段间隔", self.delay)
        cadence.addRow("随机停顿", self.jitter)
        cadence.addRow("逐字间隔", self.character_delay)
        cadence.addRow("速度倍率", self.speed)
        pacing.box.addLayout(cadence)
        self.continuous = QCheckBox("连续流 · 直到客户端停止")
        self.tools = QCheckBox("执行 sandbox 文件工具")
        self.native_tools = QCheckBox("原生 Responses 工具事件")
        self.native_tools.setToolTip("仅适用于实现完整工具握手的客户端；界面预览使用文本工具模式。")
        for check in (self.continuous, self.tools, self.native_tools):
            pacing.box.addWidget(check)
        grid.addWidget(pacing, 0, 1)
        box.addWidget(self.settings_body)
        help_text = label("参数修改在下次启动时生效。快速验证时，可将逐字间隔设为 0、阶段间隔设为 0.1 秒。", muted=True)
        help_text.setWordWrap(True)
        box.addWidget(help_text)
        self.save_settings_button = button("保存设置", self.save_settings, primary=True)
        box.addLayout(row(None, self.save_settings_button))
        box.addStretch()
        return self._scroll(page)

    def _logs_page(self):
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(14)
        box.addLayout(row(label("服务输出与操作记录", "cardTitle"), None,
                          button("打开 Sandbox", self.open_sandbox),
                          button("导出日志", self.export_logs), button("清空", lambda: self.logs.clear())))
        self.logs = QPlainTextEdit()
        self.logs.setObjectName("console")
        self.logs.setReadOnly(True)
        self.logs.setMaximumBlockCount(2000)
        self.logs.setFont(QFont("Menlo" if sys.platform == "darwin" else "Consolas", 11))
        self.logs.setPlaceholderText("启动服务后，日志会显示在这里。")
        box.addWidget(self.logs, 1)
        return page

    @staticmethod
    def _scroll(content):
        content.setObjectName("scrollContent")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        return scroll

    @staticmethod
    def _double(low, high, decimals, suffix):
        field = QDoubleSpinBox()
        field.setRange(low, high)
        field.setDecimals(decimals)
        field.setSingleStep(0.01 if decimals > 2 else 0.1)
        field.setSuffix(suffix)
        return field

    def _connect(self):
        self.backend.state_changed.connect(self._state_changed)
        self.backend.log.connect(self.append_log)
        self.backend.error.connect(lambda text: self.notify(text, error=True))
        self.backend.health.connect(self._health_changed)
        self.backend.stream_text.connect(self._stream_text)
        self.backend.stream_preset.connect(self._stream_preset)
        self.backend.stream_finished.connect(self._stream_finished)
        self.preset_combo.currentIndexChanged.connect(self._preview_dialogue_changed)
        self.protocol.currentIndexChanged.connect(self._preview_protocol_changed)
        self.preset_combo.setToolTip("随机模式避免连续重复；勾选持续输出可轮播。指定剧本后只播放该剧本。")
        self.preview_continuous.toggled.connect(lambda checked: self.preview_events.setEnabled(not checked))

    def append_log(self, text):
        self.logs.appendPlainText(f"[{datetime.now().strftime('%H:%M:%S')}] {text}")

    def notify(self, text, error=False):
        self.notice.setText(text)
        self.notice.setProperty("error", error)
        self.notice.style().unpolish(self.notice)
        self.notice.style().polish(self.notice)
        self.notice.show()
        self.notice_timer.start(10000 if error else 4500)
        self.append_log(("错误：" if error else "") + text)

    def _load_config_fields(self):
        for field, value in ((self.port, self.config.port), (self.delay, self.config.delay),
                             (self.jitter, self.config.jitter), (self.character_delay, self.config.character_delay),
                             (self.speed, self.config.speed_factor), (self.max_events, self.config.max_events)):
            field.setValue(value)
        self.sandbox_path.setText(self.config.sandbox)
        self.presets_path.setText(self.config.presets)
        self.continuous.setChecked(self.config.continuous)
        self.tools.setChecked(self.config.simulate_tools)
        self.native_tools.setChecked(self.config.native_tools)
        self._connection_changed()

    def _read_config(self):
        if not self.sandbox_path.text().strip() or not self.presets_path.text().strip():
            raise ValueError("Sandbox 和预设文件路径不能为空")
        return ServerConfig(port=self.port.value(), delay=self.delay.value(), jitter=self.jitter.value(),
                            character_delay=self.character_delay.value(), speed_factor=self.speed.value(),
                            max_events=self.max_events.value(), continuous=self.continuous.isChecked(),
                            simulate_tools=self.tools.isChecked(), native_tools=self.native_tools.isChecked(),
                            sandbox=str(Path(self.sandbox_path.text()).expanduser().resolve()),
                            presets=str(Path(self.presets_path.text()).expanduser().resolve())).validate()

    def save_settings(self, quiet=False):
        if self.backend.state not in ("stopped", "error"):
            return False
        try:
            config = self._read_config()
            if config.presets != self.config.presets and not self._confirm_preset_changes():
                return False
            changed_presets = config.presets != self.config.presets
            config.save(self.settings_path)
            self.config = config
            self._connection_changed()
            if changed_presets:
                self._load_presets()
            if not quiet:
                self.notify("设置已保存，下次启动生效。")
            return True
        except (ValueError, OSError) as exc:
            self.notify("无法保存设置：" + str(exc), error=True)
            return False

    def _connection_changed(self):
        self.base_url.setText(self.config.base_url + "/v1")
        self.overview_address.setText(self.config.base_url)
        self.mode_label.setText(("连续输出" if self.config.continuous else "有限输出") +
                               (" · sandbox 文件工具" if self.config.simulate_tools else " · 按需文件工具"))

    def toggle_server(self):
        if self.backend.state in ("running", "starting"):
            self.backend.stop()
            return
        if self.backend.state == "stopping":
            return
        if self.preset_dirty and not self.save_presets():
            return
        if self.save_settings(quiet=True):
            self.append_log("正在启动本地服务…")
            self.backend.start(self.config)

    def _state_changed(self, state):
        running = state == "running"
        editable = state in ("stopped", "error")
        self.status_pill.setText("●  " + STATES[state])
        self.status_pill.setProperty("state", state)
        self.status_pill.style().unpolish(self.status_pill)
        self.status_pill.style().polish(self.status_pill)
        self.metric_labels[0].setText({"stopped": "待启动", "running": "运行中", "error": "异常",
                                       "starting": "启动中", "stopping": "停止中"}[state])
        self.hero_title.setText("豆皮，正在工作。" if running else "豆皮，准备就绪。")
        self.start_button.setText("■  停止服务" if state in ("running", "starting") else
                                  "正在停止…" if state == "stopping" else "▶  启动服务")
        self.start_button.setEnabled(state != "stopping")
        self.logo.set_live(running)
        self.settings_body.setEnabled(editable)
        self.save_settings_button.setEnabled(editable)
        self.preset_editor.setReadOnly(not editable)
        self.save_presets_button.setEnabled(editable)
        self.import_button.setEnabled(editable)
        self.preview_start.setEnabled(running)
        self.create_job_button.setEnabled(running)
        self._job_selected()
        if not running:
            self.jobs = []
            self.job_table.setRowCount(0)
            self.job_details.clear()
            self.jobs_status.setText("启动服务后可创建任务")
            self.preview_status.setText("启动服务后即可预览")
        else:
            self.preview_status.setText("已连接 · 等待请求")
            self.refresh_jobs()
        self.append_log("服务状态：" + STATES[state])

    def _health_changed(self, payload):
        if self.backend.state == "running":
            self.metric_labels[3].setText(str(payload.get("token_usage", 0)))

    def _tick(self):
        elapsed = int(time.monotonic() - self.backend.started_at) if self.backend.started_at else 0
        self.metric_labels[1].setText(f"{elapsed // 3600:02}:{elapsed // 60 % 60:02}:{elapsed % 60:02}")
        if self.pages.currentIndex() == 2 and self.backend.state == "running":
            self.refresh_jobs()

    def copy(self, text):
        QApplication.clipboard().setText(text)
        self.notify("已复制到剪贴板。")

    def copy_connection(self):
        self.copy(f"Provider: OpenAI Compatible\nBase URL: {self.config.base_url}/v1\n"
                  "API Key: local\nModel: agent-nonsense\nStreaming: enabled")

    def choose_sandbox(self):
        path = QFileDialog.getExistingDirectory(self, "选择 Sandbox 目录", self.sandbox_path.text())
        if path:
            self.sandbox_path.setText(path)

    def choose_presets(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择预设 JSON", self.presets_path.text(), "JSON (*.json)")
        if path:
            self.presets_path.setText(path)

    def open_sandbox(self):
        try:
            path = Path(self.config.sandbox)
            path.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        except OSError as exc:
            self.notify(str(exc), error=True)

    def start_preview(self):
        if self.backend.state != "running":
            self.notify("请先启动本地服务。", error=True)
            return
        prompt = self.prompt.toPlainText().strip()
        if not prompt:
            self.notify("请输入测试请求。", error=True)
            return
        # Finish the previous reply before clearing its view; its completion signal
        # must never render into or disable controls for the replacement request.
        self.backend.cancel_stream()
        self._clear_preview()
        self.output_stack.setCurrentIndex(1)
        self.preview_preset.setText("当前剧本：正在选择…")
        path, body = preview_request(self.protocol.currentText(), prompt, self.preset_combo.currentData() or "",
                                     self.preview_continuous.isChecked(), self.preview_events.value())
        self.backend.start_stream(path, body)
        active = self.backend.stream is not None
        self.preview_start.setEnabled(self.backend.state == "running")
        self.preview_start.setText("↻  重新发送" if active else "▶  发送请求")
        self.preview_stop.setEnabled(active)
        self.preview_status.setText("●  正在接收…" if active else "未连接")
        self.append_log(f"预览请求：{path}")

    def _clear_preview(self):
        self.stream_buffer = ""
        self.stream_chars = 0
        self.stream_dirty = False
        self.output.clear()
        self.char_count.setText("0 字符")
        self.output_stack.setCurrentIndex(0)
        self.preview_preset.setText("当前剧本：等待请求")

    def _preview_dialogue_changed(self, _index=0):
        active = self.backend.stream is not None
        self.backend.cancel_stream("已切换对话")
        identity = self.preset_combo.currentData() or ""
        self.prompt.setPlainText(self.preset_questions.get(identity, DEFAULT_PREVIEW_PROMPT))
        self._clear_preview()
        if active and self.backend.state == "running":
            self.start_preview()
        else:
            self.preview_status.setText("已切换对话 · 点击发送请求" if self.backend.state == "running"
                                        else "启动服务后即可预览")

    def _preview_protocol_changed(self, _index=0):
        active = self.backend.stream is not None
        self.backend.cancel_stream("已切换协议")
        self._clear_preview()
        if active and self.backend.state == "running":
            self.start_preview()
        else:
            self.preview_status.setText("已切换协议 · 点击发送请求" if self.backend.state == "running"
                                        else "启动服务后即可预览")

    def _stream_preset(self, preset):
        title = str(preset.get("title") or preset["id"])
        self.preview_preset.setText("当前剧本：" + title)
        self.append_log("预览剧本：" + title)

    def _stream_text(self, text):
        self.stream_chars += len(text)
        self.stream_buffer = (self.stream_buffer + text)[-60000:]
        self.stream_dirty = True

    def _render_stream(self):
        if not self.stream_dirty:
            return
        self.stream_dirty = False
        bar = self.output.verticalScrollBar()
        at_bottom = bar.value() >= bar.maximum() - 25
        old_position = bar.value()
        self.output.document().setMarkdown(self.stream_buffer, QTextDocument.MarkdownFeature.MarkdownNoHTML)
        cursor = QTextCursor(self.output.document())
        cursor.beginEditBlock()
        block = self.output.document().begin()
        while block.isValid():
            cursor.setPosition(block.position())
            formatting = block.blockFormat()
            formatting.setLineHeight(130, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
            formatting.setBottomMargin(1 if block.textList() else 6)
            if formatting.headingLevel():
                formatting.setTopMargin(8)
            cursor.setBlockFormat(formatting)
            block = block.next()
        cursor.endEditBlock()
        bar.setValue(bar.maximum() if at_bottom else old_position)
        suffix = " · 仅保留最近 60,000 字符" if self.stream_chars > 60000 else ""
        self.char_count.setText(f"{self.stream_chars:,} 字符" + suffix)

    def _stream_finished(self, message):
        self._render_stream()
        self.preview_start.setEnabled(self.backend.state == "running")
        self.preview_start.setText("▶  发送请求")
        self.preview_stop.setEnabled(False)
        self.preview_status.setText(message)
        self.append_log("预览：" + message)
        if "失败" in message or "120 秒" in message:
            self.notify(message, error=True)

    def create_job(self):
        prompt = self.job_prompt.text().strip()
        modules = [key for key, check in self.job_modules.items() if check.isChecked()]
        if not prompt or not modules:
            self.notify("请输入任务描述，并至少选择一个模块。", error=True)
            return
        self.create_job_button.setEnabled(False)
        body = {"prompt": prompt, "modules": modules, "max_events": self.job_max.value(),
                "duration_seconds": self.job_duration.value(), "speed_factor": self.config.speed_factor}

        def done(_payload):
            self.create_job_button.setEnabled(self.backend.state == "running")
            self.notify("后台任务已创建。")
            self.refresh_jobs()

        def failed(message):
            self.create_job_button.setEnabled(self.backend.state == "running")
            if self.backend.state == "running":
                self.notify(message, error=True)

        self.backend.request("/v1/agent/jobs", body, done, failed)

    def refresh_jobs(self):
        if self.backend.state != "running" or self.jobs_pending:
            return
        self.jobs_pending = True

        def done(payload):
            self.jobs_pending = False
            if self.backend.state != "running":
                return
            selected = self.selected_job_id()
            self.jobs = list(reversed(payload.get("jobs", [])))
            self.job_table.blockSignals(True)
            self.job_table.setRowCount(len(self.jobs))
            for index, job in enumerate(self.jobs):
                for column, text in enumerate((job["prompt"], JOB_STATES.get(job["status"], job["status"]),
                                                str(job["event_count"]), job["id"])):
                    item = QTableWidgetItem(text)
                    item.setToolTip(text)
                    self.job_table.setItem(index, column, item)
                self.job_table.setRowHeight(index, 46)
                if job["id"] == selected:
                    self.job_table.selectRow(index)
            self.job_table.blockSignals(False)
            active = sum(j["status"] in ("queued", "running") for j in self.jobs)
            self.jobs_status.setText(f"{len(self.jobs)} 个任务 · {active} 个运行中")
            self._job_selected()

        def failed(message):
            self.jobs_pending = False
            if self.backend.state == "running":
                self.jobs_status.setText("任务获取失败：" + message)

        self.backend.request("/v1/agent/jobs", callback=done, on_error=failed)

    def selected_job_id(self):
        index = self.job_table.currentRow()
        item = self.job_table.item(index, 3) if index >= 0 else None
        return item.text() if item else None

    def _job_selected(self):
        identity = self.selected_job_id()
        job = next((job for job in self.jobs if job["id"] == identity), None)
        active = job and job["status"] in ("queued", "running")
        self.stop_job_button.setEnabled(bool(active) and self.backend.state == "running")
        if job:
            lines = [f"{event.get('module', '')}  ·  {event.get('text', '')}" for event in job.get("events", [])]
            bar = self.job_details.verticalScrollBar()
            position, bottom = bar.value(), bar.value() >= bar.maximum() - 20
            self.job_details.setPlainText("\n".join(lines))
            bar.setValue(bar.maximum() if bottom else position)

    def stop_job(self):
        identity = self.selected_job_id()
        if identity and self.backend.state == "running":
            self.backend.request(f"/v1/agent/jobs/{identity}/stop", {}, lambda _: self.refresh_jobs())

    def _load_presets(self):
        try:
            text = Path(self.config.presets).read_text(encoding="utf-8")
            payload = validate_presets(text)
        except (ValueError, OSError) as exc:
            self.notify("无法加载预设：" + str(exc), error=True)
            return
        self.preset_editor.blockSignals(True)
        self.preset_editor.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        self.preset_editor.blockSignals(False)
        self.preset_dirty = False
        self._update_preset_catalog(payload)

    def _update_preset_catalog(self, payload):
        previous = self.preset_combo.currentData()
        self.preset_questions = {preset["id"]: preset["question"] for preset in payload["presets"]}
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem("随机剧本 · 持续时轮播", "")
        self.preset_list.blockSignals(True)
        self.preset_list.clear()
        self.preset_ids = []
        for preset in payload["presets"]:
            self.preset_ids.append(preset["id"])
            self.preset_list.addItem(preset["title"])
            self.preset_combo.addItem(preset["title"], preset["id"])
        self.preset_list.blockSignals(False)
        index = self.preset_combo.findData(previous)
        self.preset_combo.setCurrentIndex(max(0, index))
        self.preset_combo.blockSignals(False)
        self._preview_dialogue_changed()
        count = len(self.preset_ids)
        self.metric_labels[2].setText(str(count))
        self.preset_status.setText(f"{count} 个预设 · UTF-8 JSON")

    def _jump_to_preset(self, index):
        if 0 <= index < len(self.preset_ids):
            cursor = self.preset_editor.document().find('"' + self.preset_ids[index] + '"')
            if not cursor.isNull():
                self.preset_editor.setTextCursor(cursor)
                self.preset_editor.centerCursor()

    def _presets_changed(self):
        self.preset_dirty = True
        self.preset_status.setText("● 有未保存的修改")

    def save_presets(self):
        if self.backend.state not in ("stopped", "error"):
            return False
        try:
            payload = validate_presets(self.preset_editor.toPlainText())
            atomic_write(self.config.presets, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            self.preset_dirty = False
            self._update_preset_catalog(payload)
            self.notify("预设已保存。")
            return True
        except (ValueError, OSError) as exc:
            self.notify("预设未保存：" + str(exc), error=True)
            return False

    def _confirm_preset_changes(self):
        if not self.preset_dirty:
            return True
        answer = QMessageBox.question(self, "保存预设修改", "预设存在未保存的修改，要先保存吗？",
                                      QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard |
                                      QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Save)
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        return self.save_presets() if answer == QMessageBox.StandardButton.Save else True

    def import_presets(self):
        if not self._confirm_preset_changes():
            return
        source, _ = QFileDialog.getOpenFileName(self, "导入预设", "", "JSON (*.json)")
        if not source:
            return
        try:
            payload = validate_presets(Path(source).read_text(encoding="utf-8"))
            target = self.data_dir / "imported-presets.json"
            atomic_write(target, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            self.config = replace(self.config, presets=str(target))
            self.config.save(self.settings_path)
            self.presets_path.setText(str(target))
            self._load_presets()
            self.notify("预设已导入，原文件保持不变。")
        except (ValueError, OSError) as exc:
            self.notify("导入失败：" + str(exc), error=True)

    def _export(self, text, filename, filter_text):
        target, _ = QFileDialog.getSaveFileName(self, "导出文件", str(Path.home() / "Documents" / filename), filter_text)
        if target:
            try:
                atomic_write(target, text)
                self.notify("已导出到：" + target)
            except OSError as exc:
                self.notify("导出失败：" + str(exc), error=True)

    def export_stream(self):
        self._export(self.stream_buffer, "豆皮-实时输出.md", "Markdown (*.md)")

    def export_logs(self):
        self._export(self.logs.toPlainText(), "豆皮-运行日志.txt", "文本 (*.txt)")

    def export_presets(self):
        try:
            payload = validate_presets(self.preset_editor.toPlainText())
            self._export(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "豆皮-预设.json", "JSON (*.json)")
        except ValueError as exc:
            self.notify(str(exc), error=True)

    def closeEvent(self, event):
        if not self._confirm_preset_changes():
            event.ignore()
            return
        self.clock.stop()
        self.render_timer.stop()
        self.backend.shutdown()
        event.accept()


def run():
    app = QApplication(sys.argv)
    app.setApplicationName("Doupi")
    app.setOrganizationName("AgentNonsense")
    app.setApplicationDisplayName("豆皮")
    app.setStyle("Fusion")
    font = QFont()
    font.setFamilies(["PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", "sans-serif"])
    font.setPointSize(10)
    app.setFont(font)
    app.setStyleSheet(STYLE)
    app.setWindowIcon(app_icon())
    window = MainWindow()
    window.show()
    return app.exec()
