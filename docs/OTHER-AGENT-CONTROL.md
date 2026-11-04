# DeepSeek Harness 和 WorkBuddy 控制调研

2026-11-04。网关已接通 Codex 和 DeepSeek Harness，WorkBuddy 仍为只读。

## DeepSeek Harness

本机桌面版 0.2.1-rc.5 自带 CLI，路径为 `/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh`。之前的记录只检查了桌面入口和 PATH。内置 CLI 提供 `dsh acp`、`dsh web`，以及支持 `--session-id` 和 JSON 事件的单次执行入口 `dsh headless`。首选 ACP，通过标准输入输出使用 JSON-RPC，可保持进程常驻。[官方仓库](https://github.com/deepseek-ai/deepseek-harness) · [ACP 实现](https://github.com/deepseek-ai/deepseek-harness/tree/8bd07339/packages/acp/acp/src)

用临时 `DSH_HOME` 实测了以下流程。测试仅操作空白会话，没有调用模型或写入日常会话目录。

- `initialize` 返回协议版本 1，并声明 `list`、`resume`、`close` 能力。
- `session/new` 成功。退出进程后，第二个进程通过 `session/list` 找到原 ID，再以原工作目录调用 `session/resume` 成功。
- 两个进程同时打开同一会话时，第二个进程恢复失败，返回已有写入者。首个进程调用 `session/close` 后，第二个进程即可恢复。这个结果来自两个 ACP 进程，桌面与 ACP 之间的交接待单独验证。

已在手机尺寸浏览器验证新建及连续两轮回复。也用第二个真实 ACP 进程验证了会话占用和双向释放。桌面 App 界面的交接仍待验证。

ACP 的 `end_turn` 也可能对应模型出错或被阻止。适配器查验发送后新增的本机 `turn/end` 日志，只有确认为 `completed` 时才显示执行成功。额外权限请求在手机侧取消。


## WorkBuddy

本机桌面版为 5.9.3。官方移动端同账号连接电脑后，支持续聊桌面会话、在当前工作空间新建任务和停止执行。[多端协同文档](https://www.workbuddy.cn/docs/workbuddyapp/features/Multidevice)

第三方也有官方入口。开放平台的本地助理 API 需要注册应用、通过 OAuth 2.1 获得授权，可查电脑端本地助理在线状态、向助理发消息，再用返回的 `message_id` 增量轮询历史。文档的发送请求只列出 `content` 和 `msg_type`，没有桌面会话 ID、工作目录或客户端幂等键。公开文档尚不足以确认它能续接 agent-phone 列出来的任意 WorkBuddy 会话。文档中的另一个 ACP 接口属于 WorkBuddy 云端任务；CodeBuddy Code 的本地 HTTP API 属于另一款产品。[WorkBuddy Open API](https://open.workbuddy.cn/docs/openapi) · [CodeBuddy Code HTTP API](https://www.workbuddy.cn/docs/cli/http-api)

WorkBuddy 的下一步是用已授权的测试应用验证本地助理 API，核对消息实际落在哪条对话、是否能对应现有本地会话，以及请求回执丢失后能否核对结果。在能指定旧会话之前，第三方发送入口可以单独作为「WorkBuddy 助理」，旧会话续聊使用官方移动端。当前尚未做 OAuth 或发送实测。

## 开源项目参考

| 项目 | 可以借鉴的实现 |
| --- | --- |
| [jep](https://github.com/tinybig-ai/jep/blob/51a66db/src/core/ports.ts) | `HarnessAdapter` 把健康检查、会话与发送封装起来，供不同前端使用。agent-phone 可借这个边界，把 Codex 和 DeepSeek 的协议差异留在各自的适配器里。 |
| [T3 Code](https://github.com/pingdotgg/t3code/blob/059804df/docs/orchestration-v2/provider-capability-system.md) | 由各运行时声明能力，界面按能力显示操作。WorkBuddy 的历史续聊与本地助理发送应分别标明。 |
| [Happy](https://github.com/slopus/happy/blob/8640012/docs/plans/codex-app-server-migration.md) | Codex app-server 迁移记录可用于对照常驻进程、会话与事件的分工。 |
| [MobileCLI](https://github.com/bigph00t/MobileCLI/blob/32ff1fd/cli/src/pty_wrapper.rs) | PTY 将终端的输入输出转发到手机，适合终端本身就是交互入口的工具。当前 DeepSeek 已有结构化 ACP，WorkBuddy 则需要验证官方接口的会话范围。 |

WorkBuddy 先完成授权和会话归属验证，再决定是否能接入已有聊天的发送框。
