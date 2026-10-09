Python 和 Qt 已包含在安装包中，无需自行安装开发环境。

| 系统 | 推荐下载 | 安装 |
| --- | --- | --- |
| Windows x64 | `windows-x64-setup.exe` | 双击运行安装向导 |
| Linux x64（Ubuntu 22.04+ / Debian 12+） | `amd64.deb` | `sudo apt install ./doupi_版本_amd64.deb` |
| macOS Apple Silicon | `macos-arm64.dmg` | 将豆皮拖入 Applications |
| macOS Intel | `macos-x64.dmg` | 将豆皮拖入 Applications |

另附 Windows portable.zip、Linux tar.gz 与 macOS app.zip。解压便携包时保留整个目录。
SHA256SUMS 文件用于校验下载完整性，BUILD-INFO 与 selftest 文件记录构建环境和应用检查结果。

每份包都经过原版图标和预设加载、后台服务启动、三种协议 SSE 预览、随机连续轮播、停止输出和退出清理检查；安装器还会在对应系统中安装/提取后启动验证。

当前安装包没有 Windows 发布者签名和 Apple Developer ID 签名/公证，系统可能显示未知发布者提示。macOS 如被拦截，可核对仓库来源后在“系统设置 → 隐私与安全性”中允许打开。

个人设置、剧本与 sandbox 保存在用户数据目录，卸载应用会保留这些数据。
