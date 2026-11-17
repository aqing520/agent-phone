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

### 尚未完成

1. DeepSeek 桌面 workspace/未分组接入及原生归档同步：桌面服务没有对当前网关公开可用的 listener，不能直接写私有 workspace 状态。
2. 使用明确支持图片的 DeepSeek 模型做一次真实端到端验收。
3. DeepSeek 定向回归：桌面交接、归档恢复、图片失败场景。


## 验收边界

- 第一批不改变 Codex 或 WorkBuddy 的会话行为，也不解决这两者的内部会话显示问题。
- DeepSeek 子会话不再出现在普通历史及项目列表；正常主会话即使正文引用内部指令也不可误删。
- 代码验证和在线服务部署分开记录。未重启网关前，手机仍使用旧逻辑。
- 过滤后的 token 总量目前也会排除内部子会话，需要后续独立确定主子任务用量是否已归集，避免重复统计或误称完整账单。
