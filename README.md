# agent-phone

面向手机的多智能体工作台，通过 Mac 本地网关读取 WorkBuddy、Codex 和 DeepSeek Harness 的用量与会话记录。

## 本地手动启动

需要 Python 3。读取 DeepSeek Harness 正文还需要系统命令 `zstd`。

```sh
python3 server.py
```

本机访问 `http://localhost:5173`；同一局域网内的手机访问 `http://<Mac 的局域网 IP>:5173`。

手动启动默认监听 `0.0.0.0:5173`，只提供查看，发送能力关闭；尚无应用层鉴权，仅适合可信局域网，不应直接暴露到公网。下面的私人远程部署会将 Mac 网关改为只监听 `127.0.0.1:5173` 并启用发送。

## 网络方案：WireGuard + SSH 反向隧道

截至 2026-11-04，个人远程访问的网络通道已部署，已验证手机 WireGuard 握手、云端到 Mac 看板的访问及用量/会话接口。Codex 消息发送使用官方 app-server 常驻模式，见下文。

```text
手机浏览器：http://10.77.73.1:5173
    │ 手机 WireGuard：加密发送到云服务器公网 UDP 51820
    ▼
云服务器 WireGuard：手机通过独立密钥接入私人网络
    │ 私人看板入口：10.77.73.1:5173
    ▼
云服务器 SSH 服务 ⇄ Mac 主动建立的 SSH 加密反向隧道
    ▼
Mac 网关：127.0.0.1:5173 → 本地会话日志
```

Mac 没有公网 IP 也可以使用：Mac 主动连接云服务器的 SSH 端口 22，申请私人地址上的转发入口；手机请求经这个入口沿已有隧道到达 Mac，响应原路返回。

| 位置 | 程序 / 服务 | 职责 |
| --- | --- | --- |
| 手机 | WireGuard 客户端 | 扫码配对，只将 `10.77.73.1/32` 的流量送到服务器 |
| 手机 | 浏览器前端 | 显示看板，轮询用量和会话内容 |
| 云服务器 | `wg-quick@apwg0` | 提供私人网络连接，使用 UDP 51820 |
| 云服务器 | `sshd` | 接收 Mac 的连接，只在私人地址转发看板请求 |
| Mac | `server.py` | 提供网页及接口，按请求读取本地日志 |
| Mac | `codex_runtime.py` + `codex app-server` | 管理常驻 Codex 进程，复用会话处理连续消息 |
| Mac | SSH 客户端 | 保持反向隧道，断线后由 `launchd` 重新启动 |

### 部署与使用

- 服务器安装脚本：`tools/setup_private_relay.sh`；云安全组放行入站 UDP 51820，SSH 需可达。不开放公网 TCP 5173。
- Mac 安装脚本：`tools/install_mac_relay.py`；安装 `local.agent-phone.codex`、`local.agent-phone.gateway` 和 `local.agent-phone.tunnel` 三个 LaunchAgent，用户登录后启动，进程退出后重新启动。
- 手机导入独立 WireGuard 配置，开启连接后打开 `http://10.77.73.1:5173`。不修改手机 DNS，也不接管其他上网流量。
- 私钥、手机配置、二维码保存在仓库之外，不提交到 GitHub。换服务器需要迁移隧道，并更新手机配对配置。

完整安装、排查和停用步骤见 [私人远程访问](docs/PRIVATE-NETWORK.md)。

### 当前边界

- Mac 必须保持开机、用户已登录、联网且不休眠；网关和隧道不依赖当前聊天窗口运行。
- 会话和智能体仍在 Mac 上，云端不保存会话副本。平时保持隧道连接，页面发起请求时返回数据。
- 手机到云端、云端到 Mac 分别加密；云服务器是受信任的中转端，能够接触转发内容，不是只见密文的端到端加密中继。
- 入口依靠 WireGuard 密钥和受限 SSH 隧道控制访问，网关尚无应用层登录。只允许前端静态资源，不提供源码、Git 数据或目录列表。
- 当前仅部署单用户连接。多人共用服务器需要独立配对、隧道入口及访问隔离，不能分享同一个二维码。

## 已有功能

- 用量统计、活跃热力图和客户端看板。
- 最近项目、历史会话与 Markdown 正文展示。
- 用量每 30 秒刷新，当前会话每 4 秒轮询。
- 移动端布局及主屏幕图标配置。
- Codex 常驻会话连续发送、后台执行状态、重复提交保护和失败提示。

WorkBuddy / DeepSeek Harness 的发送、交互式权限审批和完成通知尚未实现。断连时部分用量界面仍会显示演示数据。

## 发送消息：Codex 常驻会话

手机开启 WireGuard 后，刷新页面，选择 Codex 的一段会话，在输入框输入消息并发送。回复由现有会话轮询显示。Mac 上的官方 `codex app-server` 持续运行，同一会话后续消息复用已恢复的会话，不再逐条启动 `codex exec resume`。

