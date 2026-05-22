---
name: settings_modal
description: 设置模态框组件，负责网关配置、节点管理和系统设置。
---

# 设置模态框组件规范

## 功能概述

将 App.vue 中的设置模态框拆分为独立的 Vue 组件 `SettingsModal.vue`。

主要功能：

- 网关连接地址配置
- 节点状态查看与管理
- 网关服务重启
- 配置同步（LLM、模型组）
- 连接锁定设置

## 接口定义

### Props

| 名称 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `visible` | Boolean | `false` | 模态框是否可见 |
| `gatewayUrl` | String | `''` | 当前网关地址 |
| `nodes` | Array | `[]` | 节点列表 |
| `connectionLockEnabled` | Boolean | `false` | 连接锁定状态 |

### Events

| 事件名 | 参数 | 说明 |
|--------|------|------|
| `update:visible` | `Boolean` | 更新可见状态 |
| `update:gatewayUrl` | `String` | 更新网关地址 |
| `update:connectionLockEnabled` | `Boolean` | 更新连接锁定状态 |
| `restart-gateway` | `{ nodeId, restartFrontend }` | 请求重启网关 |
| `sync-config` | `{ sourceNode, targetNodes, sections }` | 请求同步配置 |

## 内部状态

- `restartNodeId`: 重启服务选择的节点 ID
- `restartFrontendService`: 是否同时重启前端服务
- `syncConfigSourceNode`: 配置同步源节点
- `syncConfigTargetNodes`: 配置同步目标节点数组
- `syncConfigSections`: 要同步的配置类型
- `isSyncingConfig`: 是否正在同步配置
- `isRestartingGateway`: 是否正在重启网关

## 功能行为

### 网关设置

1. 显示当前网关连接地址
2. 支持修改网关地址
3. 提供连接测试功能

### 节点管理

1. 显示所有节点状态（在线/离线）
2. 显示节点资源使用情况
3. 支持选择节点进行重启

### 配置同步

1. 支持选择源节点和目标节点
2. 支持选择同步的配置类型（LLM、模型组）
3. 显示同步进度和结果

### 连接设置

1. 连接锁定开关
2. 锁定状态持久化存储

## 样式规范

- 类名前缀：`.settings-modal`
- 遵循项目通用 Modal 样式
- 内容区域支持滚动