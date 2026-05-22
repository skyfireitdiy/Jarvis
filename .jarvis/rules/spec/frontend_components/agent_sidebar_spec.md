---
name: agent_sidebar
description: Agent 侧边栏组件，负责 Agent 列表显示、批量操作、Agent 状态管理和侧边栏布局调整。
---

# Agent 侧边栏组件规范

## 功能概述

将 App.vue 中的 Agent 侧边栏功能拆分为独立的 Vue 组件 `AgentSidebar.vue`。

主要功能：

- Agent 列表分组显示（运行中/已停止）
- Agent 状态指示器
- Agent 快捷操作（创建终端、重命名、复制、删除）
- 批量选择模式与批量操作
- 侧边栏宽度拖拽调整
- 响应式折叠/展开

## 接口定义

### Props

| 名称 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `visible` | Boolean | `true` | 侧边栏是否可见 |
| `agents` | Array | `[]` | Agent 列表数据 |
| `currentAgentId` | String | `null` | 当前选中的 Agent ID |
## Internal State

- `collapsedGroups`: Set of collapsed group keys for managing fold state of each node group
- `isBatchMode`: Whether in batch selection mode
- `selectedAgents`: Set of selected Agent IDs
- `agentSidebarWidth`: Sidebar width
- `agentSidebarResizeState`: Drag resize state
|--------|------|------|
| `update:visible` | `Boolean` | 更新可见状态 |
| `select-agent` | `agent` | 选中某个 Agent |
| `create-agent` | - | 请求创建新 Agent |
| `rename-agent` | `agent` | 请求重命名 Agent |
| `copy-agent` | `agent` | 请求复制 Agent |
### List Display

1. Running Agents are displayed in a non-collapsible group
2. Stopped Agents are grouped by node (node_id), each node forms a collapsible group
3. Group key format: `stopped-${nodeId}`, node label obtained via `getAgentNodeLabel(agent)`
4. When selecting a stopped Agent, the corresponding node group auto-expands
5. Display Agent type icon, status indicator, node info, LLM group, Worktree and quick mode markers
| `create-terminal` | `agent` | 为 Agent 创建终端 |

## 内部状态

- `showStoppedAgents`: 是否显示已停止的 Agent
- `isBatchMode`: 是否处于批量选择模式
- `selectedAgents`: 已选中的 Agent ID 集合
- `agentSidebarWidth`: 侧边栏宽度
- `agentSidebarResizeState`: 拖拽调整状态

## 功能行为

### 列表显示

1. 将 Agent 分为“运行中”和“已停止”两组
2. 已停止的 Agent 默认折叠，可点击展开
3. 显示 Agent 类型图标、状态指示器、节点信息、LLM 组、Worktree 和极速模式标记

### 批量操作

1. 点击批量按钮进入批量模式
2. 支持全选/取消全选
3. 支持批量复制和删除

### 侧边栏调整

1. 支持拖拽右侧边缘调整宽度
2. 宽度限制在 240px - 560px 之间
3. 宽度持久化存储到 localStorage

## 样式规范

- 类名前缀：`.agent-sidebar`
- 支持 `.collapsed` 状态
- 响应式设计：移动端自动隐藏