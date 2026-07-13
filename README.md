# Agent Nonsense

Agent Nonsense is a local, zero-token agent status API with OpenAI Responses, OpenAI Chat Completions, Anthropic Messages, sandboxed file tools, and editable long-form presets.

Agent Nonsense 是一个本地 API 服务，提供 OpenAI Responses、OpenAI Chat Completions 和 Anthropic Messages 兼容接口。服务从可编辑的预置内容生成持续状态流，支持按字符输出、随机任务选择、sandbox 文件工具、自定义端口和流速配置。它不连接上游模型，所有兼容接口的 usage 均为 0。

## 安装

需要 Python 3.10 或更高版本，无运行时第三方依赖：

```powershell
python -m pip install .
```

安装后提供一个服务命令：

```powershell
agent-nonsense --help
```

启动有限流 API：

```powershell
agent-nonsense --host 127.0.0.1 --port 8787
```

端口可以在启动时通过命令行或环境变量指定；显式 `--port` 优先：

```powershell
$env:AGENT_NONSENSE_PORT = '9900'
agent-nonsense --continuous-stream --simulate-tools

# 临时覆盖环境变量
agent-nonsense --port 9901 --continuous-stream --simulate-tools
```

源码目录也可以运行兼容脚本：`python .\agent_nonsense_server.py`。

## 接入桌面 Agent

服务提供 OpenAI-compatible API。为让普通桌面客户端在聊天框里持续看到工作状态，启动连续流实例：

```powershell
agent-nonsense `
  --host 127.0.0.1 `
  --port 8788 `
  --continuous-stream `
  --delay 2.0 `
  --jitter 0.32 `
  --character-delay 0.06 `
  --simulate-tools
```

`--character-delay 0.06` 会把正文拆成单个字符流出，约每秒 16–17 个字符。每段正文结束后，`--delay 2.0` 与 `--jitter 0.32` 再产生约 2.0–2.32 秒的阶段停顿。请求可用 `character_delay` 临时覆盖逐字速度，`speed_factor` 会同时缩放两种间隔。

在支持 OpenAI Compatible 的桌面 agent 中填写：

```text
Provider: OpenAI Compatible
Base URL: http://127.0.0.1:8788/v1
API Key: local
Model: agent-nonsense
Streaming: enabled
```

如果桌面软件使用 OpenAI Responses API（请求路径为 `/v1/responses`，Codex 类客户端常见），同样使用上面的地址。若经过本地代理或配置切换器，请把它的上游 Provider 指向 `http://127.0.0.1:8788/v1`。

如果桌面软件使用 Anthropic/Claude 配置：

```text
Base URL: http://127.0.0.1:8788
API Key: local
Model: agent-nonsense
Streaming: enabled
```

连续实例会把每个 `stream: true` 请求保持打开，聊天框会以较慢且略有随机停顿的节奏持续收到更接近工作对话的内容，例如“我先看一下相关文件”“这里有两个边界条件需要核对”“我先跑一组针对性的测试”，直到客户端停止生成或断开连接。正文使用常见 AI Markdown，包括阶段标题、引用、加粗重点、任务清单和代码块；正文不会说明内部内容选择过程，也不添加额外的模拟标记。`GET /v1/models` 会返回 `agent-nonsense`，并保留 `mock-agent` 兼容别名。如果客户端支持自定义请求字段，也可以在普通实例中发送 `"continuous": true`。

加上 `--simulate-tools` 后，桌面兼容模式会真实执行 sandbox 内的 `list_files` -> `read_file` -> `write_file` -> `read_file` 校验，并把可读的 `tool.call` / `tool.result` 文本继续流回聊天框。工具只允许访问 `--sandbox` 指定目录；默认 sandbox 是当前目录下的 `.agent-nonsense-sandbox`，工作笔记写入其中的 `.agent-scratch/working-note.md`。

只有确认客户端支持完整 Responses 工具握手时，才额外加上 `--native-tools`；它会发送原生 `function_call` 事件，由客户端负责执行并回传工具结果。普通桌面聊天软件不要开启这个选项，否则客户端可能停在等待工具结果的状态。

## 预制长对话

预制剧本保存在 `agent_nonsense/presets.json`，当前包含文件读写、API 超时、前端状态、数据库迁移、依赖升级、CI 偶发失败、内存增长、并发竞态、认证权限和发布打包十组任务。每条新的聊天请求都会重新随机选择一组，不再根据 prompt 关键词固定主题；同一条流式响应内部保持一致。简洁纲要在加载时由 `longform.py` 编译为至少 5000 字的完整内容，每个阶段输出“判断、依据、风险、验证和下一步”，并在指定阶段触发 sandbox 工具。

需要可重复测试时，仍可通过请求显式指定剧本：

```json
{
  "model": "agent-nonsense",
  "stream": true,
  "continuous": true,
  "preset": "python-file-io",
  "simulate_tools": true,
  "input": "hi"
}
```

可用 ID：`python-file-io`、`api-timeout`、`frontend-state`、`database-migration`、`dependency-upgrade`、`ci-flaky-tests`、`memory-growth`、`concurrency-race`、`auth-permissions`、`release-packaging`。编辑 `agent_nonsense/presets.json`，或通过 `agent-nonsense --presets path/to/presets.json` 加载自定义文件。

## 持续假工作 Job

创建一个后台活动 job。`max_events: 0` 表示不设事件数量上限，`duration_seconds: 0` 表示持续运行直到停止：

