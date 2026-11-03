# agent-phone 开发计划：外网访问（查看）+ 手机操控（输入）

> 记录时间：2026-11-03
> 背景：目前 agent-phone 只能在局域网内用（`http://192.168.5.7:5173`，依赖本会话跑着 `python3 server.py`）。
> 目标：① 不在家的网络里也能**看**（消耗统计、会话内容）；② 能在手机上**发消息操控**智能体。
> 原则：只借开源项目的架构思路，不 fork 大仓库；用现有「纯静态 PWA + Python 零依赖网关」实现轻量版。

---

## 一、网络问题：让手机在任何网络下都能访问

### 现状
- 数据全部在 Mac 本地磁盘（`~/.workbuddy/traces`、`~/.codex/sessions`、`~/.dsh`），手机够不到，必须由 Mac 上的 server.py 提供接口。
- 手机 ↔ Mac 中间隔什么不重要，**关键是加密和鉴权**，尤其入口挂上公网之后。

### 方案对比（按推荐顺序）

| # | 方案 | 原理 | 成本 | 优点 | 缺点 |
|---|------|------|------|------|------|
| 1 | **Tailscale**（最省事） | WireGuard 组网，手机装 App 后等于永远在局域网里，直接访问 `http://<Mac的Tailscale IP>:5173` | 免费（个人 100 设备） | 零代码改动、零暴露、端到端加密 | 手机要装 Tailscale；国内偶尔连不上协调服务器 |
| 2 | **Cloudflare Tunnel**（免服务器） | Mac 跑 `cloudflared` 反向连 CF，得到一个 HTTPS 域名，可配 Access 访问策略 | 免费 + 一个域名（¥10/年级别） | 不买服务器、不用备案、自带 HTTPS | 国内直连速度看运气；域名要托管到 CF |
| 3 | **frp 内网穿透** | VPS 跑 frps，Mac 跑 frpc，把 5173 端口映射到 VPS | VPS ¥24~60/月 | 简单直接，国内 VPS 快 | 公网暴露端口，靠 Token 保护；国内绑域名 80/443 要备案 |
| 4 | **VPS 自建加密中继**（完全自主） | Mac 守护进程主动连出到 VPS（长连接/WebSocket），手机连 VPS；**学 Happy：所有内容离开 Mac 前先 AES-256-GCM 加密，VPS 只存/转密文**，密钥只在手机和 Mac | VPS 同上 | 完全可控、可承载控制通道与推送 | 工作量最大，要自己维护中继与密钥体系 |
| 5 | Happy 官方中继 | 用现成加密中继，不自建 | 免费 | 开箱即用 | 只覆盖它支持的 agent，我们的看板数据带不出去 |

### 决策
- 短期：**Tailscale**（一行不改马上能用）；不满意速度换 **CF Tunnel**。
- 长期（想做产品/随时分享给别人看）：**方案 4 自建中继**，香港/海外 VPS 免备案。
- 买 VPS 注意：国内机器绑域名走 80/443 需 ICP 备案；不想备案选香港节点。
- 无论哪条路，server.py 都要先加**简单 Token 鉴权**（现成代码公开在局域网无所谓，上公网前必须有）。

---

## 二、输入/控制问题：手机发消息 → Mac 上的智能体干活

### 现状（2026-11-03 查证）
- 发送框是占位：`app.js` 的 `send()` 只弹 toast「发送通道尚未接入网关」。
- 各客户端有无"注入消息"接口（逐一验证过）：

| 客户端 | 控制可行性 | 入口 |
|--------|-----------|------|
| Codex | ✅ **真·续接会话** | `codex exec resume <session-id> "消息"`（本机 `/opt/homebrew/bin/codex` 已验证有该子命令）；回复写回同一 rollout 日志 → 现有 4 秒轮询自动刷出，闭环天然成立 |
| DeepSeek Harness | ⚠️ 无 CLI | `/Applications/DeepSeek Harness.app` 是纯 GUI（包内无命令行），只能 AppleScript 模拟键入（需辅助功能授权、App 在前台），可靠性一般 |
| WorkBuddy | ⚠️ 无注入接口 | **官方手机 App 才是正解**：v2.7.0+ 有远程下任务 + 远程控制电脑（2026-10-28 上线），要求 Mac 端 ≥5.9.3（本机满足）；"设置 → 设备连接"开启同账号远程连接，不耗 Token |
| Claude / Antigravity | 未接入 | 无本地用量日志，控制也无从谈起 |