```text
浏览器 POST /api/send（请求编号 + 会话 + 消息）
  → 私人网络 → Mac 网关校验并保存任务
  → 常驻控制器 → 官方 codex app-server（stdio JSON-RPC）
      首次接入：thread/resume；后续每轮：turn/start
      完成回执：turn/completed
  → 原会话历史 → /api/messages → 浏览器
```

### 使用边界

- Mac 上需安装并登录 Codex CLI。常驻服务使用本机账号和模型配置，桌面 App 可以关闭。
- 常驻服务与其他 CLI / 桌面进程共享会话历史，但不能同时写入。遇到占用提示，需要先释放原进程持有的会话。常驻服务也会持续持有已加载会话；若要交还其他客户端，需停止 `local.agent-phone.codex` 服务，再由其他客户端接入。不会自动杀掉其他进程或删除锁文件。
- 这不是桌面实时同步模式。在其他客户端查看更新时可能需要重新打开会话。
- 同一会话只允许一个发送任务；正在执行的会话会被拒绝发送。首版不支持忙碌时排队、引导或中止任务。
- 原会话为只读时保持只读；其他会话最多使用 `workspace-write`，不启用完全访问模式，也不自动批准额外权限。需要授权时回 Mac 处理。
- 断线后不要复制消息重复发送。页面保留请求编号，可点“确认发送结果”；网关重启后不会自动重跑同一请求。
- “结果待确认”需要先核对会话历史，再手动结束记录，不会自动重试。明确失败的消息会恢复到输入框，供用户决定是否再发送。
- 浏览器必须可使用本地存储，以保存待确认请求。切换会话保留的普通草稿只在当前页面内存中，刷新页面不会保留普通草稿。

任务数据库和服务日志保存在 Mac 的 `~/.config/agent-phone/control/`，目录权限为 700，任务数据库和日志为 600，包含消息内容，不提交到仓库。常驻控制器通过用户私有的 `runtime.sock` 接收唤醒和健康查询，不开放 Codex 的公网端口。HTTP 网关重启不影响常驻进程和会话。存储暂未自动清理。

服务异常退出后会重新启动并按需恢复历史；连接中断时，正在执行的请求标记为“结果待确认”，不会自动重放。明确尚未开始的队列请求可以继续处理。

查看常驻服务：`launchctl print gui/$(id -u)/local.agent-phone.codex`。重启使用 `launchctl kickstart -k gui/$(id -u)/local.agent-phone.codex`；它会中断尚未完成的轮次，操作前应先检查任务状态。查看日志：`runtime.log` 记录服务生命周期与请求错误，`app-server.stderr.log` 记录 Codex 标准错误。

### 接口与验证

| 接口 | 用途 |
| --- | --- |
| `GET /api/control` | 查询发送能力、防跨站请求令牌和常驻服务健康状态 |
| `POST /api/send` | 以唯一请求编号提交消息；相同编号与内容重复提交返回原任务 |
| `GET /api/jobs?id=<请求编号>` | 查询执行状态 |
| `POST /api/jobs/acknowledge` | 用户核对结果后结束一条不明确的记录，不自动重发 |

写接口要求 JSON、当前令牌和合法来源。API 只接受私人 IP / localhost 的 Host；这是私人部署，不应直接发布到公网。

本地检查（不调用模型）：

```sh
python3 tools/test_control.py
python3 tools/test_gateway_http.py
node --check app.js
```

已实测连续两轮共用同一个 Codex PID、只恢复一次会话并记住上一轮内容；重启 HTTP 网关后该 PID 保持不变；受控重启 app-server 后可从历史恢复上下文。浏览器回执丢失重试、重复提交和原会话回复展示也已验证。入口调研及版本限制见 [Codex 发送验证](docs/CODEX-CONTROL.md)。下一步分别接入 WorkBuddy、DeepSeek Harness，再考虑审批与桌面实时同步。

## 结构

- `index.html`、`styles.css`、`app.js`：无构建步骤的原生前端。
- `server.py`：Python 标准库 HTTP 网关，提供静态文件及 `/api/usage`、`/api/sessions`、`/api/messages`。
- `control.py`：发送能力查询、私有任务存储、请求编号与会话校验。
- `codex_runtime.py`：常驻控制器，维护官方 app-server 连接和已加载会话，处理回执与断线恢复。
- `tools/`：日志格式探测、私人网络部署脚本和 HTTP 访问边界测试。
- [开发计划](docs/DEV-PLAN.md)：外网访问及手机控制的方案记录。

数据从当前用户的 `~/.workbuddy/projects/`、`~/.codex/sessions/` 和 `~/.dsh/` 读取，不随代码上传。

## 参考项目

- [TokenTracker](https://github.com/mm7894215/TokenTracker)：用量解析参考。
- [agentsview](https://github.com/kenn-io/agentsview)：会话日志与看板参考。

本地 `reference/` 副本不纳入版本管理，运行本项目无需这些副本。
