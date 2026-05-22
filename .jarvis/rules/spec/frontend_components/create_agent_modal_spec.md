---
name: create_agent_modal
description: 创建 Agent 模态框组件，负责新 Agent 的配置与创建。
---

# 创建 Agent 模态框组件规范

## 功能概述

将 App.vue 中的创建 Agent 模态框拆分为独立的 Vue 组件 `CreateAgentModal.vue`。

主要功能：

- Agent 类型选择（Agent/CodeAgent）
- 工作目录选择
- 模型组选择
- 节点选择
- 高级选项配置（Worktree、极速模式、恢复会话）

## 接口定义

### Props

| 名称 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `visible` | Boolean | `false` | 模态框是否可见 |
| `modelGroups` | Array | `[]` | 可用模型组列表 |
| `nodes` | Array | `[]` | 可用节点列表 |

### Events

| 事件名 | 参数 | 说明 |
|--------|------|------|
| `update:visible` | `Boolean` | 更新可见状态 |
| `create` | `agentConfig` | 提交创建请求 |
| `open-dir-dialog` | - | 请求打开目录选择器 |

## 内部状态

- `agentType`: Agent 类型 ('agent' | 'codeagent')
- `agentName`: Agent 名称
- `workingDir`: 工作目录
- `modelGroup`: 选中的模型组
- `nodeId`: 选中的节点 ID
- `enableWorktree`: 是否启用 Worktree
- `enableQuickMode`: 是否启用极速模式
- `enableRestoreSession`: 是否恢复会话

## 功能行为

### 表单输入

1. Agent 类型默认为 'codeagent'
2. 工作目录默认为用户主目录 '~'
3. 模型组默认为 'default'
4. 根据节点状态自动选择默认节点

### 高级选项

1. Worktree 选项仅对 CodeAgent 类型显示
2. 极速模式和恢复会话对所有类型显示

### 提交验证

1. 工作目录为必填项
2. 创建成功后自动关闭模态框并重置表单

## 样式规范

- 类名前缀：`.create-agent-modal`
- 遵循项目通用 Modal 样式