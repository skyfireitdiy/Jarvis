---
name: agent_terminal_button
description: 为VS Code扩展中的Agent列表添加终端按钮，点击后打开VS Code集成终端并连接到Agent的终端会话
---

# Agent 终端按钮功能规范

## 功能概述

为VS Code扩展的Agent列表中的每个Agent添加一个"打开终端"按钮，用户点击后可以打开VS Code集成终端，并通过WebSocket连接到后端Agent的终端会话。该功能模拟前端App.vue中终端面板的行为，但将终端映射到VS Code的集成终端中。

### 使用场景

- 用户在VS Code扩展中查看Agent列表时，希望快速打开终端与Agent交互
- 用户希望使用VS Code原生终端而不是Web终端面板
- 用户需要在终端中执行命令、查看输出

## 接口定义

### 1. Webview消息接口

#### 1.1 打开终端消息

```typescript
interface OpenTerminalMessage {
  type: "openTerminal";
  agentId: string; // Agent的唯一标识符
}
```

#### 1.2 终端输入消息

```typescript
interface TerminalInputMessage {
  type: "terminal_input";
  terminal_id: string; // 终端会话ID
  data: string; // 用户输入的数据
}
```

#### 1.3 终端调整大小消息

```typescript
interface TerminalResizeMessage {
  type: "terminal_resize";
  terminal_id: string; // 终端会话ID
  rows: number; // 终端行数
  cols: number; // 终端列数
}
```

#### 1.4 终端关闭消息

```typescript
interface TerminalCloseMessage {
  type: "terminal_close";
  terminal_id: string; // 终端会话ID
  node_id?: string; // 节点ID（可选）
}
```

### 2. WebSocket消息接口（发送到后端）

#### 2.1 创建终端

```json
{
  "type": "terminal_create",
  "payload": {
    "node_id": "master", // 可选，节点ID
    "working_dir": "~/workspace" // 可选，工作目录
  }
}
```

#### 2.2 终端输入

```json
{
  "type": "terminal_input",
  "payload": {
    "terminal_id": "term_xxx",
    "data": "ls -la\n"
  }
}
```

#### 2.3 终端调整大小

```json
{
  "type": "terminal_resize",
  "payload": {
    "terminal_id": "term_xxx",
    "rows": 24,
    "cols": 80
  }
}
```

#### 2.4 终端关闭

```json
{
  "type": "terminal_close",
  "payload": {
    "terminal_id": "term_xxx",
    "node_id": "master"
  }
}
```

### 3. WebSocket消息接口（从后端接收）

#### 3.1 终端创建成功

```json
{
  "type": "terminal_created",
  "payload": {
    "terminal_id": "term_xxx",
    "interpreter": "bash",
    "working_dir": "/home/user"
  }
}
```

#### 3.2 终端输出

```json
{
  "type": "terminal_output",
  "payload": {
    "terminal_id": "term_xxx",
    "data": "output text..."
  }
}
```

#### 3.3 终端关闭

```json
{
  "type": "terminal_closed",
  "payload": {
    "terminal_id": "term_xxx"
  }
}
```

### 4. VS Code API接口

#### 4.1 创建终端

```typescript
vscode.window.createTerminal(options?: TerminalOptions): Terminal
```

#### 4.2 TerminalOptions

```typescript
interface TerminalOptions {
  name: string; // 终端名称
  pty?: Pseudoterminal; // 伪终端实现
}
```

#### 4.3 Pseudoterminal接口

```typescript
interface Pseudoterminal {
  onDidWrite: Event<string>; // 终端输出事件
  onDidClose?: Event<void>; // 终端关闭事件
  open(initialDimensions: TerminalDimensions | undefined): void; // 终端打开
  close(): void; // 终端关闭
  handleInput?(data: string): void; // 处理用户输入
  setDimensions?(dimensions: TerminalDimensions): void; // 设置尺寸
}
```

## 输入输出说明

### 输入

| 参数       | 类型   | 必需 | 说明                                  |
| ---------- | ------ | ---- | ------------------------------------- |
| agentId    | string | 是   | Agent的唯一标识符                     |
| workingDir | string | 否   | 终端工作目录，默认使用Agent的工作目录 |
| nodeId     | string | 否   | 节点ID，默认使用Agent的节点ID         |

### 输出

| 类型            | 说明                                          |
| --------------- | --------------------------------------------- |
| Terminal        | VS Code终端实例                               |
| TerminalSession | 终端会话对象，包含terminal_id、terminal实例等 |

### 终端会话对象

```typescript
interface AgentTerminalSession {
  terminalId: string; // 终端会话ID
  agentId: string; // 关联的Agent ID
  terminal: vscode.Terminal; // VS Code终端实例
  pty: vscode.Pseudoterminal; // 伪终端实现
  nodeId: string; // 节点ID
  workingDir: string; // 工作目录
  closed: boolean; // 是否已关闭
}
```

## 功能行为

### 正常流程

1. **用户点击"打开终端"按钮**
   - Webview发送`openTerminal`消息到扩展主机
   - 扩展主机获取Agent信息（nodeId、workingDir）
   - 创建Pseudoterminal实例
   - 创建VS Code终端
   - 通过WebSocket发送`terminal_create`消息到后端

