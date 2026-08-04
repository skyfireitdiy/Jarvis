---
name: cross_node_agent_creation
description: 当需要在远程节点上创建Agent时触发。每当用户提及"创建Agent"、"在节点上运行"、"跨节点"时触发。不触发：本节点创建Agent；Agent管理非创建操作；节点配置管理。
---
# 跨节点 Agent 创建指南

## 规则简介

于 Jarvis 多节点环境中，创建跨节点 Agent 需额外注意目标节点之环境差异（架构、文件系统、可用模型组等）。本规则总结跨节点 Agent 创建之最佳实践，避因路径错误、模型组不存在等问题致 Agent 启动失败。

## 汝必遵守之原则

### 1. 创建前必确认目标节点信息

**要求说明：**

- **必**：用 `list_nodes` 确认目标节点在线且状态正常
- **必**：用 `list_model_groups` 确认目标节点可用之模型组列表
- **必**：确认目标节点之架构（armv7l / x86_64 / aarch64 等），不同架构可能影响工具与依赖之可用性
- **禁**：假设目标节点之文件系统结构与 master 节点相同
- **禁**：用未经验证之模型组名称
**示例：**

```json
// 1. 确认节点在线
{"action": "list_nodes"}
// 2. 确认可用模型组
{"action": "list_model_groups", "node_id": "hinas"}
```

### 2. 工作目录必用目标节点实际路径

**要求说明：**

- **必**：用目标节点上真实存在之路径作为 `working_dir`
- **必**：优先用 `.`（当前目录）作为工作目录，令系统自动解析至正确路径
- **禁**：直接复制 master 节点之路径（如 `/home/skyfire`）至其他节点
- **禁**：假设所有节点之用户主目录路径相同
**示例：**

```json
// ✅ 推荐：用 "." 令系统自动解析
{"working_dir": "."}
// ✅ 亦可：用目标节点确认存在之绝对路径
{"working_dir": "/mnt/sda1/skyfire"}
// ❌ 错误：假设路径与 master 相同
{"working_dir": "/home/skyfire"}
```

### 3. agent_type 必用正确值

**要求说明：**

- **必**：`agent_type` 只能用 `"agent"` 或 `"codeagent"`
- **禁**：用 `"chat"` 或其他无效值，致创建失败

## 汝必执行之操作

### 操作1：创建跨节点 Agent 之标准流程

**执行步骤：**

1. 用 `list_nodes` 确认目标节点在线
2. 用 `list_model_groups` 获取目标节点可用模型组
3. 选一确认存在之模型组（如 `xunfei`、`deepseek_v3` 等）
4. 用 `create_agent` 创建 Agent，关键参数：
   - `node_id`：目标节点 ID
   - `agent_type`：`"agent"` 或 `"codeagent"`
   - `working_dir`：优先用 `"."`
   - `llm_group`：目标节点确认可用之模型组
   - `no_interaction_mode`：无交互任务设为 `true`
   - `task`：明确之任务描述
5. 创建后用 `list_agents` 确认 Agent 状态为 `running`
**注意事项：**

- 若 Agent 状态变为 `error`，检查 `working_dir` 与 `llm_group` 是否正确
- BT 下载等长时间任务需耐心等待，勿过早判定失败
- 可通过 `list_directory` 检查目标节点文件系统确认路径有效性

### 操作2：失败后之排查步骤

**执行步骤：**

1. 检查 Agent 状态：`list_agents` 查看是否为 `error`
2. 分析失败原因：对比成功与失败案例之参数差异
3. 修正参数后重新创建，勿重复用相同错误参数
4. 清理失败之 Agent：用 `delete_agent` 删除 error 状态之 Agent

## 检查清单

创建跨节点 Agent 前，汝必确认：

- [ ] 目标节点在线且状态正常
- [ ] 已获取目标节点之可用模型组列表
- [ ] `working_dir` 用 `.` 或目标节点确认存在之绝对路径
- [ ] `agent_type` 为 `"agent"` 或 `"codeagent"`
- [ ] `llm_group` 于目标节点模型组列表中
- [ ] 任务描述（`task`）清晰完整

## 相关资源

- 参考规则：`add_builtin_command.md`
