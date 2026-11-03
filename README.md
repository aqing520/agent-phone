# agent-phone

面向手机的多智能体工作台，通过 Mac 本地网关读取 WorkBuddy、Codex 和 DeepSeek Harness 的用量与会话记录。

## 启动

需要 Python 3。读取 DeepSeek Harness 正文还需要系统命令 `zstd`。

```sh
python3 server.py
```

本机访问 `http://localhost:5173`；同一局域网内的手机访问 `http://<Mac 的局域网 IP>:5173`。

当前网关监听 `0.0.0.0:5173`，尚无鉴权，仅适合可信局域网，不应直接暴露到公网。

## 已有功能

- 用量统计、活跃热力图和客户端看板。
- 最近项目、历史会话与 Markdown 正文展示。
- 用量每 30 秒刷新，当前会话每 4 秒轮询。
- 移动端布局及主屏幕图标配置。

已提供 [WireGuard + SSH 私人远程访问部署](docs/PRIVATE-NETWORK.md)，无需开放公网网页入口。
发送消息、远程控制和完成通知尚未实现。断连时部分用量界面仍会显示演示数据。

## 结构

- `index.html`、`styles.css`、`app.js`：无构建步骤的原生前端。
- `server.py`：Python 标准库 HTTP 网关，提供静态文件及 `/api/usage`、`/api/sessions`、`/api/messages`。
- `tools/`：本地日志格式探测脚本。
- [开发计划](docs/DEV-PLAN.md)：外网访问及手机控制的方案记录。

数据从当前用户的 `~/.workbuddy/projects/`、`~/.codex/sessions/` 和 `~/.dsh/` 读取，不随代码上传。

## 参考项目

- [TokenTracker](https://github.com/mm7894215/TokenTracker)：用量解析参考。
- [agentsview](https://github.com/kenn-io/agentsview)：会话日志与看板参考。

本地 `reference/` 副本不纳入版本管理，运行本项目无需这些副本。
