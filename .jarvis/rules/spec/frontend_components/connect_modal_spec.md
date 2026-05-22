---
name: connect_modal
description: 连接模态框组件，负责网关登录和连接配置。
---

# 连接模态框组件规范

## 功能概述

将 App.vue 中的连接模态框拆分为独立的 Vue 组件 `ConnectModal.vue`。

主要功能：

- 网关地址配置
- 密码认证登录
- 连接状态显示
- 错误信息展示

## 接口定义

### Props

| 名称 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `visible` | Boolean | `true` | 模态框是否可见 |
| `connecting` | Boolean | `false` | 是否正在连接 |
| `errorMessage` | String | `''` | 错误信息 |

### Events

| 事件名 | 参数 | 说明 |
|--------|------|------|
| `update:visible` | `Boolean` | 更新可见状态 |
| `connect` | `{ address, password }` | 请求连接 |

## 内部状态

- `gatewayAddress`: 网关地址输入
- `password`: 密码输入
- `showPassword`: 是否显示密码

## 功能行为

### 地址配置

1. 网关地址格式：`host:port`
2. 支持默认地址 `127.0.0.1:8000`
3. 地址持久化存储到 localStorage

### 认证登录

1. 支持密码认证
2. 密码输入框支持显示/隐藏切换
3. 回车键提交登录

### 连接状态

1. 连接中显示加载状态
2. 连接失败显示错误信息
3. 连接成功自动关闭模态框

## 样式规范

- 类名前缀：`.connect-modal`
- 居中显示
- 简洁的登录表单设计