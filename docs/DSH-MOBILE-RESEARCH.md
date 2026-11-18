# DSH 手机遥控端源码研究

研究日期：2026-11-18。范围：下载源码、静态阅读、与本项目比较；没有安装插件、启动参考应用、修改桌面配置或进行真机验证。

## 1. 本地参考源码

使用 `git clone --depth 1` 下载到独立目录，保留各自 Git 元数据和许可证；没有安装依赖、执行安装脚本或修改参考源码。

| 项目 | 本地目录 | 来源 | 固定提交 |
| --- | --- | --- | --- |
| DSH Mobile | `reference/dsh-mobile-research/dsh-mobile/` | https://github.com/saya-ch/dsh-mobile | `5c6c0f8978b6b4ebf64889d4124be57751182c13` |
| DSH Go | `reference/dsh-mobile-research/dsh-Go/` | https://github.com/ccch1mneyyy/dsh-Go | `246f503a1f51720091cbef173150fdf3939a23d4` |

现有 `.gitignore` 已忽略整个 `/reference/`，所以参考源码不会混进主项目提交；本文保留来源和版本以便重新获取。浅克隆包含当前检出的源码，不包含完整历史，也不代表下载了运行时依赖或发布安装包。

## 2. 最重要的区别：不是“有没有服务”，而是“谁执行会话”

手机总需要通信入口。插件方案也可能监听额外的 HTTPS 端口、运行隧道或者使用中继服务；不能把插件理解为完全没有额外服务。

真正应区分的是：

1. 手机请求进入电脑上已经运行的 DSH Host，让同一 Host 执行和报告状态；
2. 手机网关另外启动 DSH 进程，恢复同一磁盘会话后执行。

第二种仍使用真实 DSH 引擎，但不等于遥控桌面当前运行中的会话。共享历史文件也不等于共享内存状态、工具审批或执行所有权。

## 3. 本项目当前链路

```text
手机自有 Web UI
  → Python HTTP 网关 / 控制队列
  → DeepSeekRuntime
  → 单独的 dsh acp 进程
  → session/new 或 session/resume → session/prompt

会话历史 ← 读取本地 DSH 会话日志
桌面补充桥接 ← Unix socket → 工作区挂接 / 归档 / 恢复
```

代码证据：

