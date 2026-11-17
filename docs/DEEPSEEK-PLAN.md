# DeepSeek 手机平台开发计划

> 当前主线：只开发 DeepSeek Harness。Codex / WorkBuddy 保留原状，不修改其适配逻辑、不进行其测试或真实调用。不创建分析子代理。

## 进度

### 第一批：会话发现与内部会话过滤（已实现并部署到本机网关）

- 从 `sessions/**/session.v4.jsonl.zstd` / `session.jsonl.zstd` 发现已保存的会话。
- projection checkpoint 仅辅助读取标题、统计；缺失或损坏时回退到事件日志。
- 使用会话头 `parentSession`、`parentSessionId`、`delegationDepth`、`origin=subagent` 排除内部子会话。
- 空白/只有运行时注入而无用户消息的会话不进入历史和项目聚合。
- 同样阻止内部子会话进入手机续聊及正文读取入口，不删除底层记录。
- 从日志头恢复 cwd，避免缺少缓存就无法续聊。
- 新增隔离测试 `python3 tools/test_dsh_discovery.py`；不调用模型、不读取日常会话。

### 当前额外调整：可见性与会话历史一致

- 首页智能体开关现在同时控制看板卡片、会话历史、最近项目和会话入口。
- 首次升级默认只显示 DeepSeek，WorkBuddy/Codex 及未接入客户端隐藏；其他真实会话不删除。
- 用户重新打开某个智能体后，它的历史和项目会重新出现。
- 隐藏当前正在查看的智能体时会回到主页；直接打开隐藏来源的会话会被拒绝。
### 第二批：手机端归档（已实现，桌面状态暂不联动）

- DeepSeek 会话列表支持“归档”和“恢复”。
- 归档记录保存在 Mac 私有的 `phone-archive.sqlite`，不改写 Harness 原始会话。
- 默认列表隐藏手机归档，会话面板可切换查看归档。
- 已明确标注：这是手机平台归档，不代表 DeepSeek 桌面已同步。
- 已添加隔离测试 `python3 tools/test_dsh_archive.py`。

### 第三批：DeepSeek 图片链路（已实现，待真实兼容模型验收）

- 手机选择 PNG/JPEG/WebP/GIF，限制单张 3 MB、最多 4 张，支持预览和移除。
- 图片随 DeepSeek 任务持久保存，幂等指纹包含图片内容，网关限制格式、真实文件头和 base64。
- ACP `session/prompt` 使用官方 `image` content block；模型拒绝图片时返回明确提示。
- 历史解析支持内联图片和 DeepSeek content-addressed attachment 引用，校验 SHA-256 后才展示。
- 新增 `tools/test_dsh_images.py`，不调用模型。
- 网页仅在 DeepSeek 控制器报告 `runtime.imageInput=true` 时启用图片按钮，避免旧控制器静默丢弃附件。
- 当前代码尚未重启在线 DeepSeek 控制器；它可能正在执行本次手机任务，不能在任务中强制重启。真实端到端验收与部署仍待完成。

### 第四批：原生同步桥接（代码及隔离测试完成，安装待授权）

- 在桌面 Host 内调用 workspaceRegistry，不建立第二个 workspace 数据写入者。
- 私有 socket 仅提供状态、归档、恢复、登记到已有 workspace。
- 网关连通后读取桌面原生归档集；未连通时明确标注手机独立归档。
- 插件安装被沙箱拒绝，扩大权限批准已取消；没有绕过限制。
- 安装步骤及尚需真实验收的内容见 [DEEPSEEK-SYNC.md](DEEPSEEK-SYNC.md)。

### 尚未完成

1. 获得桌面 profile 安装许可、加载插件并验证桌面 workspace/原生归档双向变化。
2. 使用明确支持图片的 DeepSeek 模型做一次真实端到端验收。
3. DeepSeek 定向回归：桌面交接、归档恢复、图片失败场景。


## 验收边界

- 第一批不改变 Codex 或 WorkBuddy 的会话行为，也不解决这两者的内部会话显示问题。
- DeepSeek 子会话不再出现在普通历史及项目列表；正常主会话即使正文引用内部指令也不可误删。
- 代码验证和在线服务部署分开记录。未重启网关前，手机仍使用旧逻辑。
- 过滤后的 token 总量目前也会排除内部子会话，需要后续独立确定主子任务用量是否已归集，避免重复统计或误称完整账单。
