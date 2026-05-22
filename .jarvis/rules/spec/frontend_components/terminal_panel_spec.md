---
name: terminal_panel
description: 终端面板组件，负责独立终端会话管理和执行终端嵌入显示。
---

# 终端面板组件规范

## 功能概述

将 App.vue 中的终端面板功能拆分为独立的 Vue 组件 `TerminalPanel.vue`。

主要功能：

- 独立终端会话管理（创建、关闭、切换）
- 终端面板拖拽移动和调整大小
- 终端最大化/还原
- 节点选择与终端创建
- 终端输入输出处理

## 接口定义

### Props

| 名称 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `visible` | Boolean | `false` | 面板是否可见 |
| `socket` | Object | `null` | WebSocket 连接对象 |
| `nodes` | Array | `[]` | 可用节点列表 |
| `currentAgentId` | String | `null` | 当前 Agent ID |

### Events

| 事件名 | 参数 | 说明 |
|--------|------|------|
| `update:visible` | `Boolean` | 更新可见状态 |
| `terminal-created` | `terminalId` | 终端创建成功 |
| `terminal-closed` | `terminalId` | 终端关闭 |

### Expose

| 方法名 | 参数 | 说明 |
|--------|------|------|
| `createTerminalForAgent` | `agent` | 为指定 Agent 创建终端 |
| `sendInput` | `terminalId, data` | 发送终端输入 |
| `disposeTerminal` | `terminalId` | 销毁终端 |

## 内部状态

- `terminalSessions`: 终端会话列表
- `activeTerminalId`: 当前活动终端 ID
- `selectedTerminalNodeId`: 选中的节点 ID
- `terminalPanelRect`: 面板位置和大小
- `isTerminalMaximized`: 是否最大化
- `terminalPanelInteraction`: 拖拽/调整状态

## 功能行为

### 终端会话管理

1. 支持创建多个终端会话
2. 通过标签页切换不同终端
3. 支持关闭单个或所有终端

### 面板交互

1. 支持拖拽标题栏移动面板
2. 支持拖拽边缘调整大小（8方向）
3. 支持双击标题栏最大化/还原
4. 面板位置和大小持久化存储

### 终端通信

1. 通过 WebSocket 与后端通信
2. 处理终端输入输出数据
3. 处理终端大小同步

## 样式规范

- 类名前缀：`.terminal-panel`
- 支持 `.terminal-panel-dragging` 状态
- 最小尺寸：400x300