Windows PowerShell 5.1 发送中文 JSON 时，建议先编码成 UTF-8 字节：

```powershell
$body = @{ prompt = '整理项目并修复测试'; modules = @('research', 'code_edit', 'test_run'); max_events = 0; duration_seconds = 60; speed_factor = 1.2 } | ConvertTo-Json -Depth 8
$utf8Body = [System.Text.Encoding]::UTF8.GetBytes($body)
$job = Invoke-RestMethod http://127.0.0.1:8787/v1/agent/jobs -Method Post -ContentType 'application/json; charset=utf-8' -Body $utf8Body
$job.job.id
```

PowerShell 7 通常可以直接发送 UTF-8 字符串；如果看到中文变成 `?`，仍然使用上面的字节写法。查看完整进度：

```powershell
$state = Invoke-RestMethod "http://127.0.0.1:8787/v1/agent/jobs/$($job.job.id)"
$state.job | ConvertTo-Json -Depth 5
```

查询活动：

```powershell
Invoke-RestMethod http://127.0.0.1:8787/v1/agent/jobs/$($job.job.id)
```

停止活动：

```powershell
Invoke-RestMethod http://127.0.0.1:8787/v1/agent/jobs/$($job.job.id)/stop -Method Post
```

也可以直接用活动流，不创建后台 job：

```powershell
curl.exe -N http://127.0.0.1:8787/v1/agent/activity `
  -H "Content-Type: application/json" `
  -d '{"prompt":"修一个文件读写 bug","modules":["code_edit","test_run","file_ops"],"max_events":20,"speed_factor":1.5,"stream":true}'
```

## OpenAI / Claude 兼容接口

OpenAI Chat Completions：

```powershell
Invoke-RestMethod http://127.0.0.1:8787/v1/chat/completions `
  -Method Post -ContentType 'application/json' `
  -Body '{"model":"agent-nonsense","stream":true,"modules":["code_edit","test_run"],"messages":[{"role":"user","content":"修复这个测试"}]}'
```

Claude Messages：

```powershell
Invoke-RestMethod http://127.0.0.1:8787/v1/messages `
  -Method Post -ContentType 'application/json' `
  -Body '{"model":"agent-nonsense","max_tokens":512,"messages":[{"role":"user","content":"解释这个错误"}]}'
```

两个接口都支持 `stream: true`、`modules`、`speed_factor` 和活动数量参数。响应里的 usage 固定为 0，并带有 `X-Mock-Agent: true` 与 `X-Token-Usage: 0` 响应头。

## 文件工具

工具端点是 `POST /tools/call`，路径始终限制在启动参数指定的 `sandbox` 目录内：

```powershell
Invoke-RestMethod http://127.0.0.1:8787/tools/call `
  -Method Post -ContentType 'application/json' `
  -Body '{"name":"list_files","arguments":{"path":"."}}'

Invoke-RestMethod http://127.0.0.1:8787/tools/call `
  -Method Post -ContentType 'application/json' `
  -Body '{"name":"read_file","arguments":{"path":"notes/demo.txt"}}'

Invoke-RestMethod http://127.0.0.1:8787/tools/call `
  -Method Post -ContentType 'application/json' `
  -Body '{"name":"write_file","arguments":{"path":"notes/demo.txt","content":"hello"}}'
```

## 模块和端点

内置模块：`research`、`code_edit`、`test_run`、`file_ops`、`debug_trace`。

- `GET /health`
- `GET /v1/agent/modules`
- `GET /v1/agent/jobs`
- `POST /v1/agent/jobs`
- `GET /v1/agent/jobs/{id}`
- `POST /v1/agent/jobs/{id}/stop`
- `POST /v1/agent/activity`
- `POST /v1/chat/completions`
- `POST /v1/responses`
- `POST /v1/messages`
- `POST /tools/call`

## 设计边界

- 不调用 OpenAI、Anthropic、Claude 或其他上游模型。
- 不访问网络，唯一的实际 I/O 是 sandbox 内的文件工具。
- 活动文本是预制模板加随机细节，参考 genact 的模块化、随机化和速度控制思路。
- 默认没有认证，只应绑定到 `127.0.0.1`；不要直接暴露到公网。
- `--native-tools` 只适用于实现完整 Responses 工具握手的客户端，普通桌面软件应使用 `--simulate-tools`。

## 开发与测试

```powershell
python -m pip install -e .
python -m unittest discover -s tests -v
python -m compileall -q agent_nonsense
```

构建 wheel：

```powershell
python -m pip wheel --no-deps --no-build-isolation . -w dist
```

GitHub Actions 会在 Windows 和 Linux、Python 3.10 与 3.13 上运行测试，并构建发布包。

## 项目结构

```text
agent_nonsense/
  longform.py      compile each preset to at least 5000 characters
  server.py        HTTP API, streaming, jobs and sandbox tools
  presets.json     editable long-form scenarios
tests/             standard-library unit and integration tests
pyproject.toml     packaging metadata and command entry points
```

完整字段说明见 [docs/API.md](docs/API.md)，发布步骤见 [docs/RELEASING.md](docs/RELEASING.md)。贡献流程见 [CONTRIBUTING.md](CONTRIBUTING.md)，安全边界与漏洞报告方式见 [SECURITY.md](SECURITY.md)，版本记录见 [CHANGELOG.md](CHANGELOG.md)。

## License

MIT
