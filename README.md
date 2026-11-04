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

截至 2026-11-04，个人远程访问的网络通道已部署，已验证手机 WireGuard 握手、云端到 Mac 看板的访问及用量/会话接口。Codex 和 DeepSeek Harness 通过 Mac 上按需启动的运行时执行手机发来的消息。

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
| Mac | `codex_runtime.py` + `codex app-server` | 按需启动 Codex 进程，复用会话处理连续消息 |
| Mac | SSH 客户端 | 保持反向隧道，断线后由 `launchd` 重新启动 |

### 部署与使用

- 服务器安装脚本：`tools/setup_private_relay.sh`；云安全组放行入站 UDP 51820，SSH 需可达。不开放公网 TCP 5173。
- Mac 安装脚本：`tools/install_mac_relay.py`；安装 `local.agent-phone.codex`、`local.agent-phone.gateway` 和 `local.agent-phone.tunnel` 三个基础 LaunchAgent；检测到 DeepSeek Harness CLI 时另外安装 `local.agent-phone.dsh`。
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

- Token 活动按天或周展示近一年各已接入客户端的合计用量，颜色从浅蓝到深蓝。缺少逐次时间的用量按会话日期归入。
- 最近项目按工作目录归组，点项目可查看它的历史会话。会话正文支持 Markdown。
- 用量每 30 秒刷新，当前会话每 4 秒轮询。
- 移动端布局及主屏幕图标配置。
- 手机可选择已有项目或默认工作台目录，新建 Codex 或 DeepSeek Harness 聊天并发送首条消息。两者均支持连续发送、后台执行状态和重复提交保护。

WorkBuddy 发送、交互式权限审批和完成通知尚未实现。

## 手机发送开关

设置里的 Codex 和 DeepSeek Harness 开关分别控制手机发送。开启后，第一次发送才会启动对应的子进程，空闲五分钟后自动退出并释放会话。手动刷新模型列表会短暂读取运行时目录，并在读取后退出临时进程。关闭后停止接收新任务，已受理的任务处理完成后断开。开关保存在 Mac 上，会话历史和用量仍可查看。

## 发送消息：Codex 常驻会话

手机开启 WireGuard 后，刷新页面，选择 Codex 的一段会话，在输入框输入消息并发送。回复由现有会话轮询显示。Mac 上的官方 `codex app-server` 按需启动，在空闲退出前复用已恢复的会话，不再逐条启动 `codex exec resume`。

```text
浏览器 POST /api/send（请求编号 + 会话 + 消息）
  → 私人网络 → Mac 网关校验并保存任务
  → 常驻控制器 → 官方 codex app-server（stdio JSON-RPC）
      新建聊天：thread/start；接入历史会话：thread/resume
      每轮发送：turn/start
      完成回执：turn/completed
  → 原会话历史 → /api/messages → 浏览器
```

### 使用边界

- Mac 上需安装并登录 Codex CLI。常驻服务使用本机账号和模型配置，桌面 App 可以关闭。
- 同一会话一次由一个 Codex 进程写入。手机发送完成后，点击输入框上方的「释放会话」，等页面确认释放，再在桌面点击「重试」。释放会保留历史，也允许手机稍后重新接入。
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
| `POST /api/send` | 以唯一请求编号提交消息，传入 `session` 接续会话，或传入 `project` 新建会话。重复提交返回原任务 |
| `GET /api/jobs?id=<请求编号>` | 查询执行状态 |
| `POST /api/jobs/acknowledge` | 用户核对结果后结束一条不明确的记录，不自动重发 |

写接口要求 JSON、当前令牌和合法来源。API 只接受私人 IP / localhost 的 Host；这是私人部署，不应直接发布到公网。

本地检查（不调用模型）：

```sh
python3 tools/test_control.py
python3 tools/test_gateway_http.py
node --check app.js
```

已实测连续两轮共用同一个 Codex PID、只恢复一次会话并记住上一轮内容；重启 HTTP 网关后该 PID 保持不变；受控重启 app-server 后可从历史恢复上下文。浏览器回执丢失重试、重复提交和原会话回复展示也已验证。入口调研及版本限制见 [Codex 发送验证](docs/CODEX-CONTROL.md)。WorkBuddy 的官方发送入口仍待授权验证，见 [控制调研](docs/OTHER-AGENT-CONTROL.md)。

## 发送消息：DeepSeek Harness

手机在「新建聊天」里选择 DeepSeek Harness，或从会话历史打开已有对话。Mac 服务通过官方 `dsh acp` 发送消息，页面从本机会话日志读取回复。

- 新建聊天和已有会话都能选模型。Codex 从 app-server 获取目录，DeepSeek 从 ACP 获取带提供商的模型目录。未指定时沿用客户端默认或会话已保存的模型。更换账号或配置后，可以在模型旁点「刷新」。
- DeepSeek ACP 可加载 Mac 上的 `~/.config/agent-phone/control/dsh-provider.patch.yml`。如需复用桌面中转站，只在该文件加入对应提供商的插件配置，并沿用 Harness 凭据引用。配置文件留在本机，权限设为 600。
- 已有会话沿用原工作目录。其他进程持有会话时，手机会提示占用。发送完成后可点「释放会话」，让其他进程接手。
- 手机端会取消 ACP 权限请求。连接中断或缺少轮次结束记录时，页面会显示「结果待确认」。
- 安装脚本会查找 PATH 中的 `dsh` 或官方桌面包内的 CLI。已有私人网络部署可重新运行安装脚本加入 DeepSeek 服务。
- DeepSeek 的进程标准错误保存在 `~/.config/agent-phone/control/dsh-acp.stderr.log`。

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