### 开源项目可抄的点

| 项目 | 仓库 | Stars | 抄什么 |
|------|------|-------|--------|
| Happy | github.com/slopus/happy | ~24k | ① 端到端加密方案（AES-256-GCM + NaCl secretbox，每会话独立密钥，中继只见密文）；② `happy codex` 包装器思路：本地 wrapper 接管 CLI 会话，手机/电脑随时交接控制权；③ 推送通知（等授权/报错时弹通知） |
| T3 Code | github.com/pingdotgg/t3code | ~38k | ① "agent harness 控制台"定位：一个入口管本机所有 agent，复用现有订阅；② 权限模式/多账号管理的产品化设计 |
| jep | github.com/tinybigai/jep | 新 | ① HarnessAdapter 抽象：一个 daemon 统一适配 codex/claude/opencode；② 自带 macOS launchd 安装脚本（`scripts/install.sh`）可直接参考；③ Telegram 机器人也能当客户端（不用装 App 的控制通道） |
| MobileCLI | github.com/bigph00t/MobileCLI | — | ① PTY 流式方案（终端原样串到手机，审批按钮识别各 CLI 的确认提示）；② pairing QR 配对 + Tailscale/LAN 双模式 |
| agentsview | 已克隆在 `reference/agentsview` | — | 只读看板的日志解析（已吸收进 server.py） |

### 目标架构

```
手机 PWA（现有界面，加发送框真实通道）
        │ HTTPS + Token
  [中继层] Tailscale 直连 / CF Tunnel / VPS 加密中继（学 Happy 只转密文）
        │ 加密长连接
  Mac 守护进程（扩展现有 server.py）
   ├─ 查看侧（已实现）：读三客户端日志 → /api/usage /api/sessions /api/messages
   └─ 控制侧（待做）：POST /api/send
        ├─ Codex → subprocess: codex exec resume <id>，后台执行
        ├─ DeepSeek → 暂缓（或 AppleScript）
        └─ WorkBuddy → 提示用官方 App
   回复落回日志文件 → 手机 4 秒轮询自动显示（闭环已通，无需另做推送）
```

---

## 三、落地顺序（每步独立有价值）

1. **鉴权**：server.py 加 Bearer Token（一次性，几十行），公网前置条件
2. **控制闭环（先局域网）**：`/api/send` + `codex exec resume`，手机端对 Codex 真·对话
3. **外网查看**：Tailscale（5 分钟）或 CF Tunnel（半小时，需域名）
4. **外网控制**：中继层转发 /api/send（自建 VPS 时抄 Happy 的 E2E）
5. **launchd 常驻**：开机自启 server.py（参考 jep 的 install.sh）
6. **可选增强**：推送通知（审批请求/报错）、DeepSeek 的 AppleScript 控制、把 WorkBuddy 官方远程控制入口链进看板

## 四、已确认的技术事实（避免重复调研）

- `codex exec resume <id>` / `codex exec fork <id>` 均存在（`codex exec --help` 已验证）
- 本机无 Java/Android SDK：要打包真 APK 需先装 JDK17 + cmdline-tools + Capacitor
- 无头 Chrome 内容区最小宽 500px；改前端后验证要加 `?v=timestamp` 防缓存
- server.py 改动后必须 kill + 重启（会话内 run_in_background 方式跑，会话结束即停）
- WorkBuddy 官方远程控制要求：手机 App ≥2.7.0 + Mac 端 ≥5.9.3（本机 5.9.3 ✓）
