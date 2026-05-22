---
name: editor_panel
description: 编辑器面板组件，负责文件树浏览、文件内容编辑和代码查看。
---

# 编辑器面板组件规范

## 功能概述

将 App.vue 中的编辑器面板功能拆分为独立的 Vue 组件 `EditorPanel.vue`。

主要功能：

- 文件树浏览与展开/折叠
- 文件搜索与过滤
- 文件内容查看与编辑
- 代码语法高亮
- 面板拖拽移动和调整大小

## 接口定义

### Props

| 名称 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `visible` | Boolean | `false` | 面板是否可见 |
| `socket` | Object | `null` | WebSocket 连接对象 |
| `currentAgentId` | String | `null` | 当前 Agent ID |
| `currentAgent` | Object | `null` | 当前 Agent 对象 |

### Events

| 事件名 | 参数 | 说明 |
|--------|------|------|
| `update:visible` | `Boolean` | 更新可见状态 |
| `file-selected` | `{ path, content }` | 文件被选中 |
| `file-saved` | `{ path }` | 文件保存成功 |

### Expose

| 方法名 | 参数 | 说明 |
|--------|------|------|
| `loadFileTree` | `agentId, rootPath` | 加载文件树 |
| `openFile` | `path` | 打开指定文件 |
| `saveFile` | - | 保存当前文件 |

## 内部状态

- `fileTree`: 文件树数据
- `expandedNodes`: 已展开的节点集合
- `selectedFile`: 当前选中的文件
- `fileContent`: 当前文件内容
- `searchQuery`: 搜索关键词
- `editorPanelRect`: 面板位置和大小
- `isEditorMaximized`: 是否最大化

## 功能行为

### 文件树管理

1. 懒加载子目录内容
2. 支持展开/折叠节点
3. 显示文件/文件夹图标
4. 支持搜索过滤

### 文件编辑

1. 支持查看文件内容
2. 支持基本的文本编辑
3. 根据文件类型显示语法高亮
4. 支持保存修改

### 面板交互

1. 支持拖拽标题栏移动面板
2. 支持拖拽边缘调整大小（8方向）
3. 支持双击标题栏最大化/还原
4. 面板位置和大小持久化存储

## 样式规范

- 类名前缀：`.editor-panel`
- 支持 `.editor-panel-dragging` 状态
- 最小尺寸：360x260