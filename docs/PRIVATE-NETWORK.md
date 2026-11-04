# 私人远程访问

使用 WireGuard 和 SSH 反向隧道，不对公网开放看板 HTTP 端口。

```text
手机 WireGuard（10.77.73.2）
  → 云服务器 WireGuard（10.77.73.1，公网 UDP 51820）
  → SSH 反向隧道（只监听 10.77.73.1:5173）
  → Mac 网关（127.0.0.1:5173）
```

手机只路由 `10.77.73.1/32`，不修改 DNS，也不接管其他网络流量。没有配置 NAT 或内网转发。
WireGuard 到云服务器、SSH 到 Mac 分别加密；云服务器作为受信任端点能够看到经过它的数据，非端到端加密中继。

## 部署

1. Ubuntu 云服务器安装 `wireguard-tools`、`qrencode`。
2. Mac 生成专用 Ed25519 隧道密钥，不要复用 root 管理密钥。
3. 将 `tools/setup_private_relay.sh` 复制到服务器，以 root 执行，将公网 IPv4 作为参数，Mac 的隧道公钥通过标准输入传入。
4. 云防火墙允许入站 UDP 51820；不用开放公网 TCP 5173。如果 Ubuntu 的 UFW 已启用，安装脚本会添加 UDP 51820 和仅限 WireGuard 接口的手机看板访问规则，保留原有策略。
5. Mac 确认 SSH 主机指纹已记录后运行：

```sh
python3 tools/install_mac_relay.py <服务器IP> --key ~/.ssh/id_ed25519_agent_phone_tunnel
```

安装脚本配置专用 SSH 用户 `agent-phone-tunnel`：只允许反向转发到指定私人地址和端口，禁止命令会话、终端和本地转发。不会修改 root 的登录方式。

服务器手机配置位于 `/etc/agent-phone/phone.conf`，二维码位于 `/etc/agent-phone/phone-qr.png`，均只允许 root 读取。重复执行安装脚本会保留已有配对。

手机使用 WireGuard 的“扫描二维码”导入，连接后访问 `http://10.77.73.1:5173`。二维码和配置包含手机私钥，不要上传仓库或分享给其他人；同一配置只给一台设备使用。

## 运行与排查

- Mac 的基础 LaunchAgent 包括`local.agent-phone.gateway`（网页网关）、`local.agent-phone.tunnel`（SSH 隧道）、`local.agent-phone.codex`（常驻控制器及其官方 app-server 子进程）。如已安装 DeepSeek Harness CLI，安装脚本还会配置 `local.agent-phone.dsh`。这些服务在用户登录后启动，退出后自动重启；启动日志在 `~/Library/Logs/agent-phone/`。
- Mac 必须保持开机、已登录、联网且不休眠。LaunchAgent 不是登录前的系统服务。
- 服务器服务：`systemctl status wg-quick@apwg0`；查看握手：`wg show apwg0`，不要使用会显示私钥的 `wg showconf` 或 `wg show all dump`。
- 连接开关打开不等于握手成功。如果没有最近握手，检查公网 UDP 51820 的云防火墙规则以及手机网络。
- 服务器执行 `curl http://10.77.73.1:5173/` 可验证 SSH→Mac 通道；这不代表手机→服务器已经连通。
- 手机通过客户端导入本地配置文件也可以配对，无需扫描。

## 停用

Mac 使用 `launchctl bootout gui/$(id -u)/local.agent-phone.tunnel` 停止隧道，网关同理。
服务器使用 `systemctl disable --now wg-quick@apwg0` 停用私人网络。
撤销丢失手机的访问权限需要从服务器 WireGuard 配置删除对应 peer，并同步运行时配置。

网关没有应用层登录，部署时必须保持回环监听和私人地址入口。静态托管只允许前端资源，不提供源码、Git 数据或目录列表。

## 发送功能

私人通道同时承载只读接口和 Codex 的发送/状态接口，不需要新增公网端口。刷新手机页面后即可使用常驻 Codex 会话。请求编号和任务状态保存在 Mac；消息从浏览器经私人通道交给 Mac 上的官方 `codex app-server` 执行，云端不负责运行 Codex，也不需要打开桌面 App。

手机页面使用本地存储保留待确认请求，HTTP 回执丢失时可复用原编号确认结果。常驻控制器独立于网关，已验证网关重启不会重启 Codex 或重复发送任务。同一会话首次恢复后可以连续多轮使用；Codex 连接中断时，不自动重放结果不明的消息。不要将网关改为公网可访问：目前的防跨站令牌不是用户账号认证，多人隔离尚未实现。
