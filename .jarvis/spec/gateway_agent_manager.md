# Gateway Agent 管理功能规范

## 功能概述

为 Web Gateway 添加 Agent 管理功能，允许前端通过 Gateway 创建、管理和切换多个 Agent 实例（包括通用 Agent 和代码 Agent）。Gateway 负责以子进程方式启动 Agent，分配随机端口，并将端口信息返回给前端，前端直接连接到 Agent 端口进行通信，但 Agent 的生命周期管理（启动、停止）通过 Gateway 统一控制。

## 接口定义

### 1. HTTP API 端点

#### 创建 Agent

**端点**: `POST /api/agents`

**请求体**:

```json
{
  "agent_type": "agent" | "codeagent",
  "working_dir": "/path/to/project",
  "llm_group": "default",
  "tool_group": "default",
  "config_file": "/path/to/config.yaml",
  "task": "optional task description",
  "additional_args": {}
}
```

**响应体**:

```json
{
  "success": true,
  "data": {
    "agent_id": "uuid",
    "agent_type": "agent",
    "pid": 12345,
    "port": 8765,
    "status": "running",
    "working_dir": "/path/to/project",
    "created_at": "2024-01-01T00:00:00Z"
  }
}
```

**错误响应**:

```json
{
  "success": false,
  "error": {
    "code": "INVALID_AGENT_TYPE",
    "message": "Invalid agent type"
  }
}
```

#### 获取 Agent 列表

**端点**: `GET /api/agents`

**响应体**:

```json
{
  "success": true,
  "data": [
    {
      "agent_id": "uuid",
      "agent_type": "agent",
      "pid": 12345,
      "port": 8765,
      "status": "running",
      "working_dir": "/path/to/project",
      "created_at": "2024-01-01T00:00:00Z"
    }
  ]
}
```

#### 停止 Agent

**端点**: `DELETE /api/agents/{agent_id}`

**响应体**:

```json
{
  "success": true,
  "data": {
    "agent_id": "uuid",
    "status": "stopped"
  }
}
```

### 2. WebSocket 消息扩展

#### Agent 状态通知

Gateway 向前端发送 Agent 状态变更通知。

**消息格式**:

```json
{
  "type": "agent_status",
  "payload": {
    "agent_id": "uuid",
    "status": "running" | "stopped" | "error",
    "port": 8765,
    "message": "optional message"
  }
}
```

## 输入输出说明

### 创建 Agent 参数说明

- `agent_type` (必填): Agent 类型，可选值为 `"agent"` (通用 Agent) 或 `"codeagent"` (代码 Agent)
- `working_dir` (必填): Agent 的工作目录路径
- `llm_group` (可选): LLM 模型组名称，默认为 `"default"`
- `tool_group` (可选): 工具组名称，默认为 `"default"`
- `config_file` (可选): 配置文件路径
- `task` (可选): 任务描述（仅对 codeagent 有效）
- `additional_args` (可选): 其他额外的命令行参数

### Agent 状态说明

- `running`: Agent 正在运行
- `stopped`: Agent 已停止
- `error`: Agent 启动失败或运行出错

### 随机端口范围

- 范围: 10000-65535
- 端口可用性检查: 启动 Agent 前检查端口是否被占用

## 功能行为

### 正常情况

1. **创建 Agent**:
   - Gateway 接收前端创建请求
   - 生成唯一的 agent_id (UUID)
   - 分配一个可用的随机端口
   - 构建命令行参数启动 Agent 子进程
   - Agent 启动成功后，返回 agent_id、pid、端口等信息给前端
   - 前端使用返回的端口直接连接到 Agent 的 WebSocket 端点
   - Gateway 监控 Agent 子进程状态，当 Agent 异常退出时清理资源

2. **获取 Agent 列表**:
   - Gateway 返回所有活跃的 Agent 列表
   - 每个 Agent 包含基本信息和当前状态

3. **停止 Agent**:
   - Gateway 接收停止请求
   - 发送 SIGTERM 信号给 Agent 子进程
   - 等待进程退出（最多 10 秒）
   - 如果进程未退出，发送 SIGKILL 强制终止
   - 释放端口资源
   - 向前端返回停止成功响应

4. **Agent 异常退出**:
   - Gateway 监控到 Agent 子进程异常退出
   - 清理相关资源
   - 向前端发送 `agent_status` 消息通知状态变更

### 边界情况

1. **端口耗尽**:
   - 如果无法找到可用端口，返回错误响应
   - 错误码: `NO_AVAILABLE_PORT`

2. **工作目录不存在**:
   - 在启动 Agent 前验证工作目录是否存在
   - 如果不存在，返回错误响应
   - 错误码: `WORKING_DIR_NOT_FOUND`

