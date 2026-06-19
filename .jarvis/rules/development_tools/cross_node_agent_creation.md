---
name: cross_node_agent_creation
description: 当需要在远程节点上创建 Agent 时使用此规则——跨节点 Agent 创建指南，确保 Agent 在目标节点上正确运行。包括：确认目标节点状态和架构；验证工作目录路径；选择正确的模型组；使用正确的 agent_type 参数。每当用户提及"创建 Agent"、"在节点上运行"、"跨节点"或需要在非 master 节点上部署 Agent 时触发，无论任务类型。如果需要创建跨节点 Agent，请使用此规则。
---

# 跨节点 Agent 创建指南

## 规则简介

在 Jarvis 多节点环境中，创建跨节点 Agent 需要额外注意目标节点的环境差异（架构、文件系统、可用模型组等）。本规则总结了跨节点 Agent 创建的最佳实践，避免因路径错误、模型组不存在等问题导致 Agent 启动失败。

## 你必须遵守的原则

### 1. 创建前必须确认目标节点信息

**要求说明：**

- **必须**：使用 `list_nodes` 确认目标节点在线且状态正常
- **必须**：使用 `list_model_groups` 确认目标节点可用的模型组列表
- **必须**：确认目标节点的架构（armv7l / x86_64 / aarch64 等），不同架构可能影响工具和依赖的可用性
- **禁止**：假设目标节点的文件系统结构与 master 节点相同
- **禁止**：使用未经验证的模型组名称

**示例：**

```json
// 1. 确认节点在线
{"action": "list_nodes"}

// 2. 确认可用模型组
{"action": "list_model_groups", "node_id": "hinas"}
```

### 2. 工作目录必须使用目标节点实际路径

**要求说明：**

- **必须**：使用目标节点上真实存在的路径作为 `working_dir`
- **必须**：优先使用 `.`（当前目录）作为工作目录，让系统自动解析到正确路径
- **禁止**：直接复制 master 节点的路径（如 `/home/skyfire`）到其他节点
- **禁止**：假设所有节点的用户主目录路径相同

**示例：**

```json
// ✅ 推荐：使用 "." 让系统自动解析
{"working_dir": "."}

// ✅ 也可以：使用目标节点确认存在的绝对路径
{"working_dir": "/mnt/sda1/skyfire"}

// ❌ 错误：假设路径与 master 相同
{"working_dir": "/home/skyfire"}
```

### 3. agent_type 必须使用正确值

**要求说明：**

- **必须**：`agent_type` 只能使用 `"agent"` 或 `"codeagent"`
- **禁止**：使用 `"chat"` 或其他无效值，会导致创建失败

## 你必须执行的操作

### 操作1：创建跨节点 Agent 的标准流程

**执行步骤：**

1. 使用 `list_nodes` 确认目标节点在线
2. 使用 `list_model_groups` 获取目标节点可用模型组
3. 选择一个确认存在的模型组（如 `xunfei`、`deepseek_v3` 等）
4. 使用 `create_agent` 创建 Agent，关键参数：
   - `node_id`：目标节点 ID
   - `agent_type`：`"agent"` 或 `"codeagent"`
   - `working_dir`：优先使用 `"."`
   - `llm_group`：目标节点确认可用的模型组
   - `no_interaction_mode`：无交互任务设为 `true`
   - `task`：明确的任务描述
5. 创建后使用 `list_agents` 确认 Agent 状态为 `running`

**注意事项：**

- 如果 Agent 状态变为 `error`，检查 `working_dir` 和 `llm_group` 是否正确
- BT 下载等长时间任务需要耐心等待，不要过早判定失败
- 可通过 `list_directory` 检查目标节点文件系统确认路径有效性

### 操作2：失败后的排查步骤

**执行步骤：**

1. 检查 Agent 状态：`list_agents` 查看是否为 `error`
2. 分析失败原因：对比成功和失败案例的参数差异
3. 修正参数后重新创建，不要重复使用相同错误参数
4. 清理失败的 Agent：使用 `delete_agent` 删除 error 状态的 Agent

## 检查清单

在创建跨节点 Agent 前，你必须确认：

- [ ] 目标节点在线且状态正常
- [ ] 已获取目标节点的可用模型组列表
- [ ] `working_dir` 使用 `.` 或目标节点确认存在的绝对路径
- [ ] `agent_type` 为 `"agent"` 或 `"codeagent"`
- [ ] `llm_group` 在目标节点模型组列表中
- [ ] 任务描述（`task`）清晰完整

## 相关资源

- 参考规则：`add_builtin_command.md`