- [ACP 进程定义](../dsh_runtime.py#L16-L24)：`arguments = ("acp",)`。
- [任务执行](../dsh_runtime.py#L135-L170)：创建/恢复会话，再调用 ACP `session/prompt`。
- [会话占用提示](../dsh_runtime.py#L182-L195)：明确处理其他 DSH 进程仍持有会话的情况。
- [权限请求](../dsh_runtime.py#L26-L30)：ACP `session/request_permission` 当前直接返回 cancelled，没有转成手机审批卡。
- [桌面桥](../tools/dsh-desktop-bridge/index.mjs)：提供 status、archive、restore、attach，聊天发送仍走 ACP。
- [部署记录](DEEPSEEK-SYNC.md)：隔离桌面 Host 已验证挂接、归档和恢复。日常环境仍待部署。

因此，你指出的差异成立：当前主要是“手机驱动额外 ACP 执行端”，不是完整的“桌面 DSH 遥控器”。现有桌面插件只是辅助桥，不是聊天控制后端。

## 4. DSH Mobile：代理现有 Host，并替换移动布局

```text
手机浏览器 / Android WebView
  → Mobile HTTPS 网关（设备授权 / 短 Session / CSRF）
  → HTTP / WebSocket 代理
  → 已运行的本机回环 DSH Web / Desktop Host
```

关键源码证据：

- [Host 服务注入与上游认证](../reference/dsh-mobile-research/dsh-mobile/src/plugin.ts#L129-L192)：使用 webServer / connection 等 Host 服务，取得上游认证信息；不是启动另一个 ACP 执行端。
- [回环上游限制](../reference/dsh-mobile-research/dsh-mobile/src/config.ts#L301-L314)：上游限制为带显式端口的 HTTP 回环 Origin。
- [HTTP 代理](../reference/dsh-mobile-research/dsh-mobile/src/gateway.ts#L4035-L4073) 与 [WS 代理](../reference/dsh-mobile-research/dsh-mobile/src/gateway.ts#L4545-L4568)：请求进入原 DSH，上游认证 Cookie 留在服务端，不交给手机。
- [前端启动图改写](../reference/dsh-mobile-research/dsh-mobile/src/gateway.ts#L662-L732)：解析 `__DSH_BOOT__` 并替换布局模块；不是简单 iframe，也不是独立实现全部聊天协议。
- [移动布局公共 slots](../reference/dsh-mobile-research/dsh-mobile/src/mobile-layout.ts#L1234-L1275)：复用 sidebar / main / conversation / details 等原有能力。
- [配对与撤销](../reference/dsh-mobile-research/dsh-mobile/src/access.ts#L298-L364)：持久设备凭据和短访问 Session 分层；撤销不仅删除手机本地记录。
- [Host 任务事件](../reference/dsh-mobile-research/dsh-mobile/src/task-events.ts#L1-L13)：任务结束以 Host 为权威，不以手机是否仍收到文字推断。

所以它确实最贴近“遥控桌面同一 DSH”的目标。它仍有自己的网关和额外监听端口，区别是网关不接管会话执行。

复用整套 DSH 页面有很强的功能继承优势，但启动图、公共 slots、认证和第三方插件契约也带来兼容维护成本。其配对设备能执行真实工具，应视为高权限受信任设备，而非只读访问。

## 5. DSH Go：独立 UI 不等于独立会话引擎

它有 Flutter UI、纯 Dart `dsh_client` 和不同连接载体，远程模式不能一概说成全部依赖桌面插件：

### SSH 路径

[remote_bootstrap.dart](../reference/dsh-mobile-research/dsh-Go/app/lib/remote/ssh/remote_bootstrap.dart#L65-L77) 显示，它通过 SSH 查找/启动自己管理的 `dsh web`，使用 `nohup`、回环地址和随机端口，保存 PID/日志供下次复用。

**这条路径也可能是另起 DSH Web 实例，而非直接接管 macOS Desktop。** 因而不能把 DSH Go 所有远程模式当作“桌面同一 Host”范例。

### DSHarness Remote 路径

- [远程后端](../reference/dsh-mobile-research/dsh-Go/app/lib/remote/relay/dsh_remote_backend.dart#L15-L24)：账号/主机目录、指纹固定、加密连接，尝试 LAN/P2P/TURN 后回退中继。
- [隧道载体](../reference/dsh-mobile-research/dsh-Go/packages/dsh_remote/lib/src/carrier/tunnel_carrier.dart#L1-L24)：把 DshRpc / DshMux 映射到 `harness.remote.call`、stream 等远程协议，受 Host 插件端点白名单限制。
- 远程 Host 插件本体属于另一个项目；本次只下载用户指定的两个仓库，没有审查第三方远程插件本体。

### 交互协议最值得参考

- [发送和停止](../reference/dsh-mobile-research/dsh-Go/packages/dsh_client/lib/src/session_api.dart#L432-L473)：`session/prompt` 支持 requestId、queue / steer；停止走 `session/cancel`。
- [订阅选项](../reference/dsh-mobile-research/dsh-Go/packages/dsh_client/lib/src/session_api.dart#L62-L113)：不仅订阅文字，还包括审批、问题、状态，以及断线后的完整基线同步。
- [会话状态投影](../reference/dsh-mobile-research/dsh-Go/packages/dsh_client/lib/src/session_api.dart#L137-L155)：区分每一代连接的完整 baseline 与后续增量。

这里的 Web API `session/prompt` 与我们的 ACP 同名方法**不是同一契约**，不能直接复制参数。前者是 Host inbox 接收请求，后者现有实现等待整轮结束。

它最值得借鉴的是：UI 与连接层分离、queue/steer 明确区分、状态由 Host 提供、重连后重新建立可信状态。Flutter 页面不能直接塞进我们当前 JavaScript Web UI。

当前 README 明确限定 DSHarness Remote：仅图片附件、无内嵌网页版、插件管理限开关、不支持 DS Bot 和对话日志导出；不能把所有本机功能算作远程可用。

## 6. 建议的方向（尚未实施）

针对“只做 DSH 的手机遥控端”，建议保留自有手机 Web UI，但把 DSH 的执行控制收敛到桌面 Host：

```text
自有手机 Web UI（借鉴 Go 的交互）
  → 认证 / 配对 / 安全传输入口（借鉴 Mobile）
  → 运行在桌面 DSH Host 内的插件或已验证官方 API
  → 桌面原有会话 / 工作区 / 工具 / 审批 / 事件流
```

外部 Python 服务可以按需要保留为静态资源或传输网关；关键是正常桌面遥控路径不要再让额外 ACP 进程争用同一会话。若以后仍保留 headless 模式，应明确显示为另一主机/执行端，不能伪装成桌面实时控制。

推荐实施次序：

1. 验证当前安装版本的 Host API 与插件扩展点，确认能访问桌面的会话目录和运行状态。
2. 做一条纵向最小链路：桌面已有会话 → 手机发送 → 桌面同一会话执行 → 手机实时看到事件。
3. 验证手机停止、工具审批、用户问题应答，再接 queue / steer。
4. 用“任务运行中关掉手机再回来”的场景验证 baseline、重连和重复请求防护。
5. 最后整理 UI、配对、多设备与通知，而非先复制两个完整客户端。

当前只完成研究，不承诺这些 API 在本机已验证可用，不安装插件、不改变现有服务、不停止任务。

## 7. 复用与许可

- DSH Mobile：项目声明 Apache-2.0。实际复用时保留许可证及适用版权/NOTICE，并核对被取用文件和第三方依赖。
- DSH Go：主体 AGPL-3.0，SDK / examples 为 MIT，部分第三方文件另有许可（例如远程 carrier 顶部 SPDX 为 MIT）。不能把整个仓库都视为 MIT。
- Go 的品牌、标识和吉祥物不在代码开源授权范围内。优先借鉴交互和协议设计；复制代码前逐文件核对许可证与衍生作品义务。

## 8. 验证范围

已验证：两次 clone 成功，记录 HEAD，两个参考仓库 `git status --short` 均无改动，参考目录被主项目现有 ignore 规则排除。

未验证：Android/iOS 安装、运行时兼容、配对、跨网连接、实时同步、后台通知。未安装任何参考依赖或更改用户桌面 DSH profile。