3. **并发创建**:
   - 支持同时创建多个 Agent
   - 每个 Agent 分配独立的端口

### 异常情况

1. **Agent 启动失败**:
   - 如果子进程启动失败（如命令不存在、参数错误）
   - 返回错误响应
   - 错误码: `AGENT_START_FAILED`
   - 清理已分配的端口

2. **Agent 快速退出**:
   - 如果 Agent 在启动后立即退出（退出码非 0）
   - 标记状态为 `error`
   - 向前端发送错误通知

3. **停止不存在的 Agent**:
   - 返回错误响应
   - 错误码: `AGENT_NOT_FOUND`

## 验收标准

### 功能验收

1. **创建 Agent**:
   - [ ] 能够成功创建 `agent` 类型的 Agent
   - [ ] 能够成功创建 `codeagent` 类型的 Agent
   - [ ] 每个 Agent 分配的随机端口在 10000-65535 范围内
   - [ ] 返回的 agent_id 是唯一的 UUID
   - [ ] 返回的 pid 与实际运行的进程 ID 一致
   - [ ] Agent 能够正常启动并接受 WebSocket 连接

2. **获取 Agent 列表**:
   - [ ] 能够正确返回所有活跃的 Agent
   - [ ] 每个包含正确的状态信息
   - [ ] 没有活跃 Agent 时返回空列表

3. **停止 Agent**:
   - [ ] 能够正常停止运行的 Agent
   - [ ] Agent 进程被正确终止
   - [ ] 端口资源被正确释放
   - [ ] 停止后无法再连接到 Agent 的 WebSocket

4. **Agent 状态监控**:
   - [ ] Agent 异常退出时能正确检测到
   - [ ] Gateway 能向前端发送状态变更通知
   - [ ] 异常退出的 Agent 资源被正确清理

### 集成验收

1. **前端集成**:
   - [ ] 前端能够调用 Gateway API 创建 Agent
   - [ ] 前端能够使用返回的端口连接到 Agent
   - [ ] 前端能够切换不同的 Agent
   - [ ] 前端能够显示 Agent 列表

2. **多 Agent 管理**:
   - [ ] 能够同时运行多个 Agent
   - [ ] 每个 Agent 使用不同的端口
   - [ ] 前端能够同时连接多个 Agent

### 安全性验收

1. **端口安全**:
   - [ ] 不会分配系统保留端口（< 10000）
   - [ ] 分配前检查端口是否被占用

2. **进程管理**:
   - [ ] Agent 进程在 Gateway 停止时被正确清理
   - [ ] 不会出现僵尸进程

### 性能验收

1. **响应时间**:
   - [ ] 创建 Agent 的响应时间 < 5 秒
   - [ ] 获取 Agent 列表的响应时间 < 100ms
   - [ ] 停止 Agent 的响应时间 < 2 秒

2. **资源限制**:
   - [ ] 支持 10 个并发 Agent
   - [ ] 内存占用在合理范围内

## 实现架构

### 后端组件

1. **AgentManager**: 管理 Agent 生命周期
   - 创建、停止、监控 Agent
   - 维护 Agent 状态
   - 端口分配和释放

2. **API 路由**: 提供 HTTP API
   - `POST /api/agents`: 创建 Agent
   - `GET /api/agents`: 获取 Agent 列表
   - `DELETE /api/agents/{agent_id}`: 停止 Agent

3. **WebSocket 扩展**: 通知 Agent 状态变更
   - 发送 `agent_status` 消息

### 前端组件

1. **Agent 列表 UI**: 显示所有 Agent
   - Agent 类型、状态、端口
   - 创建、停止、切换操作

2. **Agent 切换**: 切换当前连接的 Agent
   - 保存每个 Agent 的连接状态
   - 切换时断开旧连接，建立新连接

3. **创建 Agent 表单**: 输入 Agent 配置
   - Agent 类型选择
   - 工作目录输入
   - 其他可选参数

4. **Gateway 重启交互**: 在设置弹窗中提供重启服务入口
   - 点击“重启服务”按钮时，必须先弹出确认对话框
   - 只有用户明确确认后，才发送重启请求
   - 用户取消时，不发起任何重启请求
   - 成功或失败后继续使用现有提示机制反馈结果

## 测试计划

1. **单元测试**:
   - 端口分配和释放
   - Agent 状态管理
   - 进程启动和停止

2. **集成测试**:
   - 创建 Agent 并连接
   - 停止 Agent 并验证资源释放
   - 多 Agent 并发操作

3. **端到端测试**:
   - 前端创建 Agent 并切换
   - Agent 异常退出时的通知
   - 点击“重启服务”时先出现确认弹窗
   - 取消确认时不会发送重启请求
   - 确认后才触发 Gateway 重启并验证状态恢复