2. **后端返回终端创建成功**
   - 接收`terminal_created`消息
   - 保存terminal_id到会话对象
   - 终端准备就绪，可以接收输入

3. **用户在终端中输入**
   - Pseudoterminal的`handleInput`被调用
   - 通过WebSocket发送`terminal_input`消息
   - 后端执行命令并返回输出

4. **后端返回终端输出**
   - 接收`terminal_output`消息
   - 通过Pseudoterminal的`onDidWrite`事件写入终端

5. **用户关闭终端**
   - Pseudoterminal的`close`被调用
   - 通过WebSocket发送`terminal_close`消息
   - 清理会话对象

6. **后端关闭终端**
   - 接收`terminal_closed`消息
   - 触发Pseudoterminal的`onDidClose`事件
   - 清理会话对象

### 边界条件

1. **Agent不存在或已停止**
   - 显示错误消息"Agent不存在或已停止"
   - 不创建终端

2. **WebSocket未连接**
   - 显示错误消息"未连接到网关"
   - 不创建终端

3. **终端创建失败**
   - 显示错误消息"创建终端失败"
   - 清理已创建的资源

4. **重复点击按钮**
   - 如果该Agent已有活跃终端，聚焦到已有终端
   - 不创建新终端

5. **终端输出过大**
   - 使用节流函数限制输出频率
   - 避免UI卡顿

### 异常处理

1. **WebSocket连接断开**
   - 关闭所有终端会话
   - 显示通知消息

2. **终端创建超时**
   - 10秒内未收到`terminal_created`消息
   - 显示超时错误
   - 清理资源

3. **终端输出解码失败**
   - 尝试使用UTF-8解码
   - 如果失败，使用原始数据

## 验收标准

### AC1: 按钮显示

- **Given** 用户已连接到网关
- **When** 查看Agent列表
- **Then** 每个Agent项显示"打开终端"按钮（🖥️图标）

### AC2: 终端创建

- **Given** 用户已连接到网关
- **When** 点击Agent的"打开终端"按钮
- **Then** 创建VS Code集成终端，名称格式为"Jarvis: {agentName}"

### AC3: 终端连接

- **Given** 终端已创建
- **When** 后端返回`terminal_created`消息
- **Then** 终端准备就绪，可以接收用户输入

### AC4: 终端输入

- **Given** 终端已准备就绪
- **When** 用户在终端中输入命令并回车
- **Then** 命令通过WebSocket发送到后端执行

### AC5: 终端输出

- **Given** 终端已准备就绪
- **When** 后端返回`terminal_output`消息
- **Then** 输出内容显示在VS Code终端中

### AC6: 终端关闭（用户主动）

- **Given** 终端已打开
- **When** 用户关闭VS Code终端
- **Then** 发送`terminal_close`消息，清理会话资源

### AC7: 终端关闭（后端触发）

- **Given** 终端已打开
- **When** 后端返回`terminal_closed`消息
- **Then** VS Code终端关闭，清理会话资源

### AC8: 重复点击处理

- **Given** Agent已有活跃终端
- **When** 再次点击"打开终端"按钮
- **Then** 聚焦到已有终端，不创建新终端

### AC9: 错误处理

- **Given** WebSocket未连接
- **When** 点击"打开终端"按钮
- **Then** 显示错误消息"未连接到网关"

### AC10: 终端调整大小

- **Given** 终端已打开
- **When** 用户调整VS Code终端大小
- **Then** 发送`terminal_resize`消息到后端

## 技术约束

1. **必须使用** VS Code Extension API的`Pseudoterminal`接口
2. **必须使用** 现有的WebSocket连接到网关
3. **必须遵循** 现有的代码风格和命名规范
4. **禁止修改** 其他功能的现有代码
5. **必须确保** 终端会话正确清理，避免内存泄漏

## 实现计划

### 步骤1: 添加AgentTerminalSession接口

- 在extension.ts中定义`AgentTerminalSession`接口
- 添加`agentTerminalSessions` Map存储会话

### 步骤2: 实现AgentTerminalPty类

- 实现`vscode.Pseudoterminal`接口
- 处理终端输入、输出、关闭事件

### 步骤3: 实现openTerminalForAgent函数

- 获取Agent信息
- 创建Pseudoterminal和VS Code终端
- 发送WebSocket消息创建终端

### 步骤4: 添加消息处理逻辑

- 处理`openTerminal`消息
- 处理`terminal_created`、`terminal_output`、`terminal_closed`消息

### 步骤5: 修改Agent列表HTML模板

- 在Agent操作区域添加"打开终端"按钮
- 添加按钮点击事件处理

### 步骤6: 添加清理逻辑

- WebSocket断开时清理所有终端会话
- 扩展停用时清理资源

## 文件变更

### 修改文件

- `src/jarvis/jarvis_vscode_extension/src/extension.ts`

### 变更内容

1. 添加`AgentTerminalSession`接口定义
2. 添加`AgentTerminalPty`类实现
3. 添加`agentTerminalSessions` Map
4. 添加`openTerminalForAgent`方法
5. 修改`getAgentListHtml`方法，添加终端按钮
6. 修改消息处理逻辑，添加终端相关消息处理
7. 添加清理逻辑
