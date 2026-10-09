# 桌面安装包

在 [GitHub Releases](https://github.com/wahahaha-cpu/agent-nonsense/releases) 下载。
无需安装 Python、Qt 或 VS Code。

| 系统 | 安装包 | 使用方式 |
| --- | --- | --- |
| Windows x64 | `Doupi-版本-windows-x64-setup.exe` | 双击安装，提供开始菜单入口及可选桌面快捷方式 |
| Linux x64 | `doupi_版本_amd64.deb` | Ubuntu 22.04+ / Debian 12+：`sudo apt install ./doupi_版本_amd64.deb` |
| macOS Apple Silicon | `Doupi-版本-macos-arm64.dmg` | 打开后将“豆皮.app”拖入 Applications |
| macOS Intel | `Doupi-版本-macos-x64.dmg` | 打开后将“豆皮.app”拖入 Applications |

Windows 安装到当前用户目录，不要求管理员权限，支持卸载。
Linux 安装到 `/opt/doupi`，创建 `doupi` 命令和桌面菜单入口；卸载使用 `sudo apt remove doupi`。
macOS 需要 13.0 或更高版本，卸载时将应用移入废纸篓。上述卸载均保留个人配置、剧本和 sandbox。

另提供 Windows portable.zip、Linux tar.gz、macOS app.zip。便携包需完整解压后启动，不能单独移动可执行文件。Linux tar.gz 仍需兼容的 glibc（2.35+）和 Qt 系统库，具体依赖见构建脚本的 DEB `Depends`。

当前包未使用 Windows 发布者证书或 Apple Developer ID 签名/公证，属于未签名分发版本。macOS 如拦截启动，可核对下载来源后从“系统设置 → 隐私与安全性”允许打开。包内 macOS 二进制使用本机 ad-hoc 签名，并在构建时校验完整性；这不等于 Apple 公证。

每组包附带对应的 `SHA256SUMS.txt`（名称带系统与架构前缀）、`BUILD-INFO.json` 及自检报告。预览版带 `desktop-preview-提交号` 标记，对应 PR 分支的具体提交；正式版使用 `desktop-vX.Y.Z` 标签。

## 构建

使用 Python 3.12，在目标系统上构建。PyInstaller 的打包说明见[官方文档](https://pyinstaller.org/en/stable/usage.html)，运行时路径处理见[官方说明](https://pyinstaller.org/en/stable/runtime-information.html)。

```sh
python -m venv .venv
# 激活环境，Windows 使用 .venv\Scripts\activate
source .venv/bin/activate
python -m pip install -r packaging/requirements.txt
python packaging/build_installers.py
python packaging/verify_installer.py
```

Windows 另外安装 Inno Setup 6，脚本会寻找 `ISCC.exe`。
Linux 另外安装 `dpkg-deb`、`desktop-file-validate` 和 Qt 依赖，完整列表见 `.github/workflows/installers.yml`；安装验证使用 `sudo`。
macOS 使用系统 `codesign`、`ditto` 和 `hdiutil`。
输出默认位于 `release/`；重建时指定新的空目录，如 `--output release-next`，避免把旧包混入新版本。

构建保留原版豆皮图标，转换出系统需要的 ICNS 和 PNG，不修改角色设计。Python、Qt、预设数据和依赖许可一起打包。

## 自动验证和发布

`Desktop installers` 工作流分别使用 Windows、Ubuntu、Apple Silicon Mac 与 Intel Mac runner。当前 runner 标签参考 [GitHub 官方镜像列表](https://github.com/actions/runner-images)。每个平台先运行源码测试，然后构建应用并执行 `--self-test REPORT.json`：

1. 加载原版图标和内置预设，个人预设写入临时用户目录。
2. 使用包内程序启动本地服务，检查健康状态。
3. 真实请求三种协议，检查流式正文与当前剧本标题。
4. 验证随机连续轮播保留同一连接，再取消输出。
5. 退出窗口并检查服务子进程已清理，安装资源未被修改。
6. 安装/提取安装包，重新运行上述自检；Windows 和 Linux 还验证卸载。

构建失败会保留诊断文件。只有四个平台全部通过，发布任务才会校验所有 SHA-256 并上传到 GitHub Releases。PR 运行只生成 Actions 附件；`codex/desktop-installers` 分支推送自动发布预览包；版本标签推送发布正式包。也可以在 Actions 手动运行，勾选 `publish` 生成预览版。

Windows 使用独立的 `doupi-server.exe` 保留进程日志管道，与 GUI 共享包内运行时；macOS/Linux 通过同一个应用的内部 `--doupi-server` 入口启动服务。它们都不调用用户系统里的 Python。
