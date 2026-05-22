---
name: agent_data_storage_spec
description: Agent 网关数据存储接口规范，提供统一的 Key-Value 存储功能
---

# Agent 网关数据存储接口规范

## 功能概述
为 Jarvis 的两类 Agent 网关（General Agent 和 Code Agent）提供统一的数据存储接口，支持通过 REST API 进行 Key-Value 数据的持久化存储。

## 接口定义

### API 端点

#### 1. 保存数据
- **路径**: `POST /data/{key}`
- **请求体**: JSON 对象，包含要存储的值
- **响应**: 
  - 成功: `{"success": true, "message": "Data saved successfully"}`
  - 失败: `{"success": false, "error": "Error message"}`

#### 2. 读取数据
- **路径**: `GET /data/{key}`
- **响应**:
  - 成功: `{"success": true, "data": <stored_value>}`
  - 不存在: `{"success": false, "error": "Key not found"}`
  - 失败: `{"success": false, "error": "Error message"}`

#### 3. 删除数据
- **路径**: `DELETE /data/{key}`
- **响应**:
  - 成功: `{"success": true, "message": "Data deleted successfully"}`
  - 不存在: `{"success": false, "error": "Key not found"}`
  - 失败: `{"success": false, "error": "Error message"}`

### Key 值规范
- **允许字符**: 字母（a-z, A-Z）、数字（0-9）、下划线（_）、短横线（-）
- **长度限制**: 1-64 字符
- **安全要求**: 禁止包含路径分隔符（/、\）和特殊字符（.、..）

## 存储逻辑

### 存储位置
- **根目录**: `~/.jarvis/data_store/`
- **文件命名**: `{key}.json`
- **文件格式**: JSON 格式存储值

### 并发处理
- 使用原子写入（先写入临时文件，再重命名）
- 读取时使用共享锁
- 删除时使用排他锁

### 数据格式
- 存储值可以是任意 JSON 可序列化的数据类型
- 文件内容为 JSON 字符串

## 异常处理

### 错误场景
1. **Key 格式无效**: 返回 400 错误
2. **Key 不存在**: 返回 404 错误
3. **存储失败**: 返回 500 错误
4. **读取失败**: 返回 500 错误
5. **删除失败**: 返回 500 错误

### 错误响应格式
```json
{
  "success": false,
  "error": "具体错误描述"
}
```

## 验收标准

1. **功能完整性**
   - 能够通过 POST 接口成功保存数据
   - 能够通过 GET 接口成功读取已保存的数据
   - 能够通过 DELETE 接口成功删除数据
   - 两类 Agent 网关（jarvis.py 和 code_agent.py）均能正常工作

2. **数据持久化**
   - 数据正确存储在 `~/.jarvis/data_store/` 目录下
   - 文件内容为有效的 JSON 格式
   - 文件名与 Key 值一致

3. **安全性**
   - Key 值校验正确，拒绝非法字符
   - 防止路径遍历攻击
   - 错误信息不泄露系统敏感信息

4. **并发安全**
   - 多个请求同时操作不同 Key 时不会冲突
   - 原子写入确保数据完整性

5. **错误处理**
   - 所有错误场景都有明确的错误响应
   - 错误响应格式一致

## 测试场景

### 正常流程
1. 保存数据 `{"test": "value"}` 到 Key `test-key`
2. 读取 Key `test-key`，验证返回数据
3. 删除 Key `test-key`
4. 再次读取 Key `test-key`，验证返回 404

### 边界测试
1. 使用包含特殊字符的 Key（应被拒绝）
2. 使用超长 Key（应被拒绝）
3. 保存空 JSON 对象 `{}`
4. 保存复杂嵌套 JSON 数据

### 错误测试
1. 读取不存在的 Key
2. 删除不存在的 Key
3. 保存无效 JSON 数据
4. 使用非法 Key 格式