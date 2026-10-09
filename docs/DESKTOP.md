# 豆皮桌面版

Python + Qt（PySide6 Essentials）独立桌面窗口，复用豆皮原有 HTTP 服务。GUI 是可选依赖，`pip install .` 仍然只安装无第三方运行时依赖的 API 服务。

## 安装与启动

普通用户可在 [GitHub Releases](https://github.com/wahahaha-cpu/agent-nonsense/releases) 下载包含 Python 与 Qt 的安装包，详见 [安装包指南](INSTALLERS.md)。以下命令适用于源码开发环境。

需要 Python 3.10+。在项目目录创建独立环境：

```sh
python -m venv .venv
```

Windows：

```powershell
.venv\Scripts\python -m pip install -e ".[gui]"
.venv\Scripts\python -m agent_nonsense.desktop
```

macOS / Linux：

```sh
.venv/bin/python -m pip install -e '.[gui]'
.venv/bin/python -m agent_nonsense.desktop
```

macOS 如果只有 `python3` 命令，第一步使用 `python3 -m venv .venv`。
安装后也可以运行环境内的 `doupi` 命令，或直接执行 `doupi_gui.py`。
项目附有 `启动豆皮.command`（macOS）和 `启动豆皮.bat`（Windows）；创建环境并安装依赖后，可双击启动。

## VS Code

用 VS Code 打开项目文件夹，安装推荐的 Python 扩展。选择 `.venv` 作为解释器，在“运行和调试”选择 **豆皮 · 桌面 GUI**，按 F5。另有 **豆皮 · API 服务** 配置，两者如同时启动应使用不同端口。

## 功能

- **控制台**：一键启动/停止、运行时长、剧本数量、Token 消耗与客户端连接配置复制。
- **实时预览**：真实请求 Responses、Chat Completions 或 Anthropic Messages；支持指定/随机剧本、有限阶段和连续输出、Markdown 渲染、取消、复制和导出。
- **后台任务**：选择活动模块、事件数和时长，创建、查看、停止任务；事件数/时长为 0 表示不限制。任务使用原有活动模块 API，不使用长对话剧本。
- **预设剧本**：JSON 编辑、目录定位、导入、导出、保存前校验。默认编辑的是用户数据目录的副本。服务运行期间锁定编辑，停止后再保存。
- **服务设置**：端口、sandbox、预设文件、阶段间隔、随机停顿、逐字间隔、速度倍率、默认阶段数、连续流、文件工具及原生 Responses 工具事件。
- **运行日志**：启动和请求记录、导出、打开 sandbox。

快速验证输出可设：阶段间隔 `0.1` 秒，随机停顿 `0`，逐字间隔 `0`。日常可保持默认 `2.0 / 0.32 / 0.06`。界面预览中的“持续输出”独立控制单次请求，默认只输出 3 个阶段，便于测试。

预览中切换剧本会自动填入对应问题并清空旧输出；正在输出时，会取消旧请求并立即开始选中的新对话。切换协议也会重新发送当前对话。输出期间可编辑问题后点击“重新发送”。预置正文以所选剧本为准，自定义输入会作为请求发送给原有 API，不会将本地模拟器变成上游模型。

要自动切换，选择 **随机剧本 · 持续时轮播**，勾选 **持续输出** 后发送。每份完整剧本及其工具输出结束后会随机换下一份，紧邻两轮不会重复（只有一份时继续循环）。上方的“当前剧本”实时显示服务实际播放的标题，选择框仍保留随机模式。未勾选持续输出时，按阶段数完成单次预览，再次发送会避开服务上一次随机选择。指定某份剧本后，持续输出只循环该份。内置每份至少 5,000 字，默认逐字速度下播完一份需要数分钟；快速检查轮播可使用上面的快速验证速度。

应用图标、侧边栏、控制台和预览空状态统一使用仓库原有 `docs/assets/agent-nonsense.ico`，打包时包含其原样副本。

原生工具选项适用于实现完整 Responses 工具握手的客户端；界面预览显式关闭原生事件，使用可读的工具文本。

## 配置与生命周期

配置保存在 Qt `AppDataLocation` 下的 `AgentNonsense/Doupi` 对应目录。常见位置：

- macOS：`~/Library/Application Support/AgentNonsense/Doupi/`
- Windows：`%APPDATA%\AgentNonsense\Doupi\`
- Linux：`~/.local/share/AgentNonsense/Doupi/`

该目录包含 `settings.json`、个人 `presets.json` 和默认 `sandbox/`。通过“保存设置”持久化参数；停止/关闭后后台任务随本次服务结束，不跨服务会话恢复。

GUI 只管理自己创建的服务进程；端口被占用时提示更换端口，不接管已有服务。关闭窗口会取消请求并回收自己启动的服务。所有 HTTP 请求只发送到 `127.0.0.1`，并绕过系统代理。文件工具继续受原有 sandbox 约束。

预览只保留最近 60,000 字符，复制/导出也使用这部分；计数展示累计收到的字符数。日志最多保留 2,000 行。连续流 120 秒没有收到任何数据时会停止预览。

## 开发验证

```sh
python -m unittest discover -s tests -v
python -m compileall -q agent_nonsense
```

安装 `.[gui]` 后，测试会以 Qt offscreen 平台实际启动服务进程，验证三种流式协议、连续流取消、任务启停、端口冲突、配置持久化、无效预设保护和窗口关闭后的进程清理。未安装 Qt 时只跳过 GUI 集成测试，配置与协议解析测试仍会运行。

CI 增加 Windows / Linux / macOS 桌面测试；配置在仓库推送后由 GitHub Actions 执行。没有在本机执行的系统不能视为已验证。

GUI 使用 [Qt for Python](https://doc.qt.io/qtforpython-6/)，选择 Essentials 仅安装本项目需要的 QtCore、QtGui、QtWidgets、QtNetwork 等基础模块。发布包含 Qt 的二进制时，请同时遵循 Qt / PySide 的许可证。
