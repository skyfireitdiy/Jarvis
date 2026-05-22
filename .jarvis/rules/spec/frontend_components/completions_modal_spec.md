---
name: completions_modal
description: 补全模态框组件，负责命令和文件补全功能。
---

# 补全模态框组件规范

## 功能概述

将 App.vue 中的补全模态框拆分为独立的 Vue 组件 `CompletionsModal.vue`。

主要功能：

- 命令补全搜索
- 文件路径补全
- 补全项使用统计
- 补全项排序推荐

## 接口定义

### Props

| 名称 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `visible` | Boolean | `false` | 模态框是否可见 |
| `completions` | Array | `[]` | 补全项列表 |
| `fileCompletions` | Array | `[]` | 文件补全结果 |
| `currentInput` | String | `''` | 当前输入内容 |

### Events

| 事件名 | 参数 | 说明 |
|--------|------|------|
| `update:visible` | `Boolean` | 更新可见状态 |
| `select` | `item` | 选择补全项 |
| `search` | `query` | 搜索补全项 |

## 内部状态

- `searchQuery`: 搜索关键词
- `selectedIndex`: 当前选中的索引
- `completionUsageStats`: 使用统计
- `completionItemsRef`: 补全项元素引用

## 功能行为

### 补全搜索

1. 实时过滤补全列表
2. 支持命令和文件两种模式
3. 搜索结果按相关性排序

### 补全排序

1. 基于使用频率排序
2. 基于最近使用时间排序
3. 基于原始顺序排序

### 使用统计

1. 记录补全项选择次数
2. 记录最后使用时间
3. 统计数据持久化存储

### 键盘导航

1. 上下箭头选择补全项
2. 回车键确认选择
3. ESC 键关闭模态框
4. Tab 键切换补全模式

### 文件补全

1. 支持相对路径和绝对路径
2. 实时显示文件列表
3. 支持目录导航

## 样式规范

- 类名前缀：`.completions-modal`
- 支持高亮匹配文本
- 显示补全项详细信息